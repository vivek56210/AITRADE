# 03 · Data Platform

> **ATIS Design Doc 03 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [01-ARCHITECTURE](01-ARCHITECTURE.md) · Consumers: every other plane.

---

## 1. Data philosophy

1. **No trade on bad data.** Quality gates sit *upstream* of all analytics; a data problem
   becomes a trading halt, never a silent wrong answer.
2. **Point-in-time everything.** Any feature, label, or dataset can be reconstructed *as it was
   knowable* at any past instant — the precondition for honest backtests.
3. **Declared honesty about data tiers.** India ≠ crypto in data depth. Every detector declares
   the tier it needs; the platform never pretends to see order flow it doesn't have.
4. **Raw is sacred.** Raw feeds are archived untouched forever; every downstream artifact is a
   reproducible projection.

## 2. Data tiers (load-bearing concept)

| Tier | Contents | Where it exists | Unlocks |
|---|---|---|---|
| **A** | Full L2 depth deltas + aggressor-flagged trades | Crypto venues (free), NSE TBT feed (exchange-licensed, expensive — not v1) | True footprint, absorption/exhaustion, queue dynamics, full order-flow suite |
| **B** | Trade ticks + 5–20 level depth, vendor tick history | India via TrueData tick feed (P0-D2) and/or **Dhan 20-level depth WS** (NSE EQ+NFO, ~50 instruments per connection — focused watchlist, not whole-market); broker WS best-effort | Estimated delta (tick rule), profiles, liquidity maps, most detectors with declared estimation error; 20-depth unlocks better absorption/imbalance estimates on the focus set |
| **C** | Conflated broker WS snapshots + 1m bars | Broker-only fallback | Profiles, structure, VWAP, regime — no order-flow detectors |

Detector availability by tier is declared in each detector spec (04 §2). The Strategy Manager
auto-disables strategies whose evidence quorum is unsatisfiable at an instrument's tier.

## 3. Source catalog

### 3.1 India — equities & F&O

| Source | Data | Latency | Cost | Notes |
|---|---|---|---|---|
| Zerodha Kite WS | Conflated ticks, 5-level depth, OI | ~100–300 ms | ₹500/mo (data key; execution-only key free) | 3,000 instruments × 3 connections per key; the P1 backbone |
| **Dhan WS** | Ticks + order-update stream; **separate 20-level depth feed** (NSE EQ + NFO only, ~50 instruments/connection) | ~100–300 ms | ₹499/mo (waived with activity) | 5 conns × 5,000 instruments (standard feed); 20-depth = focused watchlist order-flow upgrade |
| TrueData | Real-time **tick-by-tick** push + option chain with greeks/IV; 5-level depth | ~100 ms | ~₹2–10k/mo (quote-based) | The tick-feed option for P0-D2; historical archive depth must be confirmed in procurement |
| Global Datafeeds (NimbleData) | Real-time at **1-second snapshot** cadence (not tick-by-tick); EOD history to 2010; tick archive ~1 week only | ~1 s | quote-based | Suits 1s-bar systems; **not** a tick-backfill source |
| NSE/BSE official files | Bhavcopy, deliverable %, FII/DII, MWPL/ban list, corporate actions, index constituents | EOD | Free | Ground truth for reconciliation & survivorship-free universe |
| Exchange announcements (NSE/BSE) | Corporate filings, circulars | ~1 min | Free | Primary corporate news source (beats media) |
| NSE option chain | OI, IV (derived), chain snapshots | seconds | via broker/vendor | Options Intelligence input |
| RBI / MOSPI / GoI | Policy, CPI/IIP/GDP, auctions | Calendar | Free | Macro Agent + embargo calendar |
| GIFT Nifty (NSE IX) | Overnight index context for gap playbook | Best-effort | via Kite (personal-use quotes) or delayed web | Treated as context only — never a hard dependency |
| Earnings calendar + results | Dates, PDFs, con-call transcripts | Daily | Free/cheap | Fundamental Agent |

### 3.2 Crypto

| Source | Data | Latency | Cost |
|---|---|---|---|
| Venue WS (Binance/Bybit/Delta) | L2 deltas, aggressor trades, funding, OI, liquidations, mark/index | <100 ms | Free |
| Coinglass (or similar) | Cross-venue liquidation maps, aggregated OI/funding | 1 m | $30–100/mo |
| CryptoQuant / Glassnode (tier by budget) | Exchange flows, whale metrics, stablecoin flows, on-chain activity | 10 m–1 d | $0–800/mo |
| Stablecoin/DeFi public APIs, dev-activity (GitHub) | Supply, TVL, commits | Daily | Free |

