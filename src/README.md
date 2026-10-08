# ATIS — Autonomous Trading Intelligence Platform

> **Status: DESIGN PHASE.** These documents are the complete architecture and phase plan, written
> for review. The only code so far is the volume-profile playbook detectors (`src/atis/playbook`,
> see [Code](#code-volume-profile-playbook) below) — recommendation mode only, all setups CANDIDATE.
>
> Doc set version: **v0.2-draft** (validation pass applied — see [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md)) · Date: 2026-07-11 · Markets: Indian Equities, Indian F&O, Crypto, Commodities (MCX)

---

## What ATIS is

ATIS is an institutional-grade trading intelligence platform that continuously observes markets,
builds an evidence-based model of current conditions, evaluates opportunities against measured
statistical edge, manages risk as an independent first-class function, executes under graduated
autonomy (recommend → assisted → autonomous), and learns from every outcome — including trades it
recommended but did not take.

It is designed to behave like a professional trading **organization** (research desk, portfolio
manager, risk desk, execution desk, compliance) — not like a trading bot.

**The default action is NO TRADE.** Everything in this design exists to make the exceptions to
that default safe, explainable, and positive-expectancy.

## What ATIS is not

- Not an indicator-crossover bot or a signal-selling service
- Not an HFT / market-making system (mid-frequency by design; see [00-VISION §6](docs/00-VISION.md))
- Not a win-rate or trade-count maximizer
- Not a black box — every decision carries a full, auditable evidence trail

---

## Document map (review order)

| # | Document | Covers |
|---|----------|--------|
| 0 | [docs/00-VISION.md](docs/00-VISION.md) | Mission, philosophy, priority stack, target markets, operating modes, success metrics, constraints, guiding principles |
| 1 | [docs/01-ARCHITECTURE.md](docs/01-ARCHITECTURE.md) | High-level architecture, planes, microservice decomposition, event backbone, canonical objects, storage, tech stack, security, observability, failure/recovery, scalability |
| 2 | [docs/02-AGENTS.md](docs/02-AGENTS.md) | Multi-agent roster and contracts, Trade Committee protocol, Confidence Engine math, LLM usage policy, agent lifecycle and degradation rules |
| 3 | [docs/03-DATA-PLATFORM.md](docs/03-DATA-PLATFORM.md) | Source catalog per market, ingestion, canonical schemas, Data Quality Engine, stream processing, feature store, knowledge graph, institutional memory, history/backfill |
| 4 | [docs/04-STRATEGY-ENGINE.md](docs/04-STRATEGY-ENGINE.md) | Market-knowledge detector specs (profile, structure, liquidity, order flow, SMC, Wyckoff, VWAP, options), regime engine, strategy framework and lifecycle, opportunity ranking, trade decision engine, dynamic trade management, backtesting and statistical validation |
| 5 | [docs/05-RISK-PORTFOLIO.md](docs/05-RISK-PORTFOLIO.md) | Independent risk kernel, pre-trade checks, position sizing, portfolio intelligence, capital allocation, drawdown governance, market health, VaR/stress testing, kill switches |
| 6 | [docs/06-LEARNING-ENGINE.md](docs/06-LEARNING-ENGINE.md) | Outcome capture, attribution, trade review, self-reflection, drift detection, model lifecycle, strategy evolution, research engine, digital twin and simulation |
| 7 | [docs/07-EXECUTION-ENGINE.md](docs/07-EXECUTION-ENGINE.md) | Operating modes, order lifecycle, execution algos, broker adapter layer, safety pipeline, live trade management, TCA, reconciliation, failure recovery |
| 8 | [docs/08-IMPLEMENTATION-ROADMAP.md](docs/08-IMPLEMENTATION-ROADMAP.md) | Phase-wise roadmap with exit gates, testing strategy, governance and audit framework, DR plan, cost bands, operating rituals, risk register |
| 9 | [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md) | **The validation audit**: 21 internal findings (3 HIGH), externally verified July-2026 facts with sources (SEBI algo framework, F&O regime, crypto tax/venues, broker APIs, data vendors), rejected alternatives, residual risks, v0.1→v0.2 change log |
| 10 | [docs/10-VOLUME-PROFILE-PLAYBOOK.md](docs/10-VOLUME-PROFILE-PLAYBOOK.md) | Market/volume-profile setups for NIFTY & BANKNIFTY options (Oct 2026): setups A1–A5, B1–B4, C1–C3, D1–D2, India expiry/lot/STT/CAS rules, risk rules — the spec for `src/atis/playbook` |

*Note: `05-RISK-PORTFOLIO.md` was added beyond the originally listed six phase docs — risk is an
independent function in institutional design and warrants its own specification.*

## Master-prompt deliverable coverage

| Deliverable | Where |
|---|---|
| 1. High-level architecture | 01 §1–3 |
| 2. Microservice decomposition | 01 §3 |
| 3. AI agent collaboration | 02 §3–5 |
| 4. Data pipelines | 03 §3–6 |
| 5. Event-driven workflows | 01 §4, 02 §4 |
| 6. Knowledge graph design | 03 §8 |
| 7. Feature store | 03 §7 |
| 8. Model registry | 06 §7 |
| 9. Backtesting framework | 04 §9 |
| 10. Research framework | 06 §9 |
| 11. Strategy lifecycle | 04 §10 |
| 12. Continuous learning workflow | 06 §1–6 |
| 13. Self-improvement workflow | 06 §5, §8 |
| 14. Trade decision workflow | 04 §7, 02 §4 |
| 15. Portfolio management workflow | 05 §5–6 |
| 16. Risk management framework | 05 (entire) |
| 17. Broker integration architecture | 07 §4–5 |
| 18. Monitoring & observability | 01 §12, 07 §11 |
| 19. Security architecture | 01 §11 |
| 20. Phase-wise implementation roadmap | 08 §2–6 |
| 21. Technology stack recommendations | 01 §9 |
| 22. Scalability plan | 01 §10 |
| 23. Testing strategy | 08 §8 |
| 24. Disaster recovery plan | 08 §11, 01 §13 |
| 25. Governance & audit framework | 08 §10, 02 §3 (Governance Agent), 05 §11 |

## Conventions used in these documents

- **MUST / SHOULD / MAY** carry RFC-2119 meaning.
- **(P)** marks a *proposed default* number awaiting your review — every threshold, limit, and
  target so marked is configurable and stored in the versioned limits registry, never hardcoded.
- **R** is the risk unit: the rupee amount risked between entry and stop on one trade.
- **Modes**: P1 = Recommendation, P2 = Assisted execution, P3 = Constrained autonomy.
- **Criticality tiers**: C0 = must never be wrong (risk, orders); C1 = trading halts without it;
  C2 = quality degrades without it; C3 = offline/batch.
- Every doc ends with **Open questions for review** — decisions only you can make.

## Glossary

| Term | Meaning |
|---|---|
| Evidence | Typed, calibrated, provenance-carrying claim published by an agent |
| MarketState | Continuously updated per-instrument market understanding object |
| TradePlan | Fully specified trade proposal (entry/stop/targets/size/reasoning) |
| DecisionRecord | Immutable, hash-chained record of a decision and all its inputs |
| POC / VAH / VAL / IB | Point of Control, Value Area High/Low, Initial Balance (market profile) |
| HVN / LVN | High / Low Volume Node (volume profile) |
| BOS / CHOCH | Break of Structure / Change of Character (market structure) |
| FVG | Fair Value Gap (3-bar displacement gap) |
| CVD | Cumulative Volume Delta |
| OI / PCR / IVR / IVP / GEX | Open Interest, Put-Call Ratio, IV Rank, IV Percentile, Gamma Exposure |
| MWPL / SPAN | Market-Wide Position Limit, exchange margin methodology (F&O) |
| EV / PF / ECE | Expected Value, Profit Factor, Expected Calibration Error |
| DSR / PSR | Deflated / Probabilistic Sharpe Ratio (multiple-testing-aware) |
| WFO | Walk-Forward Optimization |
| BOCPD / HMM | Bayesian Online Change-Point Detection, Hidden Markov Model |
| PIT | Point-In-Time correctness (no lookahead in features) |
| TCA / OMS | Transaction Cost Analysis, Order Management System |
| Digital Twin | Same production engine driven by replayed/simulated events |
| Dead-man switch | Broker-side protection that survives total platform failure |

## Change log

- **v0.1** (2026-07-11) — initial full design set (docs 00–08).
- **v0.2** (2026-07-11) — adversarial validation pass: internal audit (21 findings, 3 HIGH —
  stock-F&O physical-delivery guard, equity short-selling constraint, statistically-sound
  calibration gates) + external fact verification against July-2026 primary sources (SEBI algo
  framework mechanics incl. the 10-orders/sec threshold, verified expiry/lot/margin regime,
  crypto derivatives-first tax posture on FIU venues, broker API and data-vendor realities).
  Full findings, sources, and per-doc changes in [docs/09-VALIDATION-REVIEW.md](docs/09-VALIDATION-REVIEW.md).

## Code: volume-profile playbook

`src/atis/playbook` implements [docs/10](docs/10-VOLUME-PROFILE-PLAYBOOK.md) in dependency-free
Python (3.11+). It reads **current-month index futures bars** (spot has no volume), builds the
prior-day and developing volume/TPO profile (POC, VAH/VAL, HVN/LVN, IB, tails, poor extremes,
single prints, composite balance), classifies open type and day type, and runs the setup detectors
bar by bar. Each signal carries the futures entry/stop/targets, the option structure (ATM/ITM buy,
debit spread, credit spread, iron condor/fly with strikes beyond profile levels), lot sizing from the
risk rules, an exit-by time, and the reasons any setup was skipped. It never places orders.

```bash
pip install -e '.[dev]' && pytest
python -m atis.playbook demo --days 30 --backtest           # synthetic data
python -m atis.playbook run --csv nifty_fut_1m.csv --symbol NIFTY --iv 0.13 --basis 45 --backtest
```

**Real data (no account needed):** `--upstox` downloads 1-minute NIFTY / BANKNIFTY index bars from
Upstox's public historical API (from 2022-01-01), cached per month under `data/upstox/`:

```bash
python -m atis.playbook run --upstox --symbol BANKNIFTY --from 2025-10-01 --to 2026-10-01 --backtest
python -m atis.playbook fetch --symbol NIFTY --from 2025-10-01 --out nifty_1m.csv   # just save a CSV
```

Index bars carry no volume, so every minute is weighted equally (a time-at-price / TPO profile) and
order-flow confirmations read `n/a`. Exchange holidays are inferred from gaps in the data and short
special sessions are dropped. In the console, set **Settings → Data source = upstox** with a date range.

**Futures with volume and OI (Dhan account):** `--dhan` downloads 1-minute front-month NIFTY / BANKNIFTY
futures from DhanHQ v2 (`POST /v2/charts/intraday`), cached per contract-month under `data/dhan/`. It is
read-only: only `/v2/profile` and `/v2/charts/intraday` can be called. Credentials come from
`DHAN_CLIENT_ID` and `DHAN_ACCESS_TOKEN` in the environment (tokens last 24 hours).

```bash
python -m atis.playbook dhan-check --symbol NIFTY      # token check + how far back each contract goes
python -m atis.playbook run --dhan --symbol NIFTY --from 2026-07-01 --backtest
python -m atis.playbook fetch --source dhan --symbol BANKNIFTY --from 2026-07-01 --out bn_fut_1m.csv
```

Security IDs come from Dhan's public scrip master, which lists only live contracts; every contract seen is
kept in `data/dhan/contracts.csv`. Contracts are joined at expiry (the expiring contract is front through its
expiry day), and each roll gap — measured at the last minute both contracts traded — is added to earlier
bars so profile levels line up across rolls (`--raw-roll` to disable). **Dhan serves intraday history only
for active contracts**, so a series reaches back only as far as the oldest listed contract's data.
When the true front month isn't served, the next contract stands in. Months downloaded while a contract
is active stay cached, so history grows from the first download onward.
Console: **Settings → Data source = dhan**.

Measured with `dhan-check` on 2026-10-03 (expired contracts are not in the scrip master at all):

| Contract | Expiry | 1-minute data served |
|---|---|---|
| NIFTY-Oct2026-FUT | 2026-10-27 | 2026-07-29 → 2026-10-01 |
| NIFTY-Nov2026-FUT | 2026-11-23 | 2026-08-26 → 2026-10-01 |
| NIFTY-Dec2026-FUT | 2026-12-29 | 2026-09-30 → 2026-10-01 |

So a one-year futures backtest is not possible from Dhan today; the futures window starts 2026-07-29.
Upstox spot baselines (R before costs, 3 warm-up sessions; reproduced from a fresh download on 2026-10-03),
for comparison with futures runs:

| Spot (Upstox) | Window | Signals | Total R | Win | PF | Max DD |
|---|---|---|---|---|---|---|
| NIFTY | 2025-10-07 → 2026-10-01 | 363 | +7.41 | 57% | 1.05 | −23.5R |
| BANKNIFTY | 2025-10-07 → 2026-10-01 | 339 | +26.21 | 60% | 1.20 | −9.3R |
| NIFTY | 2026-08-03 → 2026-10-01 | 63 | −0.70 | 59% | 0.97 | −7.8R |
| BANKNIFTY | 2026-08-03 → 2026-10-01 | 56 | −2.88 | 57% | 0.87 | −6.6R |

Same window on Dhan futures (`run --dhan --from 2026-07-29 --to 2026-10-01`, back-adjusted, 43 sessions):

| Futures (Dhan) | Signals | Total R | Win | PF | Max DD | vs spot, same window |
|---|---|---|---|---|---|---|
| NIFTY | 54 | −2.61 | 52% | 0.89 | −8.0R | −1.9R |
| BANKNIFTY | 57 | −8.94 | 42% | 0.65 | −15.2R | −6.1R |

Read this as a data-quality result, not a verdict on futures profiles. Because the Sep contract has expired,
every day up to 2026-09-29 comes from the **next-month** Oct contract, which barely trades then. Share of
session minutes with zero volume:

| | Aug (next month) | Sep 1–29 (next month) | Sep 30 (front month) |
|---|---|---|---|
| NIFTY | 23.7% | 3.9% | 0.0% |
| BANKNIFTY | 54.8% | 24.0% | 0.0% |

The worst underperformance is where the profile is built from the sparsest prints: BANKNIFTY in August
(−9.6R). With ~55 trades a side, the NIFTY difference is within noise. A meaningful spot-vs-futures
comparison needs front-month history. That builds up in the cache from now on: each month is saved while
its contract is still active, and Dhan keeps no intraday history after expiry.

Front-month only, 2026-09-30 as history and 2026-10-01 traded (`--from 2026-09-30 --warmup 1 --details`).
This is one session, so it is an anecdote, not evidence:

| 2026-10-01 | Futures (front month) | Spot |
|---|---|---|
| NIFTY | +2.50R, 1 trade: A3 short | −1.72R, 3 trades: A2 short −1, B3 long −1, A3 short +0.28 |
| BANKNIFTY | +1.08R, 3 trades: B2 long +0.46, B3 short +1.13, A3 short −0.51 | +0.78R: B3 short; C1 condor broke |

The difference is in which setups fire. Futures profiles are weighted by traded volume, spot profiles by
time, so the prior-day value area moves. NIFTY's 2026-09-30 value area was ~170 points wide on futures
vs ~95 on spot, so the early move that spot read as a test of the prior low (A2, −1R) sat mid-value on
futures and was skipped. BANKNIFTY opened inside value on spot (condor) but below value on futures (80%
rule long). Two of the three BANKNIFTY futures signals sized to 0 lots at 1% risk; the backtest still
scores them in R. Front-month bars had no zero-volume minutes.

CSV columns: `timestamp,open,high,low,close,volume[,buy_volume,sell_volume]` (IST). Without
buy/sell volume, order flow is estimated with the tick rule and delta-divergence confirmation is
reported as `n/a`. Without `--iv`, option premiums are not priced and sizing falls back to an
assumed delta. The backtest scores futures R-multiples and condor containment — **not option P&L**.
Every threshold lives in `config.py` as a proposed default (P).

### Out-of-sample check, loss limits and grading

**Out of sample, the playbook has no edge on NSE spot.** These numbers include the loss limits
below and are R before costs:

| Spot (Upstox) | 2025-10 → 2026-10 (the window above) | **2022-01 → 2025-09 (out of sample)** |
|---|---|---|
| NIFTY | 362 trades, +6.1R, PF 1.04 | **1,388 trades, −0.5R, PF 1.00** |
| BANKNIFTY | 339 trades, +26.2R, PF 1.20 | **1,384 trades, −68.8R, PF 0.88** |

The positive year was the window, not a durable edge. Only B3 (failed IB breakout) is positive in
every window on both indices, at +0.003 to +0.21R per trade.

**Loss limits.** Implemented in `trade.py` and the engine.

- `TradeState` is now the single implementation of how a trade plays out. The backtest replays
  it, and the engine updates it bar by bar.
- That gives realized R during the day, recorded in a `RiskLedger`.
- New trades stop once today's loss reaches `daily_loss_limit / risk_per_trade` (3R), or this
  week's reaches `weekly_loss_limit / risk_per_trade` (6R).
- The live runner shares one ledger across NIFTY and BANKNIFTY, so the limits are account-wide.
  It seeds the ledger from this week's paper journal and announces a hit limit once on Telegram.

**Grading** (`grading.py`). Every signal gets A+ / B / C from rules fixed before testing:

| Factor | Score |
|---|---|
| Entry or stop at a pre-market map level: prior day, single prints, composite balance, prior-week value, naked POCs | +1 |
| Structure confirmations | ±1 |
| Real order flow (estimated flow scores 0) | ±1 |
| With / against value migration | ±1 |
| VWAP side, for initiative trades | ±1 |
| First target ≥ 1.5R away (+1) or < 1R away (−1) | ±1 |
| Fees above 0.2R | −1 |

The pre-market plan and Telegram plan also show the prior-week value area and naked POCs.

| R per trade by grade | NIFTY 2022–25 | BANKNIFTY 2022–25 | NIFTY 2025–26 | BANKNIFTY 2025–26 |
|---|---|---|---|---|
| A+ | +0.001 (716) | −0.051 (748) | +0.050 (204) | −0.004 (183) |
| B | +0.019 (617) | −0.037 (594) | −0.011 (153) | +0.197 (143) |
| C | −0.240 (55) | −0.215 (42) | −0.482 (5) | −0.090 (13) |

A+ does not beat B out of sample. C is negative in all four samples, so `atis-live` sends grade B
and above (`--min-grade`). Every signal is still journaled with its grade.

### Operator console (UI)

`src/atis/console` (FastAPI) runs the engine in a background **replay worker** and serves the
React + TypeScript UI from `console-ui/` (the documented ops-console stack, 01 §9):

| Page | What it shows / does |
|---|---|
| Live alerts | The Telegram runner's status and heartbeat, today's index chart with levels and signals, the paper-trade journal with results by setup and by day (reads `data/live`, written by `atis-live`) |
| Dashboard | Engine state, replay progress, today's structure (open type, IB, day type, dPOC, VA), live mini-chart, recent signals, activity feed, plan warnings, last backtest equity |
| Market | Futures candles with prior VA/POC/H/L, IB, dPOC, HVN/LVN, single prints, composite balance overlays; today's and prior volume profile; signal markers; pre-market plan; skip reasons; any past session |
| Setups | All 13 setups with rules, today's status (fired / skipped + reason / watching), counts, backtest stats, and an on/off switch that applies on the next bar |
| Signals | Every signal with futures plan, option legs, sizing, confirmations; mark **taken / ignored** with a note (persisted journal); CSV export |
| Backtest | Run a backtest as a background job (progress, cancel), equity curve, per-setup table, trade list |
| Monitor | Replay worker health (thread, heartbeat, bars/s, position), background jobs, process/threads/memory, live event log with level filter |
| Settings | Every data, context, risk, playbook and session-time parameter with defaults and validation, persisted to `atis_console.json`; "live" fields apply at once, the rest on Reset |

Controls in the top bar: Start / Pause / Resume, Step 1 bar, +30 bars, Stop, Reset (reload data with
current settings), replay speed.

```bash
pip install -e '.[console]'
cd console-ui && npm install && npm run build && cd ..   # builds into src/atis/console/static
atis-console                                              # http://127.0.0.1:8765
```

For UI development run `atis-console` and `npm run dev` in `console-ui/` (Vite proxies `/api`).
The console binds to 127.0.0.1 and has no login, so do not expose it on a network directly; the
Oracle setup below puts HTTPS and a password in front of it.

### Crypto backtest (Delta Exchange India BTC/ETH perpetuals)

```bash
atis-playbook crypto --from 2024-10-01 --to 2026-09-30                 # BTCUSD + ETHUSD, all session definitions
atis-playbook crypto --symbols ETHUSD --session ny --from 2025-01-01   # one coin, one session
```

How the backtest is set up:

- **Data.** 1-minute candles with real traded volume come from Delta's public API (no key needed)
  and are cached per month in `data/delta`.
- **Sessions.** Crypto never closes, so "the session" is a choice. Three are tested, each with the
  playbook's NSE clock scaled to fit (`scaled_session_times`; the IB stays one hour):
  - `utc`: a 24-hour day from 00:00 UTC
  - `ny`: US cash hours, 09:30–15:45 New York
  - `ist`: 09:15–15:30 IST, the same hours as NSE
- **Fees.** Each directional trade pays Delta's taker fee on entry and exit, 0.05% + 18% GST per
  side, converted to R. A second scenario uses limit entries (maker fee 0.02%).
- **Calendar.** Every calendar day is a session. NSE expiry-day rules are off.

Results, 2024-10-01 → 2026-09-30, two years, on the perpetual (not option P&L), before funding
and slippage:

| | Trades | Gross R/trade | Fee R/trade | Net R | Net R, limit entries | Condors contained |
|---|---|---|---|---|---|---|
| BTC utc | 1,322 | −0.024 | 0.51 | −711 | −507 | 45/211 |
| BTC ny | 971 | −0.014 | 0.37 | −372 | −265 | 33/112 |
| BTC ist | 969 | +0.002 | 0.68 | −656 | −459 | 33/102 |
| ETH utc | 1,301 | +0.038 | 0.33 | −383 | −253 | 55/245 |
| ETH ny | 1,005 | −0.002 | 0.25 | −252 | −177 | 52/115 |
| ETH ist | 947 | −0.031 | 0.43 | −440 | −317 | 32/101 |

What the results show:

- **No gross edge.** Before fees, every configuration averages between −0.03R and +0.04R per trade,
  which is noise. On NSE spot the same engine made +0.08R per trade on BANKNIFTY and +0.02R on
  NIFTY over its one-year run, also before costs.
- **Fees dominate.** The playbook's 1-minute structural stops are tight relative to price
  (0.2–0.6%). Delta's round-trip fee of about 0.12% of notional therefore costs 0.25–0.68R per
  trade. Every setup is negative after fees in at least one configuration.
- **No setup survives everywhere.** ETH `ny` A1 is +15.5R net over 41 trades and positive in both
  years, but this run covers about 54 setup × configuration combinations, so a couple of positive
  ones are expected by chance.
- **Conclusion.** The NSE playbook does not carry over to crypto as-is. Crypto alerts are not wired
  into `atis-live`.

**Real order flow** (`--source binance`, `binance.py`). Binance's free 1-minute USD-M archives
include taker-buy volume, so every bar gets a true aggressor split. The engine's delta,
cumulative-delta and divergence checks then run on real data, scored with Delta's fees. Two years,
same windows:

| Test | Result |
|---|---|
| Real flow as a confirmation inside the 13 setups | No change: gross is still about 0R per trade in all six configurations. "Flow confirms" beat "flow disagrees" in only 3 of 6 |
| **R1** (`setups/reaction.py`, off by default, `reaction_setups`) | Fades a probe of a pre-market map level once price closes back away from it. With real flow it also needs absorption or a delta divergence at the probe |
| R1 with real flow vs without | Better in 4 of 6 configurations. Best: BTC New York hours, +0.097R/trade gross vs −0.045 |
| R1 after fees | −0.38 to −0.86R per trade: its stops are tight, so fees are a large share of risk |
| R1 on NSE spot (structure only) | −0.053 / −0.066R per trade in 2022–25, about flat in 2025–26 |
| Trailing the stop over the last 30 bars after the first target (`trail_bars`) | Worse in 10 of 12 comparisons |

### Live Telegram alerts (paper trading)

`atis-live` runs the same engine on today's 1-minute NIFTY/BANKNIFTY index candles. It uses the
Upstox public intraday feed, polled every 15 s, and sends each setup to Telegram as it fires. It
never places orders.

```bash
export TELEGRAM_BOT_TOKEN=...   # from @BotFather; never commit or paste it anywhere else
atis-live telegram-chat-id      # after sending your bot a message: prints TELEGRAM_CHAT_ID=...
export TELEGRAM_CHAT_ID=...
atis-live telegram-test         # sends a test message
atis-live run                   # waits for 09:05 IST, alerts until 15:30, day summary, exits
atis-live replay --date 2026-10-01 --dry-run   # a past day through the same code, printed
atis-live summary               # paper results so far
```

The runner skips weekends and holidays. Holidays are inferred from shifted option expiries in the
exchange scrip master. The runner warns on a stale feed, survives restarts without resending, and
writes a snapshot, a heartbeat and a journal to `data/live` for the console's Live alerts page.

**What an alert contains** (`live/messages.py`, `live/optionquotes.py`):

- **What to trade, in option terms.** Each leg's real premium at the signal minute comes from
  Upstox's public instrument list and 1-minute option candles.
- **Option stop and targets.** Each leg's implied volatility is backed out from its live premium,
  and the position is repriced at the index stop and targets. The stop is never looser than 35% of
  the premium. Condors use the playbook rules: the stop is a buy-back at double the credit, and the
  targets are 50% and 70% of the credit.
- **Risk:reward** for each target.
- **Lots** sized from the real premium risk.
- **The index levels behind the trade.**
- **Why**: the setup's context and trigger.
- **Confidence: HIGH / MEDIUM / LOW**, combining the signal grade with that setup's 2022–26
  index-backtest track record (`setup_history.json`, regenerated with `atis-playbook setup-stats`):
  - HIGH: grade A+ and history of at least +0.03R per trade (condors: held 70% or more).
  - LOW: grade C, or history of −0.03R or worse (condors: held under 50%).
  - This is not a win probability.
- **Day summary.** Option P&L in rupees from the real premiums at each exit minute, before
  brokerage and taxes. If option prices can't be fetched, the alert falls back to index levels only.

### Recording NSE order flow (Dhan live feed)

Historical NSE ticks with the aggressor side are not available to retail traders, so `atis-live
record` builds that history going forward.

- **Instruments.** It subscribes to the front-month NIFTY / BANKNIFTY futures in Dhan's full mode
  (last trade, cumulative volume, 5-level depth). The packet layouts follow Dhan's official SDK.
- **Classification.** Each traded quantity is classified as buyer- or seller-initiated against the
  quotes in force before it: at or above the ask is a buy, at or below the bid is a sell, and the
  tick rule applies inside the spread.
- **Output:**
  - `data/flow/<SYMBOL>/<date>.csv`: 1-minute bars with `buy_volume` / `sell_volume` / `oi`. These
    load with `atis-playbook run --csv` and give the engine real delta.
  - `<date>-ticks.csv.gz`: every update, for later research.
- **Requirements.** `pip install -e '.[record]'`, `DHAN_CLIENT_ID` / `DHAN_ACCESS_TOKEN` and an
  active Dhan Data API plan. Dhan tokens currently last about 24 hours. On the VM,
  `deploy/oracle/enable-recorder.sh` installs a weekday 08:57 IST timer, and `sudo atis-dhan-token`
  pastes a fresh token.

### Run it on an Oracle Cloud Always Free VM

[deploy/oracle/README.md](../deploy/oracle/README.md) is a step-by-step guide covering the account,
the VM, the Telegram bot and the firewall. Then one command,
`sudo bash atis-setup.sh`, sets everything up:

- systemd services
- a weekday 08:55 IST timer
- Caddy with automatic HTTPS on `<ip>.sslip.io` and a password
- the VM firewall

## After review

1. You review the docs and answer the **Open questions** (consolidated in 08 §14, plus the three
   new ones in 09 §7).
2. We amend the docs (v0.3) and freeze them as the build baseline.
3. Phase 0 implementation begins per [08-IMPLEMENTATION-ROADMAP](docs/08-IMPLEMENTATION-ROADMAP.md).
