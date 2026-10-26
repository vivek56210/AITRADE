# Order flow: what the data says, and the improvement plan

2026-10-24. Question asked: research our logic in depth and find the best improvement, or a new
strategy based on order flow.

**Answer in one paragraph.** No order-flow signal available to us predicts NIFTY, BANKNIFTY or BTC
returns well enough to pay for a trade. That holds for every source on disk: true tick aggressor
flow on BTC, footprint patterns, 9.5 years of NSE participant positioning, and daily OI change.
Each one was tested. The pattern is the same as in the literature: order flow *explains* price
moves at the moment they happen, but its forecast fades within seconds to minutes. A retail trader
paying 4–12 bps a round trip, acting on alerts, cannot reach that horizon. The improvement that
does pay is the one already made: the October live review cut the losing trade types. The plan
below builds on that, and uses order flow for **execution**, where its evidence is strongest,
rather than for prediction.

---

## 1. What order-flow data exists here

| Source | Market | Span | Signed? | Status before this study |
|---|---|---|---|---|
| Binance aggTrades (`data/parquet/futures/um/aggTrades`, 12 GB) | BTCUSDT perp | 2024-01 → 2026-06 | **Yes**: true taker side on every trade | Used by the crypto desk detectors |
| Binance taker-buy volume in klines | BTC/ETH perp | 2 years | Yes | Tested as setup confirmation (README) |
| NSE F&O bhavcopy (`hist/options.db`, 8.2M rows) | NIFTY/BANKNIFTY options and futures | 2017-04 → 2026-09 | Only via change in OI | Wave 4: rejected |
| **NSE participant-wise OI and volume** (new, `data/participant`) | All index F&O, by FII / DII / Pro / Client | **2017-04-03 → 2026-10-23, 2,359 days** | **Yes**: long and short contracts per participant | Never tested |
| Dhan live feed recorder (`atis-live record`) | NIFTY/BANKNIFTY futures, 5-level depth | — | Yes, Lee-Ready | **Recorded nothing**: ran once at 08:07 on Oct 5, never scheduled |
| Upstox index candles | NIFTY/BANKNIFTY spot | 2022 → now | No volume at all | Used by the playbook |

NSE intraday futures history with an aggressor flag does not exist on any free or retail route.
The only way to get it is to record it.

## 2. Results

### 2.1 True intraday aggressor flow (BTC, 1.3M minutes, 2024-01 → 2026-06)

Taker buy/sell imbalance over the last 5–240 minutes against the next 5–240 minutes. Samples are
non-overlapping.

| Lookback | Horizon | IC | IC after the window's own return | Edge per side (top vs bottom decile) |
|---|---|---|---|---|
| 15 min | 15 min | −0.043 | −0.018 | 0.57 bps |
| 60 min | 15 min | −0.042 | −0.009 | 0.37 bps |
| 15 min | 240 min | +0.008 | +0.014 | 3.09 bps |
| 240 min | 60 min | −0.026 | −0.001 | 2.93 bps |

- The sign is **negative** in all three years: heavy buying slightly predicts a pullback. It is not
  continuation.
- Most of that is price mean reversion. Controlling for the window's price change leaves |IC| ≤ 0.018.
- The best edge is about 3 bps per side, against **10–12 bps round-trip taker fees** (4 bps maker).
  Even perfect flow data carries roughly a tenth of the edge needed.