### 3.3 Commodities (MCX)

Broker/vendor feed for MCX ticks; EIA/API inventories, COMEX/NYMEX/LME settlement cues, IMD/NOAA
weather, USDINR (spot + futures), DGFT/policy notifications. Mostly daily/event cadence; MCX
prices are largely global-benchmark × USDINR pass-through — the KG encodes this explicitly.

### 3.4 News & sentiment

| Source | Method | Notes |
|---|---|---|
| Exchange announcements | API/scrape | Highest reliability class |
| Wire/portal RSS (Reuters/Moneycontrol/ET/BusinessLine…) | RSS + fetch | Reliability-scored per source |
| Economic calendars | API | Drives embargo windows |
| X/Twitter | Paid API tier (open question 02 §10) | Curated handle lists per asset class |
| Reddit / Telegram / Discord / YouTube | Official APIs / bot membership / transcript API | Rate-limit-respecting collectors |
| Analyst/broker reports | Manual drop folder + parse | Low cadence |

Every source gets a **reliability prior** (exchange filing = 0.99; anonymous Telegram = 0.2) that
flows into News Score; high-impact claims from low-reliability sources require cross-confirmation
before they can move anything (02 §3.1-8).

**Point-in-time honesty:** historical news archives with original publication timestamps are
scarce and expensive. Until a PIT news archive is acquired (optional later purchase), news-driven
strategies validate **live-forward only** (04 §4 constraint 3) — we archive our own news stream
from day one so the platform builds its own PIT history going forward.

## 4. Ingestion & canonical schemas

```
venue APIs → md-connector-{venue} → md.raw.{venue} → normalizer → md.tick/md.depth/md.chain
                                                     │
                                              dq-sentinel (inline)
                                                     ▼
                                     bar-builder → md.bar.{tf} → feature-engine → features
                                                     ▼
                                                archiver → lake (Parquet/Iceberg)
```

**Connector duties:** reconnect with jittered backoff; sequence/heartbeat tracking; gap events;
venue clock-offset estimation; raw archival. **Normalizer duties:** symbology (one instrument
master: `MARKET:SYMBOL` ↔ venue tokens ↔ ISIN, versioned over corporate actions), unit/decimal
normalization, timezone discipline (everything UTC internally, IST only at presentation),
`ts_event` vs `ts_ingest` separation.

**Canonical schemas (Protobuf, registry-managed):**

- `Tick {instrument, ts_event, ltp, ltq, cum_vol, oi?, bid, ask, bid_qty, ask_qty, seq, tier, flags}`
- `Depth {instrument, ts_event, levels[{px,qty,orders?}], is_snapshot, seq}`
- `Bar {instrument, tf, ts_open, o,h,l,c, vol, vwap, trades?, delta?, oi_close?, quality}`
- `OptionChainSnapshot {underlying, expiry, ts, spot, futures_px, strikes[{k, cp, ltp, bid, ask, oi, oi_chg, vol, iv}]}`
- `NewsItem {id, ts_pub, ts_seen, source, reliability, url, title, body_ref, entities[], dedup_cluster}`
- `SentimentReading {scope, ts, window, score, volume, source_mix, crowding}`
- `OnChainMetric {asset, metric, ts, value, source}`
- `EconomicEvent {id, ts_scheduled, region, type, importance, consensus?, actual?, revised?}`
- `FIIDIIFlow {segment, date, fii_buy, fii_sell, dii_buy, dii_sell}`

### 4.1 Instrument master & contract lifecycle (added in v0.2 — load-bearing)

- **Instrument master** is a versioned, point-in-time-queryable registry: `MARKET:SYMBOL` ↔
  venue tokens ↔ ISIN, tick/lot size, price bands, **capability matrix** (shortable overnight?
  settlement type cash/physical? option style?), F&O-list membership, ban status — all dated.
  Risk checks 05 §3.16–17 read this matrix.
- **Derivative chains:** each underlying owns its live contract chain (expiries, strikes).
  Exchange-issued corporate-action adjustments to F&O contracts create *new instrument versions*,
  never in-place edits.
- **Roll policy:** front-month selection by OI+volume crossover (default: next-month OI exceeds
  front, or T-2 sessions, whichever first, P). Rolls are first-class TradePlans — risk-checked
  and cost-modeled, never silent swaps.
- **Continuous series for research:** back-adjusted (panama) and unadjusted series both
  maintained with stored roll dates; every backtest declares which series it used.
- **Ex-date awareness:** cash-equity corporate actions flag affected positions so protective
  stops are re-based before the ex-date open (07 §7).

