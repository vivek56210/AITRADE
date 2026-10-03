#!/usr/bin/env bash
# ATIS one-shot setup for an Oracle Cloud Always Free VM (Ubuntu 24.04, Ampere A1 or E2.1.Micro).
#
#   curl -fsSL https://raw.githubusercontent.com/vivek56210/AITRADE/claude/sweet-dirac-l8xhkg/deploy/oracle/setup.sh -o atis-setup.sh
#   sudo bash atis-setup.sh
#
# What it does (safe to re-run; it keeps existing secrets unless you choose to change them):
#   - installs Python, Node 22 (to build the UI) and Caddy (HTTPS + password in front of the console)
#   - clones the code to /opt/atis, data lives in /var/lib/atis, secrets in /etc/atis/atis.env (root/atis, 640)
#   - atis-console.service : the web console on 127.0.0.1:8765 (never exposed directly)
#   - atis-live.timer      : starts atis-live.service at 08:55 IST Mon-Fri; it sends Telegram alerts and exits at 15:31
#   - Caddy serves https://<public-ip>.sslip.io with a login, and the VM firewall opens ports 80/443
# Alerts only: nothing here can place an order.
set -euo pipefail

REPO_URL="${ATIS_REPO_URL:-https://github.com/vivek56210/AITRADE.git}"
BRANCH="${ATIS_BRANCH:-claude/sweet-dirac-l8xhkg}"
APP_DIR=/opt/atis
DATA_DIR=/var/lib/atis
ENV_FILE=/etc/atis/atis.env
CADDY_AUTH_FILE=/etc/atis/caddy-auth
PORT=8765

say()  { printf '\n\033[1;34m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m!! %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mxx %s\033[0m\n' "$*" >&2; exit 1; }
ask()  { local v; read -r -p "$1" v </dev/tty; printf '%s' "$v"; }
ask_secret() { local v; read -r -s -p "$1" v </dev/tty; echo >/dev/tty; printf '%s' "$v"; }
env_get() { [ -f "$ENV_FILE" ] && sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 || true; }

[ "$(id -u)" -eq 0 ] || die "run with sudo: sudo bash $0"
. /etc/os-release
[ "${ID:-}" = ubuntu ] || warn "tested on Ubuntu 24.04; this is ${PRETTY_NAME:-unknown}"
[ -e /dev/tty ] || die "needs an interactive terminal (run it over SSH or in Cloud Shell, not piped from a script)"

# ---------------------------------------------------------------- packages
say "System packages"
export DEBIAN_FRONTEND=noninteractive
timedatectl set-timezone Asia/Kolkata || true
if [ "$(awk '/MemTotal/ {print $2}' /proc/meminfo)" -lt 2000000 ] && ! swapon --show | grep -q .; then
  say "Small VM: adding a 2 GB swap file"
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
apt-get update -qq
apt-get install -y -qq git curl ca-certificates gnupg python3 python3-venv python3-pip \
  debian-keyring debian-archive-keyring apt-transport-https iptables-persistent >/dev/null

if ! command -v node >/dev/null || [ "$(node -p 'process.versions.node.split(".")[0]')" -lt 22 ]; then
  say "Node.js 22 (only used to build the web UI)"
  curl -fsSL https://deb.nodesource.com/setup_22.x | bash - >/dev/null
  apt-get install -y -qq nodejs >/dev/null
fi

if ! command -v caddy >/dev/null; then
  say "Caddy web server"
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt > /etc/apt/sources.list.d/caddy-stable.list
  apt-get update -qq && apt-get install -y -qq caddy >/dev/null
fi

# ---------------------------------------------------------------- code
say "ATIS code ($BRANCH)"
id atis >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin atis
install -d -o atis -g atis "$DATA_DIR" "$DATA_DIR/data" "$DATA_DIR/data/live" "$DATA_DIR/data/upstox"
if [ -d "$APP_DIR/.git" ]; then
  git -C "$APP_DIR" fetch -q origin "$BRANCH" && git -C "$APP_DIR" checkout -q -B "$BRANCH" "origin/$BRANCH"
else
  git clone -q --branch "$BRANCH" "$REPO_URL" "$APP_DIR"
fi
bash "$APP_DIR/deploy/oracle/update.sh" --build-only