This matches the earlier crypto-desk detectors on the same data: CVD divergence −0.049R per trade
(59 signals), delta exhaustion −0.048R (72). It also matches the README's finding that real flow as
a confirmation inside the 13 setups changed nothing. In the literature, order-flow imbalance
explains price changes over the same interval at the best bid and ask ([Cont, Kukanov & Stoikov](https://arxiv.org/abs/1011.6402)).
Its forecasting reach is seconds to about two minutes, even on index futures
([CSI 300 study](https://arxiv.org/pdf/2505.17388); [BankNifty tick study](https://arxiv.org/abs/2507.22712)).
That is execution territory, not alert territory.

### 2.2 NSE participant positioning, the "Indian COT report" (2017-04 → 2026-10)

The 2026-08 review panel ranked participant-wise OI as the best free Indian positioning dataset
(REVIEW-PANEL §4.2). Four hypotheses were fixed before the data was opened. Each was tested on
NIFTY and BANKNIFTY at 1, 3 and 5 days, entering at the next open because NSE publishes after the
close. Costs were 0.042% a round trip.

| Hypothesis | 2017–22 (in sample) | 2023–26 (out of sample) |
|---|---|---|
| H1 Follow FII net index-futures change | IC +0.09 to +0.10 (1-day) | **IC −0.02 to −0.06, t down to −3.1** |
| H1b Follow FII net futures *volume* | IC +0.09 to +0.10 | **IC −0.04 to −0.06, t −3.4 / −3.6** |
| H2 Fade extreme Client (retail) net position | ~0 | ~0 |
| H3 FII long-ratio extremes (<25% / >75%) | ~0, few trades | ~0 |
| H4 Follow FII net index-option change | IC +0.08 to +0.10 | IC −0.02 to −0.14 |

Why "follow the FIIs" flipped sign:

| | 2017–22 | 2023–26 |
|---|---|---|
| Same-day correlation of FII futures flow with the index return | +0.37 to +0.44 | **+0.52 to +0.61** |
| Next-day correlation of the index return with itself | +0.03 to +0.05 | **−0.05 to −0.10** |
| FII flow's next-day IC **after removing the day's return** | +0.07 to +0.08 | **−0.02 to +0.02** |

FII index-futures flow is mostly an echo of that day's price move. It has carried no independent
information since 2023. The OOS "flip" is daily mean reversion showing through it.
([Earlier work](https://www.sciencedirect.com/science/article/pii/S0970389616300854) also finds
FII futures positions have no reliable link to NIFTY returns.)

One effect held its sign in every window, but was found after looking, so it counts as an extra
trial. Retail (Client) futures flow beyond what the day's return explains predicts the next day
negatively: partial IC −0.05 to −0.06 on both indices in both windows. As a strategy with a
rolling, look-ahead-free fit, it **loses after costs out of sample**: −0.008% to −0.034% per trade.
An IC of 0.05 on a ~1% daily move is worth about 4 bps, the same as the cost.
(Context: SEBI found [91–93% of individual F&O traders lose money](https://www.sebi.gov.in/media-and-notifications/press-releases/sep-2024/updated-sebi-study-reveals-93-of-individual-traders-incurred-losses-in-equity-fando-between-fy22-and-fy24-aggregate-losses-exceed-1-8-lakh-crores-over-three-years_86906.html).
Retail as a group loses, but its daily flow is not a timing signal.)

As a **filter on the intraday playbook** (2022–26 trades, prior-day signal):

| Filter | 2022–25 aligned / against | 2025–26 aligned / against |
|---|---|---|
| Prior-day FII futures flow | +0.049R / +0.056R | +0.206R / **+0.383R** |
| Prior-day fade-retail signal | **+0.132R / −0.031R** | +0.178R / **+0.444R** |

Neither filter helps in both windows. Not adopted.

### 2.3 Already rejected earlier, and still valid

- Daily change in OI from the bhavcopy, standalone and as a filter: no stable edge
  (RESEARCH-LOG wave 4).
- Order flow on NSE spot: impossible, because index candles have no volume.

## 3. Why order flow fails *for us*: the cost arithmetic

| | Edge needed per trade | What flow delivers |
|---|---|---|
| NIFTY futures, intraday | ~10 points round trip (RESEARCH-LOG) | — |
| NIFTY ATM option, alert-driven | spread + STT + slippage. Not measured: our feed has no bid/ask | — |
| BTC perp, taker | 10–12 bps | 0.4–3 bps |
| Daily, next open → close | 4.2 bps | ~4 bps (IC 0.05) |

Order flow's information decays within seconds to minutes. An alert reaches a phone and a person
places the order after that. Any order-flow edge that survives a human in the loop would have to
be large and slow, and none of the sources shows one.

## 4. The improvement plan, ranked by expected value

**1. Keep the October rules and measure them on option P&L, not index R.** *(done; now measure)*
Commit `e7b418c`: no entries before 09:45, first target ≥ 1R, B2 off, a 10% premium-stop sizing
floor. On 2022–25 history NIFTY went from −0.5R to +54.5R. Those are index R before costs. The
alerts trade options, so the real test is rupee P&L in `journal-live.jsonl`:

- About 0.5 alerts per symbol per day means roughly 100 alerts in 4–5 months.
- Decide then, against a written bar: positive net ₹, profit factor above 1.2, BANKNIFTY no worse
  than flat.

**2. Fix operations, which cost more than any signal tweak.**

- The runner missed Oct 7, 15, 19 and 21. On Oct 22 it stopped before the close.
- Deploy `e7b418c` to the Oracle VM. Check that `ATIS_LIVE_ARGS` still says what you intend.
- Add a "no heartbeat by 09:20" Telegram alert.

**3. Start recording NSE futures flow now, for execution research, not signals.**

- `atis-live record` works but isn't scheduled, and needs a daily Dhan token.
- With 3 months of L1–L5 depth and trades, test what the literature supports. Does order-book
  imbalance or microprice at the alert minute predict the next 30–120 seconds? If yes, use it to
  **time the entry inside the signal minute**, or to place a limit order instead of crossing the
  spread.
- That attacks option round-trip cost directly. The same recording also measures that cost for
  the first time.
- Cost: a Dhan Data API plan and the daily token step.

**4. Stop building predictive order-flow detectors.**

- Five independent tests, on true flow and on positioning, give the same answer.
- Re-open only with new data that changes the arithmetic: NSE tick-by-tick depth, or an
  institutional fee tier.

**5. If you want a second strategy, it is not order flow.**

- The only other result in this repository that survived real prices is the volatility risk
  premium: the monthly 5% strangle when India VIX is below its 1-year median
  (`strangle_lowvix`, RESEARCH-LOG wave 4).
- It is a thin edge: CAGR about 1% at research sizing, and 48% of its profit came in 2021.
- It is a different risk (short premium, tail exposure). Treat it as a separate, small allocation
  only after a written risk limit.

**Lead noted, not pursued:** FII futures volume correlates +0.05 to +0.07 with the *next overnight
gap* out of sample. That gap only trades on GIFT Nifty after NSE publishes in the evening. It is
small, and GIFT history is not on hand.

## 5. Trial count

Pre-registered: 5 signals × 3 horizons × 2 indices = 30 tests. Post-hoc: 4 partial-IC checks, the
fade-retail strategy at 2 thresholds × 2 indices, and 2 filters on 2 trade sets. BTC: 16
lookback × horizon cells. Nothing here passed, so no deflated-Sharpe adjustment is needed. The
count is recorded so a later "discovery" in the same data is judged against it.

## 6. Reproduce

Scripts are in `research/orderflow/`. Data goes to `data/` (gitignored).

```bash
python research/orderflow/participant_download.py          # NSE participant OI + volume -> data/participant
python research/orderflow/daily_index.py <dir>             # daily NIFTY/BANKNIFTY -> <dir>/daily_*.json
python research/orderflow/participant_h1_h4.py <dir>       # pre-registered H1-H4
python research/orderflow/participant_partial_ic.py <dir>  # flow vs same-day return
python research/orderflow/participant_fade_retail.py <dir> # post-hoc retail strategy, rolling fit
python research/orderflow/btc_flow_bars.py <out>           # aggTrades -> 1m taker buy/sell bars
python research/orderflow/btc_flow_ic.py <out>             # flow IC vs horizon vs fees
```

Notes:

- `participant_download.py` reads trading days from the main checkout's `hist/options.db`.
- `btc_flow_bars.py` reads the main checkout's Binance aggTrades.
- The analysis scripts use `pandas`. The `v5/.venv` interpreter has it; it has no `scipy`, so
  Spearman correlation is computed on ranks.
