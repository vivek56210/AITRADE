# Run ATIS on an Oracle Cloud Always Free VM

What you get when you're done:

- **Telegram alerts** every trading day, starting automatically at 08:55 IST (Mon–Fri):
  - a pre-market plan per symbol
  - each setup as it triggers
  - a day summary at 15:31
- **The console** at `https://<your-ip>.sslip.io`, behind a password, from any browser or phone. The
  **Live alerts** page shows:
  - whether the runner is alive
  - today's chart with levels and signals
  - the paper-trade journal, with results by setup and by day
- **Alerts only.** Nothing on the VM can place an order, and no broker credentials are stored there.

Total time is about 30 minutes, mostly in the Oracle sign-up. You only need a browser: every
command runs in Oracle **Cloud Shell**.

## What you need

| Item | Where it comes from |
|---|---|
| Oracle Cloud account | [signup.oracle.com](https://signup.oracle.com/) — needs a card for identity verification (a small temporary hold, then refunded) |
| Telegram bot token | @BotFather in Telegram (step 4) — you paste it **only into the VM**, never into chat or email |
| A console password | You choose it during setup (10+ characters) |

## 1. Create the account

1. Sign up at [signup.oracle.com](https://signup.oracle.com/).
2. For **Home Region** pick **India South (Hyderabad)** or **India West (Mumbai)**.
   - Always Free compute exists only in your home region.
   - You cannot change the home region later.
3. Wait for the "account is ready" email (usually minutes), then sign in at
   [cloud.oracle.com](https://cloud.oracle.com/).

## 2. Make an SSH key in Cloud Shell

In the console, click the **Cloud Shell** icon (`>_`, top right) and run:

```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519 && cat ~/.ssh/id_ed25519.pub
```

Copy the printed line that starts with `ssh-ed25519`. Keep Cloud Shell open.

## 3. Create the VM

**Menu → Compute → Instances → Create instance**:

| Field | Value |
|---|---|
| Name | `atis` |
| Image | **Change image → Ubuntu → Canonical Ubuntu 24.04** (the normal one, not "Minimal") |
| Shape | **Change shape → Ampere → VM.Standard.A1.Flex**, 1 OCPU, 6 GB memory (all Always Free) |
| Networking | Create a new virtual cloud network and a **public** subnet; **Assign a public IPv4 address: Yes** |
| SSH keys | **Paste public keys** → paste the `ssh-ed25519 …` line from step 2 |
| Boot volume | Leave the default |

Click **Create** and wait until the state is **Running**. Copy the **Public IP address**.

> **"Out of capacity" for A1?** Free Ampere capacity is often busy. You have three options:
> - Retry later.
> - Pick another availability domain.
> - Use shape **VM.Standard.E2.1.Micro** (AMD, also Always Free, 1 GB RAM). The setup adds swap
>   for it automatically.

## 4. Create the Telegram bot

1. In Telegram, open **@BotFather** and send `/newbot`.
2. Give it a name, then a username ending in `bot`.
3. BotFather replies with a **token** like `123456789:AA…`. Keep it private.
4. Open your new bot, press **Start** and send it `hi`. The setup uses this message to find your
   chat id.

## 5. Open the web ports in Oracle's firewall

On the instance page, click the **subnet** link (under Primary VNIC), then go to **Security
Lists** (on some screens, **Security**) and open **Default Security List**. Click **Add Ingress
Rules** and add two rules:

| Source CIDR | IP Protocol | Destination port |
|---|---|---|
| `0.0.0.0/0` | TCP | `80` |
| `0.0.0.0/0` | TCP | `443` |

Port 80 is needed once so the free HTTPS certificate can be issued. After that it only redirects
to HTTPS.

## 6. Run the setup

In Cloud Shell:

```bash
ssh ubuntu@<PUBLIC-IP>
```

Answer `yes` to the fingerprint question. Then, on the VM:

```bash
curl -fsSL https://raw.githubusercontent.com/vivek56210/AITRADE/claude/sweet-dirac-l8xhkg/deploy/oracle/setup.sh -o atis-setup.sh
sudo bash atis-setup.sh
```

The setup takes 5–10 minutes and asks for:

1. **Bot token.** Paste it; the input is hidden.
2. **Press Enter.** Do this after you have sent `hi` to the bot. It finds your chat id automatically.
3. **Console user name and password.**

At the end it prints your URL, such as `https://140-238-1-2.sslip.io`. You should also get an
**"ATIS test message"** in Telegram. Open the URL and log in; you land on **Live alerts**. It stays
empty until Monday's session starts.

## What happens on a trading day

| Time (IST) | What you get |
|---|---|
| 08:55 | The runner starts; the VM may sleep until 09:05 |
| ~09:05 | Telegram: a plan for NIFTY and BANKNIFTY, then "ATIS live started" |
| 09:15–15:30 | Telegram: each setup as it fires (entry, stop, targets, option legs, lots), with its **grade (A+ / B)** and the reasons, marked *paper trade only*. C-grade signals are journaled but not sent. The Live alerts page refreshes every 15 s |
| A loss limit is hit | Telegram, once: the daily (−3R) or weekly (−6R) loss limit is reached. No new alerts until it resets |
| If the feed stalls | Telegram: "no new data since …", then "data resumed" |
| 15:31 | Telegram: day summary with the paper result per signal. It's also added to the journal on the Live alerts page |

The runner skips weekends and NSE holidays by itself. Holidays are read from the exchange's
option expiry calendar. If it crashes, systemd restarts it within a minute, and it does not resend
alerts it already sent.

## Everyday commands (on the VM)

```bash
systemctl status atis-live atis-console     # is everything running?
journalctl -u atis-live -f                  # watch today's log live
systemctl list-timers atis-live.timer       # when is the next run?
sudo atis-update                            # pull the latest code, rebuild, restart
sudo nano /etc/atis/atis.env                # change options (below)
```

Options go in `ATIS_LIVE_ARGS` in `/etc/atis/atis.env` and apply from the next morning:

```
ATIS_LIVE_ARGS="--symbols NIFTY,BANKNIFTY --capital 500000 --risk-pct 1 --disable B1,C2"
```

To change the token or password, run `sudo bash atis-setup.sh` again. It keeps everything else.
Add `--min-grade A+` to `ATIS_LIVE_ARGS` to receive only A+ signals. Out of sample, A+ did not beat
B, so the default is B.

## Optional: record real NSE order flow (Dhan)

This builds a history of NIFTY/BANKNIFTY futures trades split into buyer- and seller-initiated
volume, which can't be downloaded. It needs your **Dhan client id, an access token and an active
Dhan Data API plan**. It's read-only market data; no orders.

```bash
sudo bash /opt/atis/deploy/oracle/enable-recorder.sh   # once: client id + token, installs the 08:57 IST weekday timer
sudo atis-dhan-token                                   # each morning before 08:57: paste a fresh token
```

Dhan access tokens currently last about 24 hours. If the token has expired or the data plan
lapses, the recorder stops and tells you on Telegram. Data lands in `/var/lib/atis/data/flow/`.

## Keeping it free

- Always Free resources do not expire. The 30-day trial credit expires, but the VM keeps running.
- On a free-tier account, Oracle may **reclaim an idle Always Free instance**: roughly, under 20%
  CPU for 7 days. ATIS uses very little CPU, so this can apply to you.
- To avoid reclamation, upgrade the account to **Pay As You Go** (Billing → Upgrade). Always Free
  resources stay free; add a budget alert of ₹100 to be safe.
- Without the upgrade, check the URL once a week.

## Troubleshooting

| Symptom | Check |
|---|---|
| URL does not load at all | Step 5 rules are present; `sudo iptables -S INPUT` shows ports 80 and 443; `sudo journalctl -u caddy -n 50` |
| Browser warns about the certificate | Wait a minute after the first start; Caddy logs show the certificate request |
| Login works, page says API unreachable | `systemctl status atis-console`; `journalctl -u atis-console -n 50` |
| No Telegram messages on a trading day | `journalctl -u atis-live -n 100`; test with `sudo -u atis bash -c 'set -a; . /etc/atis/atis.env; /opt/atis/.venv/bin/atis-live telegram-test'` |
| Telegram says "no market data by 09:45" | The Upstox public feed was unreachable from the VM. The log shows the error |
| Want your own domain | Point an A record at the VM, then `sudo ATIS_DOMAIN=atis.example.com bash atis-setup.sh` |

## Security notes

- The console listens only on `127.0.0.1:8765`.
- Caddy is the only public entry point. It serves HTTPS and asks for your password before
  anything is shown.
- Secrets live in `/etc/atis/atis.env`, readable only by root and the `atis` service user.
- The password is stored only as a bcrypt hash, in `/etc/caddy/atis-auth`.
- Services run as the unprivileged `atis` user, with a read-only system and no access to home
  directories.
- No broker (Dhan) credentials are on the VM, and there is no order-placement code.
