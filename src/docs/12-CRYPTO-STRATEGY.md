# Crypto: the strategy, the evidence, and how the bot runs

2026-10-25. Request: research crypto trading, implement the best strategy as an automated bot,
with risk management, consistent profit and volume profile in mind.

**Result.** The bot trades **BTC and ETH trend following**: long or short each coin depending on
the direction of its 20-, 60- and 120-day returns, sized so each coin runs at about 20% annual
volatility, and rebalanced once a day on Delta Exchange India perpetuals.

| | 2018–2022 (selection) | 2023–Oct 2026 (out of sample) | 2018–Oct 2026 |
|---|---|---|---|
| CAGR | +20.4% | +9.6% | +15.6% |
| Sharpe | 1.22 | 0.67 | 0.99 |
| Max drawdown | −14.3% | −20.0% | −20.0% |

These figures are after Delta India fees, slippage and real funding, and before income tax. Every
calendar year was positive: 2018 +14%, 2019 +31%, 2020 +44%, 2021 +14%, 2022 +3%, 2023 +11%,
2024 +9%, 2025 +7%, 2026 so far +10%.

**What "consistent" means here, honestly.**

- Yearly consistency is good: 9 of 9 years positive, and 83% of rolling 12-month windows positive.
  The worst 12 months were −11%.
- Monthly consistency is not: **about half of all months lose money**, and the worst month was −7%.
  Trend following loses small amounts often and wins large amounts occasionally.
- The 2023–26 result is about half the 2018–22 result. Expect the lower one.
- No strategy guarantees profit. This is the most robust result this repository has produced, not
  a promise.

---

## 1. How it was chosen

Data:

- Binance spot hourly candles for BTCUSDT and ETHUSDT, 2017-08 → 2026-10.
- Binance USD-M funding, 2019-09 →. Before that, a flat 0.01% per 8 hours (longs pay).
- Delta India's own perpetuals only start in Dec 2023 (BTC) and Feb 2024 (ETH), too late to cover
  a bear market.

Every cost is Delta India's: 0.05% taker plus 18% GST per side, and 0.02% slippage per side.

Eight strategies were fixed before testing. Selection used 2018–22 only; 2023–26 is the check.

| ID | Strategy | BTC Sharpe IS / OOS | ETH Sharpe IS / OOS |
|---|---|---|---|
| **S1** | **Trend blend 20/60/120d, vol-targeted, long/short** | **1.00 / 0.75** | **1.11 / 0.48** |
| S1L | Same, long-only | 1.07 / 1.02 | 1.08 / 0.53 |
| S2 | Donchian 20-day breakout, 10-day exit, 2×ATR stop | 1.14 / 0.52 | 0.64 / 0.32 |
| S3 | Above 100-day EMA, long-only | 0.90 / 0.71 | 0.90 / 0.38 |
| S4 | **Volume profile:** 20-day value-area breakout with POC migration | 0.87 / 0.29 | 0.52 / 0.12 |
| S5 | **Volume profile:** balance fade back to POC | −0.74 / −0.57 | −1.16 / 0.38 |
| S6 | **Volume profile:** trend + limit entry at the 20-day POC | 0.63 / −0.18 | 0.60 / 0.00 |
| S7 | **Volume profile:** S1L at half size below the 20-day POC | 1.09 / 0.92 | 1.12 / 0.29 |

As a BTC+ETH portfolio, S1 and S1L tie on 2018–22 Sharpe (1.19 vs 1.20). **S1 was chosen for
consistency**: positive in all 9 years, against S1L's losses in 2018 (−6%) and 2022 (−5%), when
long-only sat in cash through the bear markets. S1L has the shallower drawdown (−14% vs −20%) and
can be selected with `TrendParams(long_only=True)`.

### Volume profile: tested four ways, adds nothing

You asked for volume profile to be considered, so it was the core of S4–S7:

- S4–S6 use it as the signal.
- S7 uses it as a risk throttle.

None beat plain trend following out of sample. S7 cut BTC's return from 14% to 11.5% and ETH's
from 6% to 2.8%, with about the same drawdown. This agrees with the earlier finding: intraday
volume-profile setups on two years of BTC/ETH lost 250–700R after fees (src/README.md, crypto
backtest).

The bot still computes the 20-day composite POC, VAH and VAL and puts them in every Telegram
report, as context. They never change a position.

### Robustness: a plateau, not a peak

S1L as a BTC+ETH portfolio over 2018–2026. Every variant stays between Sharpe 0.94 and 1.10:

| Change | Full-period Sharpe | OOS Sharpe | Max DD |
|---|---|---|---|
| Base (20/60/120d, 20% vol, 25% band) | 1.06 | 0.87 | −13.8% |
| Lookbacks 10/30/90 | 1.00 | 0.79 | −13.8% |
| Lookbacks 30/90/180 | 0.96 | 0.77 | −17.6% |
| Lookbacks 20/60/120/250 | 0.94 | 0.65 | −14.1% |
| Target vol 15% / 30% | 1.06 / 1.10 | 0.85 / 0.85 | −10.7% / −20.7% |
| Rebalance band 10% / 50% | 1.08 / 1.02 | 0.85 / 0.75 | −13.7% / −17.0% |
| **Costs ×2 / ×3** | **1.01 / 0.95** | 0.80 / 0.73 | −14.3% / −14.7% |

