#!/usr/bin/env bash
# Install the BTC/ETH trend bot on the VM (run deploy/oracle/setup.sh first).
#
#   sudo bash /opt/atis/deploy/oracle/enable-crypto.sh
#
# Modes:
#   paper   (default) simulated fills at Delta India's live prices; no account, no keys
#   testnet Delta India demo exchange; needs testnet API keys; no real money
#   live    real orders on Delta Exchange India; needs API keys and a typed confirmation
# Installs:
#   atis-crypto-rebalance.timer : 00:05 UTC (05:35 IST) daily - the strategy trades once a day
#   atis-crypto-watch.timer     : hourly at :30 - kill switches (daily loss, drawdown) and heartbeat
# Create the Delta API key with trading permission only - never withdrawal - and, if Delta offers it,
# whitelist only this VM's public IP.
set -euo pipefail

APP_DIR=/opt/atis
DATA_DIR=/var/lib/atis
ENV_FILE=/etc/atis/atis.env

die() { printf '\033[1;31mxx %s\033[0m\n' "$*" >&2; exit 1; }
ask() { local v; read -r -p "$1" v </dev/tty; printf '%s' "$v"; }
ask_secret() { local v; read -r -s -p "$1" v </dev/tty; echo >/dev/tty; printf '%s' "$v"; }
env_get() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -1 | sed 's/^"\(.*\)"$/\1/'; }
env_set() {  # replace or append KEY=VALUE without printing the value
  local tmp; tmp="$(mktemp)"
  grep -v "^$1=" "$ENV_FILE" > "$tmp" || true
  printf '%s=%s\n' "$1" "$2" >> "$tmp"
  cat "$tmp" > "$ENV_FILE"; rm -f "$tmp"
}

[ "$(id -u)" -eq 0 ] || die "run with sudo"
[ -f "$ENV_FILE" ] && [ -x "$APP_DIR/.venv/bin/atis-crypto" ] || die "run deploy/oracle/setup.sh (or sudo atis-update) first"

MODE="$(ask 'Mode - paper, testnet or live [paper]: ')"; MODE="${MODE:-paper}"
case "$MODE" in paper|testnet|live) ;; *) die "mode must be paper, testnet or live" ;; esac

ARGS="--broker $MODE --state-dir $DATA_DIR/data/live"
if [ "$MODE" = paper ]; then
  CAP="$(ask 'Paper starting capital in USD [10000]: ')"; CAP="${CAP:-10000}"
  [[ "$CAP" =~ ^[0-9]+(\.[0-9]+)?$ ]] || die "capital must be a number"
  ARGS="$ARGS --paper-capital $CAP"
else
  echo "Paste the Delta Exchange India API key and secret ($MODE). Input is hidden; stored only in $ENV_FILE."
  KEY="$(ask_secret 'API key: ')"; SECRET="$(ask_secret 'API secret: ')"
  [ -n "$KEY" ] && [ -n "$SECRET" ] || die "key and secret are both required"
  env_set DELTA_API_KEY "$KEY"; env_set DELTA_API_SECRET "$SECRET"
  unset KEY SECRET
  if [ "$MODE" = live ]; then
    cat <<'EOF'

LIVE TRADING places real orders with real money. Read src/docs/12-CRYPTO-STRATEGY.md first:
historically half of all months lost money, the worst drawdown was -20%, and past results do not
guarantee future ones. The bot halts and flattens at -8% in a day or -30% from peak.
EOF
    [ "$(ask 'Type I_ACCEPT_THE_RISK to enable live orders: ')" = I_ACCEPT_THE_RISK ] || die "not confirmed - nothing changed"
    env_set ATIS_CRYPTO_LIVE I_ACCEPT_THE_RISK
  fi
fi
env_set ATIS_CRYPTO_ARGS "\"$ARGS\""
chown root:atis "$ENV_FILE" && chmod 640 "$ENV_FILE"

for job in rebalance watch; do
cat > /etc/systemd/system/atis-crypto-$job.service <<EOF
[Unit]
Description=ATIS crypto trend bot: $job
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
User=atis
Group=atis
WorkingDirectory=$DATA_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/atis-crypto $job \$ATIS_CRYPTO_ARGS
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR
EOF
done

cat > /etc/systemd/system/atis-crypto-rebalance.timer <<EOF
[Unit]
Description=ATIS crypto daily rebalance just after the UTC daily close

[Timer]
OnCalendar=*-*-* 00:05:00 UTC
Persistent=true
Unit=atis-crypto-rebalance.service

[Install]
WantedBy=timers.target
EOF

cat > /etc/systemd/system/atis-crypto-watch.timer <<EOF
[Unit]
Description=ATIS crypto hourly risk watch

[Timer]
OnCalendar=*-*-* *:30:00
Persistent=true
Unit=atis-crypto-watch.service

[Install]
WantedBy=timers.target
EOF

cat > /usr/local/bin/atis-crypto-ctl <<'CTL'
#!/usr/bin/env bash
# atis-crypto as the service user, with the VM's settings: sudo atis-crypto-ctl status|watch|resume|flatten
[ $# -ge 1 ] || { echo "usage: sudo atis-crypto-ctl status|watch|resume|flatten" >&2; exit 2; }
exec sudo -u atis bash -c 'set -a; . /etc/atis/atis.env; set +a; cd /var/lib/atis
exec /opt/atis/.venv/bin/atis-crypto "$1" $ATIS_CRYPTO_ARGS' _ "$1"
CTL
chmod 755 /usr/local/bin/atis-crypto-ctl

systemctl daemon-reload
systemctl enable --now atis-crypto-rebalance.timer atis-crypto-watch.timer >/dev/null
atis-crypto-ctl watch >/dev/null && echo "first risk check: ok" || echo "first risk check failed - see the error above"
echo
echo "Crypto bot enabled ($MODE). The first rebalance runs at the next 00:05 UTC (05:35 IST)."
systemctl list-timers 'atis-crypto-*' --no-legend | awk '{print "  next:", $1, $2, $3, $4, "->", $NF}'
echo "  status        : sudo atis-crypto-ctl status"
echo "  close all     : sudo atis-crypto-ctl flatten"
echo "  after a halt  : sudo atis-crypto-ctl resume"
echo "  pause trading : sudo systemctl disable --now atis-crypto-rebalance.timer   (positions stay open)"
