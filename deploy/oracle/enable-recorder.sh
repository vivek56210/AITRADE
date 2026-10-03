#!/usr/bin/env bash
# Optional: record real NIFTY/BANKNIFTY futures order flow from Dhan's live feed on the VM.
#
#   sudo bash /opt/atis/deploy/oracle/enable-recorder.sh            first time: client id + token, installs the timer
#   sudo atis-dhan-token                                            each morning: paste a fresh access token
#
# Needs an active Dhan Data API plan. Dhan access tokens currently last about 24 hours, so a new one
# must be pasted before 08:57 IST on each day you want to record; when the token has expired the
# recorder stops and says so on Telegram. Read-only market data: no order endpoint is ever called.
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
[ -f "$ENV_FILE" ] && [ -d "$APP_DIR/.venv" ] || die "run deploy/oracle/setup.sh first"

TOKEN_ONLY=0
if [ "${1:-}" = "--token-only" ] || [ "$(basename "$0")" = "atis-dhan-token" ]; then
  TOKEN_ONLY=1
fi

if [ "$TOKEN_ONLY" -eq 0 ]; then
  CID="$(env_get DHAN_CLIENT_ID)"
  NEW="$(ask "Dhan client id${CID:+ [keep $CID]}: ")"
  CID="${NEW:-$CID}"
  [[ "$CID" =~ ^[0-9]+$ ]] || die "the client id is a number (Dhan web -> profile)"
  env_set DHAN_CLIENT_ID "$CID"
fi
echo "Paste a Dhan access token (web.dhan.co -> My Profile -> Access DhanHQ APIs). Input is hidden."
TOKEN="$(ask_secret 'Access token: ')"
[ -n "$TOKEN" ] && [[ ! "$TOKEN" =~ [[:space:]] ]] || die "empty or malformed token"
env_set DHAN_ACCESS_TOKEN "$TOKEN"
unset TOKEN
chown root:atis "$ENV_FILE" && chmod 640 "$ENV_FILE"
echo "token saved to $ENV_FILE"
[ "$TOKEN_ONLY" -eq 1 ] && exit 0

"$APP_DIR/.venv/bin/pip" install -q -e "${APP_DIR}[console,record]"
install -d -o atis -g atis "$DATA_DIR/data/flow" "$DATA_DIR/data/dhan"

cat > /etc/systemd/system/atis-record.service <<EOF
[Unit]
Description=ATIS order-flow recorder: NIFTY/BANKNIFTY futures ticks from Dhan (read-only market data)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=atis
Group=atis
WorkingDirectory=$DATA_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$APP_DIR/.venv/bin/atis-live record --out $DATA_DIR/data/flow --cache $DATA_DIR/data/dhan
Restart=on-failure
RestartSec=60
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true
ReadWritePaths=$DATA_DIR
EOF

cat > /etc/systemd/system/atis-record.timer <<EOF
[Unit]
Description=Start the ATIS order-flow recorder before the NSE open on weekdays

[Timer]
OnCalendar=Mon..Fri *-*-* 08:57:00 Asia/Kolkata
Persistent=true
Unit=atis-record.service

[Install]
WantedBy=timers.target
EOF

ln -sf "$APP_DIR/deploy/oracle/enable-recorder.sh" /usr/local/bin/atis-dhan-token
systemctl daemon-reload
systemctl enable --now atis-record.timer >/dev/null
echo
echo "Recorder enabled: next run $(systemctl list-timers atis-record.timer --no-legend | awk '{print $1, $2, $3, $4}')"
echo "Data: $DATA_DIR/data/flow/<SYMBOL>/<date>.csv (1-minute bars with buy/sell volume) and -ticks.csv.gz"
echo "Each morning before 08:57 IST: sudo atis-dhan-token   (Dhan tokens last about 24 hours)"