# ---------------------------------------------------------------- secrets
say "Telegram and login settings"
install -d -m 750 -o root -g atis /etc/atis
TOKEN="$(env_get TELEGRAM_BOT_TOKEN)"
CHAT="$(env_get TELEGRAM_CHAT_ID)"
if [ -n "$TOKEN" ] && [ "$(ask 'Telegram bot token is already saved. Replace it? [y/N] ')" != y ]; then :; else
  echo "Paste the token BotFather gave you (input is hidden; it is stored only in $ENV_FILE)."
  TOKEN="$(ask_secret 'Bot token: ')"
  [[ "$TOKEN" =~ ^[0-9]+:[A-Za-z0-9_-]{30,}$ ]] || die "that does not look like a bot token (expected digits:letters)"
  CHAT=""
fi
if [ -z "$CHAT" ]; then
  echo "Open your bot in Telegram and send it any message (for example: hi). Then press Enter here."
  ask "" >/dev/null
  CHAT="$(TELEGRAM_BOT_TOKEN="$TOKEN" "$APP_DIR/.venv/bin/atis-live" telegram-chat-id | sed -n 's/^TELEGRAM_CHAT_ID=\([-0-9]*\).*/\1/p' | head -1 || true)"
  [ -n "$CHAT" ] || CHAT="$(ask 'Could not find the chat automatically. Enter your chat id: ')"
  [[ "$CHAT" =~ ^-?[0-9]+$ ]] || die "chat id must be a number"
fi
LIVE_ARGS="$(env_get ATIS_LIVE_ARGS)"
LIVE_ARGS="${LIVE_ARGS:---symbols NIFTY,BANKNIFTY}"
umask 027
cat > "$ENV_FILE" <<EOF
# ATIS secrets and options - readable by root and the atis service user only.
TELEGRAM_BOT_TOKEN=$TOKEN
TELEGRAM_CHAT_ID=$CHAT
# Extra atis-live options, e.g. --capital 500000 --risk-pct 1 --disable B1,C2
ATIS_LIVE_ARGS=$LIVE_ARGS
PYTHONUNBUFFERED=1
EOF
chown root:atis "$ENV_FILE" && chmod 640 "$ENV_FILE"
umask 022
unset TOKEN

UI_USER="atis"
if [ -s "$CADDY_AUTH_FILE" ] && [ "$(ask 'A console password is already set. Change it? [y/N] ')" != y ]; then
  UI_USER="$(cut -d' ' -f1 "$CADDY_AUTH_FILE")"
else
  UI_USER="$(ask 'Console login user name [atis]: ')"; UI_USER="${UI_USER:-atis}"
  [[ "$UI_USER" =~ ^[A-Za-z0-9._-]+$ ]] || die "user name: letters, digits, . _ - only"
  while :; do
    PW1="$(ask_secret 'Console password (min 10 characters): ')"
    PW2="$(ask_secret 'Repeat password: ')"
    [ "$PW1" = "$PW2" ] && [ "${#PW1}" -ge 10 ] && break
    warn "passwords differ or are shorter than 10 characters - try again"
  done
  HASH="$(printf '%s\n' "$PW1" | caddy hash-password)"
  unset PW1 PW2
  printf '%s %s\n' "$UI_USER" "$HASH" > "$CADDY_AUTH_FILE"
  chown root:caddy "$CADDY_AUTH_FILE" && chmod 640 "$CADDY_AUTH_FILE"
fi

# ---------------------------------------------------------------- services
say "systemd services"
VENV="$APP_DIR/.venv/bin"
cat > /etc/systemd/system/atis-console.service <<EOF
[Unit]
Description=ATIS web console (localhost only; Caddy adds HTTPS and login)
After=network-online.target
Wants=network-online.target

[Service]
User=atis
Group=atis
WorkingDirectory=$DATA_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/atis-console --host 127.0.0.1 --port $PORT --settings $DATA_DIR/atis_console.json --journal $DATA_DIR/atis_journal.json --live-dir $DATA_DIR/data/live
Restart=always
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR

[Install]
WantedBy=multi-user.target
EOF

cat > /etc/systemd/system/atis-live.service <<EOF
[Unit]
Description=ATIS live Telegram alerts for today's session (alerts only, no orders)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=atis
Group=atis
WorkingDirectory=$DATA_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV/atis-live run --state-dir $DATA_DIR/data/live --cache $DATA_DIR/data/upstox \$ATIS_LIVE_ARGS
Restart=on-failure
RestartSec=60
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR
EOF