## 5. Data Quality Engine (dq-sentinel)

**Validation rules (inline, per event):**

| Class | Checks |
|---|---|
| Schema | Types, required fields, enum ranges |
| Time | Monotonic per-key `ts_event` (tolerance), skew vs platform clock, session-hours sanity |
| Price | > 0, within circuit band, jump vs last (>x σ ⇒ suspect-tick flag), bid ≤ ask, OHLC coherence |
| Volume/OI | Non-negative, cum_vol monotonic per session, volume sanity vs 20-day profile |
| Continuity | Sequence gaps, heartbeat timeouts, snapshot-vs-delta consistency (depth) |
| Cross-source | Broker vs vendor price divergence > y bps sustained ⇒ quarantine + alert |
| Duplicates | event dedup by (source, seq/id) |

**Stream quality score** per instrument (EWMA of pass rate, gap penalty, staleness penalty),
published on `state.market.data_quality`. **Action ladder:**

| Quality | Action |
|---|---|
| ≥ 0.999 | Normal |
| ≥ 0.99 | Flag; suspect ticks excluded from bars (bar carries `quality`) |
| ≥ 0.95 | Tier downgrade for instrument (flow detectors off) |
| < 0.95 | Instrument halt (no new entries; manage positions on protective stops) |
| Market-wide < 0.95 | Market-level kill switch L3 |

**EOD reconciliation:** rebuilt bars vs official bhavcopy (close, volume, OI) — any mismatch
opens a data-incident ticket and marks the day's lake partition `unverified` (research excludes
it until resolved). Clock discipline: NTP (chrony) with sanity sentinel; skew > 250 ms ⇒ pause.

## 6. Stream processing jobs

| Job | Input → Output | Notes |
|---|---|---|
| bar-builder | ticks → bars 1s/1m/5m/15m/1h/1d | Venue calendars, auction handling, session boundaries; late-tick policy (grace 2 s, then correction event) |
| delta/CVD | aggressor trades (A) or tick-rule (B) → per-bar delta, CVD | Estimation method stamped on output |
| profile-builder | bars/ticks → session & composite profiles, TPO structures | POC/VAH/VAL/IB/HVN/LVN (definitions in 04 §2.1) |
| vwap-suite | ticks → daily/weekly/anchored VWAP + σ-bands | Anchor registry (events, swings) |
| chain-snapshotter | option ticks → coherent chain snapshots | Staleness-aware (per-strike ts) |
| rolling-features | bars → returns/vol/ER/ADX/Hurst/correlations | Feeds feature store online |
| oi-analytics | chain snapshots → ΔOI, PCR, max-pain, IVR/IVP, GEX | 02 §3.1-7 |

All jobs are deterministic, replayable, and CI-tested against golden days.

## 7. Feature Store (Feast)

- **Entities:** instrument, underlying, sector, market, strategy.
- **Offline store:** lake (Iceberg) — training/backtests read *point-in-time joins* only; lookahead
  is structurally impossible through the store API (event-time watermarks, no future rows).
- **Online store:** Redis — low-latency serving to agents/committee; TTL per feature view.
- **Feature views (examples):** `ret_{5m,1h,1d}`, `rv_yz_30m`, `atr_14`, `er_20`, `adx_14`,
  `hurst_dfa_100`, `dist_to_poc_atr`, `value_area_position`, `cvd_slope_20`, `sweep_recency`,
  `oi_chg_pctile`, `pcr_z`, `ivr`, `gex_regime`, `news_score_1h`, `sent_z_4h`, `funding_8h`,
  `basis_annualized`, `fii_net_5d`, `regime_probs`, `health_score`.
- **Rules:** every feature has an owner, a definition in code (versioned), a validation notebook,
  and drift monitoring (06 §6). Features used by any ACTIVE model are immutable — changes create
  new feature versions.

## 8. Knowledge Graph (kg-svc, Neo4j)

**Purpose:** propagate meaning — "this news hits whom?", "what hedges what?", "what leads what?"

**Nodes:** Company, Instrument, Sector, Index, Commodity, Currency, CryptoAsset, Protocol,
Exchange/Venue, MacroIndicator, Event, Strategy, Person(promoter/insider — public data only).

**Edges (typed, dated, evidenced):**