Trial count: 8 strategies × 2 coins plus 11 robustness variants. With about 20 configurations
over 8.8 years, the best Sharpe you'd expect from luck alone is about 0.5. S1's 0.99 clears it, and
time-series momentum was a documented crypto effect before this test
([SSRN: risk-managed TSMOM in crypto majors](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=7115459);
[2025 comparative study](https://www.journals.vu.lt/BATP/en/article/download/44540/42590/138419)).
The literature also warns that simple Bitcoin trading rules decay out of sample, with one study
showing Sharpe falling from 0.66 to 0.06. That decay is visible here too, from 1.22 to 0.67.

### Costs that matter

Over 8.8 years the backtest paid fees equal to 27% of starting equity, and **funding equal to 43%**.
Longs pay funding most of the time in crypto. All return figures above are after both.

### Also ruled out (earlier research in this repository)

- Hourly cross-sectional momentum across 30 coins: costs of 13–31 bps per rebalance exceed the gross edge.
- Funding-rate carry: −25% a year even at zero cost, with a liquidation.
- Order-flow detectors on true aggressor data: no edge (11-ORDER-FLOW-RESEARCH.md).

---

## 2. What the bot does

`src/atis/crypto/`, standard library only, with the same signal code in backtest and live.

| When | Job | What happens |
|---|---|---|
| 00:05 UTC daily (05:35 IST) | `rebalance` | Reads Delta's completed daily candles, computes each coin's target, runs the risk checks, trades the difference (reductions first, all `reduce_only`), re-reads positions, journals, sends Telegram |
| :30 every hour | `watch` | Re-marks the account. If a kill switch trips: flatten everything, halt, Telegram |

**Sizing.** Each coin gets half the equity. Its notional is
0.5 × equity × min(20% / realised 30-day vol, 1.0) × |trend score|, where the trend score is
−1, −1/3, +1/3 or +1. Before the 0.5 weight, per-coin exposure had a median of about 0.2× and never
exceeded 0.91×. After it, a typical position is about 0.1× equity per coin.

**Risk manager** (`risk.py`, state in `crypto-risk-<broker>.json`, so it survives restarts):

| Control | Limit | Why there |
|---|---|---|
| Daily loss | −8% → flatten and halt | Worst historical day −5.65% |
| Drawdown from peak | −30% → flatten and halt | Worst historical drawdown −20% |
| Halt latch | Stays halted until `resume` by a person | A machine should not decide the brake was wrong |
| Gross exposure | ≤ 1.5× equity, scaled down if above | With the 0.5 weight per coin, history stayed under about 0.9×; a backstop against a bug |
| Per-coin exposure, before the weight | ≤ 1.0× | History max 0.91× |
| Stale data | Daily candle older than 30 h → hold, don't trade | No trading on yesterday's data |
| Price sanity | Mark more than 2% from the latest hourly close → hold | Catches a bad print or feed |
| Exchange leverage | 2× isolated per product | Liquidation about 50% away at maximum size |
| Once per day | Keyed by UTC date | A rerun or restart can't double-trade |
| Order type | Market only; every reduction `reduce_only` | A duplicated close can't open a reverse position |

**Brokers:**

- `paper` (default): simulated fills at Delta's live mark price plus slippage and fee. It does
  not simulate funding, so it is slightly optimistic for longs.
- `testnet`: Delta India's demo exchange. Real API, no real money.
- `live`: needs `DELTA_API_KEY`, `DELTA_API_SECRET` **and** `ATIS_CRYPTO_LIVE=I_ACCEPT_THE_RISK`.

## 3. Going live: a gate, not a date

1. **Paper**, 4+ weeks. Confirm the daily cycle runs every day, messages arrive, and the watchdog
   stays quiet.
2. **Testnet**, 2+ weeks. Confirm real order placement, `reduce_only` closes, position
   reconciliation (the Telegram report flags any mismatch), and a manual `flatten`.
3. **Live at small size.** Delta's contract granularity is coarse: one BTC contract is 0.001 BTC,
   about $80. A typical BTC target is 0.1× equity. Below about $2,000 that is two or three
   contracts, so rounding moves BTC exposure by 20% or more. At $10,000 or more it tracks the
   target within about 5%.
4. Scale only after 3+ months live that look like the backtest: drawdown inside −20% and no risk
   breaches.

The API key needs **trading permission only, never withdrawal**. Whitelist the VM's IP if Delta
offers it. The key lives only in `/etc/atis/atis.env` on the VM.

Crypto gains in India carry specific tax treatment. Get advice from a tax professional; this
document does not cover it. Nothing here is investment advice.

## 4. Commands

```bash
atis-crypto backtest --sync              # download/refresh history, then the full backtest
atis-crypto rebalance --dry-run          # one paper cycle now, printed instead of sent
atis-crypto status | watch | resume | flatten  [--broker paper|testnet|live]
```

On the VM: `sudo bash /opt/atis/deploy/oracle/enable-crypto.sh`, then `sudo atis-crypto-ctl status`.

Reproduce the study: `research/crypto/strategy_study.py data/crypto` (all eight strategies) and
`research/crypto/robustness.py data/crypto research/crypto` (plateau and cost stress). Both need
pandas; the bot itself does not.