cat > /etc/systemd/system/atis-live.timer <<EOF
[Unit]
Description=Start ATIS live alerts before the NSE open on weekdays

[Timer]
OnCalendar=Mon..Fri *-*-* 08:55:00 Asia/Kolkata
Persistent=true
Unit=atis-live.service

[Install]
WantedBy=timers.target
EOF

ln -sf "$APP_DIR/deploy/oracle/update.sh" /usr/local/bin/atis-update
systemctl daemon-reload
systemctl enable --now atis-console.service atis-live.timer >/dev/null
systemctl restart atis-console.service

# ---------------------------------------------------------------- HTTPS
say "HTTPS address"
PUBLIC_IP="${ATIS_PUBLIC_IP:-$(curl -fsS4 --max-time 10 https://api.ipify.org || curl -fsS4 --max-time 10 https://ifconfig.me || true)}"
[[ "$PUBLIC_IP" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || PUBLIC_IP="$(ask 'Could not detect the public IP. Enter it: ')"
DOMAIN="${ATIS_DOMAIN:-${PUBLIC_IP//./-}.sslip.io}"
cat > /etc/caddy/Caddyfile <<EOF
# ATIS console: HTTPS (automatic certificate) + login in front of the localhost-only console.
$DOMAIN {
	encode gzip
	basic_auth {
		import $CADDY_AUTH_FILE
	}
	reverse_proxy 127.0.0.1:$PORT
	header {
		Strict-Transport-Security "max-age=31536000"
		X-Content-Type-Options nosniff
		X-Frame-Options DENY
		Referrer-Policy no-referrer
	}
}
EOF
caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null
systemctl enable caddy >/dev/null 2>&1 || true
systemctl reload-or-restart caddy

say "VM firewall: allow 80 and 443"
for port in 80 443; do
  if ! iptables -C INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT 2>/dev/null; then
    reject="$(iptables -L INPUT --line-numbers -n | awk '$2 == "REJECT" {print $1; exit}')"
    if [ -n "$reject" ]; then
      iptables -I INPUT "$reject" -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    else
      iptables -A INPUT -p tcp -m state --state NEW --dport "$port" -j ACCEPT
    fi
  fi
done
netfilter-persistent save >/dev/null 2>&1 || true
if command -v ufw >/dev/null && ufw status | grep -q active; then ufw allow 80/tcp >/dev/null; ufw allow 443/tcp >/dev/null; fi

# ---------------------------------------------------------------- checks
say "Checks"
sleep 2
curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null && echo "console: running" || warn "console did not answer - see: journalctl -u atis-console -n 50"
sudo -u atis env PYTHONPATH= "$VENV/python" - <<'EOF' || warn "market data check failed - alerts may not work; see the error above"
from datetime import date, timedelta
from pathlib import Path
from atis.playbook.upstox import fetch_index_1m
bars = fetch_index_1m("NIFTY", date.today() - timedelta(days=7), date.today() - timedelta(days=1), Path("/var/lib/atis/data/upstox"))
print(f"market data: ok ({len(bars)} NIFTY 1-minute bars for the last week)")
EOF
TELEGRAM_BOT_TOKEN="$(env_get TELEGRAM_BOT_TOKEN)" TELEGRAM_CHAT_ID="$(env_get TELEGRAM_CHAT_ID)" \
  "$VENV/atis-live" telegram-test || warn "Telegram test failed - check the token and that you messaged the bot"

cat <<EOF

$(printf '\033[1;32m')ATIS is set up.$(printf '\033[0m')

  Console   : https://$DOMAIN   (user: $UI_USER)
              The first visit can take up to a minute while the HTTPS certificate is issued.
              If it never loads, open ports 80 and 443 in the Oracle security list (see the guide).
  Alerts    : start at 08:55 IST Monday-Friday, Telegram messages until 15:30, day summary at 15:31.
  Next run  : $(systemctl list-timers atis-live.timer --no-legend | awk '{print $1, $2, $3, $4}')

  Useful commands
    systemctl status atis-live atis-console    service state
    journalctl -u atis-live -f                 today's live log
    sudo atis-update                           pull the latest code and restart
    sudo nano $ENV_FILE                        change options, then: sudo systemctl restart atis-console
EOF