| Edge | Example | Source |
|---|---|---|
| `constituent_of` | RELIANCE → NIFTY50 (weight) | Index files |
| `belongs_to` | TCS → IT sector | Master data |
| `supplier_of` / `customer_of` / `competitor_of` | Motherson → Maruti | Filings/LLM extraction (citation-verified) |
| `correlated_with {ρ, window, pvalue}` | USDINR ↔ IT sector | Nightly stats job, FDR-controlled |
| `leads {lag, strength}` | COMEX gold → MCX gold | Lead-lag estimation |
| `sensitive_to {beta}` | OMCs → Brent | Rolling regression |
| `derives_from` | NIFTY-FUT → NIFTY50 | Master data |
| `bridged_by / issued_by / runs_on` | USDT ↔ exchanges; token → chain | Crypto metadata |
| `impacted_by {direction, confidence}` | Sugar stocks ← ethanol policy Event | News pipeline |

**Statistical edges are recomputed nightly with significance discipline** (rolling windows,
p-values, FDR control, minimum history) — stale/insignificant edges expire. LLM-extracted edges
require citation verification and carry provenance.

**Uses:** news impact propagation (company → suppliers → sector → index), correlation-aware
portfolio checks (05 §5), hedge candidate lookup, crypto contagion maps, research hypothesis
mining (06 §9).

## 9. Institutional memory

| Store | Content | Medium |
|---|---|---|
| Decision store | Every DecisionRecord (plans, abstentions, vetoes) hash-chained | PG + lake |
| Outcome store | Labels, MAE/MFE, attribution per plan | ClickHouse + lake |
| Narrative memory | Post-trade reviews, incident post-mortems, regime narratives — embedded for retrieval (pgvector) | PG |
| Anomaly log | Every DQ incident, weird print, broker quirk | PG |
| Strategy/detector registry | Every version, validation report, promotion history | PG + MLflow |
| Parameter history | Every limits-registry change (who/when/why) | git + PG |

Nothing is deleted. Devil's Advocate and Research agents query this memory (similarity search
over narratives: "when have we seen this setup fail?").

## 10. Historical data & backfill

- **Targets (P):** daily OHLCV 2010→ (equities/indices), 1-minute 2019→ (indices, F&O liquid set,
  top-250 equities), tick where vendor archives allow (indexes first), option chains EOD 2019→ +
  intraday snapshots start-of-platform→, crypto: full trades/L2 from venue archives (Binance data
  dumps) 2020→, MCX 1-min 2019→.
- **Archive reality check (verified 2026-07, [09 §3.2](09-VALIDATION-REVIEW.md)):** GDFL holds
  ~1 week of tick history — *not* a backfill source; TrueData's tick-archive depth is unpublished
  and must be confirmed during P0-D2 procurement. **Plan B is structural: ATIS archives its own
  ticks from day 0**, so live-forward history accumulates regardless of vendor archives.
- **Corporate actions:** both adjusted and unadjusted series kept; adjustment factors versioned;
  splits/bonuses/dividends from official files.
- **Survivorship:** monthly universe snapshots (index constituents, F&O list, ban lists) —
  backtests select from the universe *as of that date*.
- **Vendor data is quarantined until** cross-checked vs bhavcopy on overlapping ranges.
- Datasets are versioned (Iceberg snapshots); every research result pins dataset versions.
- **Scheduling:** backfill procurement and load begin in Phase 0 — it is on the critical path
  for Phase-1 strategy validation (08 §2).

## 11. Retention & capacity envelope

| Class | Volume (est.) | Hot | Archive |
|---|---|---|---|
| India ticks+depth (Tier B, ~300 instr + chains) | 2–6 GB/day raw | 7 d bus | Forever, ~0.5–1.5 GB/day Parquet |
| Crypto trades + conflated L2 (50 pairs; full depth top 10) | 5–20 GB/day | 7 d | Forever, compressed |
| Bars all TFs | ~200 MB/day | 30 d bus, 2 y CH | Forever |
| Chains | 1–3 GB/day | 7 d | Forever |
| News/sentiment | <200 MB/day | 90 d | Forever |
| Decisions/outcomes | trivial | ∞ PG | Forever |

Year-one lake ≈ 2–6 TB — a non-problem on object storage. Knobs if crypto depth grows: conflate
to 250 ms / top-10 levels for storage while keeping live full depth in memory.

## 12. Open questions for review

1. **P0-D2:** TrueData vs Global Datafeeds vs broker-only start (this decides Tier B vs C for India, which decides whether order-flow detectors exist for NSE in v1)?
2. Historical tick backfill budget (vendor archives are priced per segment/year) — how deep do we buy?
3. X/Twitter paid API: yes/no for v1?
4. On-chain vendor tier: free/cheap (Coinglass only) vs CryptoQuant/Glassnode subscription?
5. Confirm the v1 instrument universe: NIFTY/BANKNIFTY complex + top-100 equities + F&O liquid set + 20 crypto pairs + 6 MCX contracts (P)?
