# 07 · Execution Engine & Broker Integration

> **ATIS Design Doc 07 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [05-RISK-PORTFOLIO](05-RISK-PORTFOLIO.md) (verdicts), [01-ARCHITECTURE](01-ARCHITECTURE.md) §13–14
> Scope: everything from "approved plan" to "reconciled fill", in all three modes, live and simulated.

---

## 1. Modes and the mode-manager

| Mode | Execution behavior |
|---|---|
| P1 Recommendation | No orders. Plans → console + notifier (Telegram/email) with full reasoning; user actions logged (06 §2). Paper env may auto-execute the same plans for baseline tracking. Decision→notification SLA ≤ 5 s; every recommendation card shows an explicit validity window and expires visibly. |
| P2 Assisted | OMS stages complete order groups (entry + protection + targets), all risk checks pre-passed; user one-click approve/reject in console (approval expires with the entry zone); every decision logged. |
| P3 Constrained autonomy | Auto-submit after the safety pipeline (§6). Hard caps from limits registry (capital slice, position count, per-day order budget). Per-market flags; instant downgrade authority (human or automatic). |

The **same OMS/exec path runs in every mode and environment** — sim/paper use a simulated broker
adapter behind the identical interface (01 §7).

**Safe mode:** a single control drops every market to P1 simultaneously (vacation, illness,
extended unattended periods) — paired with the unattended-hours risk policy (05 §8). Ignoring
the platform must always be safe.

## 2. Order lifecycle (OMS)

```
DRAFT → RISK_CHECKED → STAGED → [USER_APPROVED (P2)] → SUBMITTED → ACKED
   → PARTIALLY_FILLED → FILLED | CANCELLED | REJECTED | EXPIRED
                     ↘ AMBIGUOUS (timeout/unknown) — special handling below
```

- **Idempotency:** client order ID = `hash(plan_id, leg, attempt)`; adapters MUST treat resubmits
  of the same key as queries, not new orders. Journal (append-only, local disk + PG) records
  every transition before the side effect ("write-ahead trading").
- **AMBIGUOUS state:** submit timed out / connection died mid-call ⇒ *query-first* protocol:
  reconcile by client-ID against broker order book before any retry; if unresolvable in 30 s ⇒
  page + freeze instrument (never blind-retry into a possible double fill).
- **Order groups:** entry + stop-loss + targets managed as an atomic group with declared
  bracket/OCO semantics; where the broker lacks server-side OCO, OMS emulates and the *protection
  leg always exists broker-side* (§7).
- Every transition is an `exec.order.evt` — the audit and TCA source.

## 3. Execution algorithms (exec-agent)

| Situation | Algo |
|---|---|
| Size ≪ touch liquidity, tight spread | Passive limit at zone edge; reprice on tape drift ≤ max_chase |
| Zone filling fast / momentum entry | Marketable limit with price collar (never naked market orders) |
| Size vs liquidity high (capacity cap near) | Slice: TWAP/POV (≤ 8% of 1-min volume P), iceberg where venue supports |
| Crypto multi-venue | Smart order routing across approved venues by top-of-book + fees + our inventory; per-venue caps (05 §5) |
| Options (spreads) | Leg-risk-managed: ratio-guarded legging with abort-and-flatten rule, or native basket/spread orders where available; max leg exposure window 5 s (P) |
| Exits on stop trigger | Pre-staged; stop-limit with protective offset + market fallback on breach-through (venue-dependent; NSE options: SL-M unavailable — protective-offset limit ladder instead) |

Participation caps, collars, and chase limits are risk-registry values; exec-agent cannot exceed
them (kernel re-validates on any modification). An **order-rate governor** (token bucket per
broker and per venue) keeps the platform inside broker API limits and below the SEBI
algo-registration threshold with headroom: default **≤5 orders/s and ≤150/min per client** (P) —
half the verified 10-OPS threshold ([09 §3.1](09-VALIDATION-REVIEW.md)). Slicing is
**exchange freeze-quantity aware**: parent orders auto-split below the per-order freeze limit,
and the governor paces the children.

## 4. Broker & venue adapter layer

**Uniform adapter contract:** `place / modify / cancel / cancel_all(scope)`,
`orders() / positions() / margins() / fills_stream()`, `health()`, `capabilities()`
(order types, OCO/GTT support, rate limits, lot/tick rules), `clock()`.

| Adapter | Venue | Notes |
|---|---|---|
| kite | NSE/NFO/MCX via Zerodha | Primary India. Daily interactive login is a human pre-open step (01 §11 — automation is against stated broker policy); postbacks + polling reconciliation; GTT CRUD API used for dead-man protection; 5-level depth WS (3,000 instr × 3 conns/key) |
| dhan | NSE/NFO/MCX | Failover India (07 §5); kept warm with mirrored watchlists; also serves the 20-level depth feed (NSE EQ+NFO focus set) and a dedicated order-update WebSocket; Forever/OCO orders |
| binance / bybit | Crypto spot + perps | Native WS user streams; exchange-native OCO/reduce-only used |
| delta-india | Crypto derivatives (India-compliant option) | Policy-gated (00 §11) |
| sim | All venues | Fill/latency models calibrated from our TCA data; used by twin/paper |

**India compliance notes (verified 2026-07, [09 §3.1](09-VALIDATION-REVIEW.md)):** SEBI retail-algo
framework fully binding since Apr 2026. Mechanics: order-placement APIs only from a **static IP
whitelisted per API key**; **≤10 orders/sec per client** ⇒ generic exchange algo-ID, no strategy
registration; >10 OPS ⇒ registration via broker + strategy algo-ID. Zerodha hard-enforces 10 OPS
(HTTP 429) and caps slicing at 10. **ATIS default = under-threshold path**: governor at ≤5
orders/s (§3), generic tagging, static-IP VPS deployment, broker's written concurrence at P0.
Human-confirmed P2 orders are likely non-"algo" (to be confirmed with broker, not assumed).
Complete audit trail (DecisionRecords + broker logs), 5-year retention. Additional venue rules
encoded per adapter: F&O ban-list rejection, expiry-day auto-square-off cutoffs and delivery-
margin ramps from E-4 (physical settlement), peak-margin snapshots, MCX session calendars,
crypto venue maintenance windows.

## 5. Broker health & failover

- **Probes:** heartbeat + synthetic read call every 10 s; latency/error budgets per adapter
  (p99 ack > 2 s or error rate > 5%/min ⇒ DEGRADED).
- **Failover policy (India):** primary DEGRADED ⇒ no new entries via primary; protection orders
  for *open positions* placed/verified on the account's existing broker (positions don't move
  brokers) — so failover for protection means: if primary API is down but exchange is up,
  attempt via primary's alternate channels (API retry, then GTT already resting, then manual
  console alert with pre-formatted order tickets). True dual-broker failover applies to *new*
  activity only. This asymmetry is explicit and drilled.
- **Crypto:** per-venue independent; venue DEGRADED ⇒ routing excludes it; open exposure there
  managed by resting reduce-only stops (always present).
- Broker scorecards (fill quality, rejects, latency, downtime) feed venue selection and the
  quarterly broker review.

## 6. P3 safety pipeline (pre-flight, every order, all must pass in < 150 ms)

1. Kill switches clear (all levels for scope)
2. Mode = P3 for market, plan not expired, entry zone still valid vs LTP
3. Risk verdict fresh (< 60 s) and unchanged inputs (re-check delta if stale)
4. Internet/route health (dual egress check)
5. Exchange session open, not in auction/halt; instrument not banned/circuit-locked
6. Broker adapter HEALTHY; rate budget available
7. Margin re-check with live SPAN/exposure (or venue equivalent)
8. Daily order budget + daily loss ladder state permit
9. Protection leg pre-staged and accepted logic verified (bracket/GTT path confirmed)
10. DecisionRecord persisted (no record ⇒ no order — hard invariant)

Any failure ⇒ order not sent, reason logged, and (by failure class) instrument/market auto-pause
with notification. The pipeline itself is C0 Rust, property-tested.

## 7. Position protection & the dead-man design

- **Invariant:** every open position has live broker-side protection (stop-loss order, GTT, or
  reduce-only stop on crypto) at all times — placed *in the same action group* as the entry fill,
  verified by recon within 30 s, re-verified continuously.
- Synthetic (platform-managed) stops may *tighten* management, but the broker-side backstop
  never lifts while the position lives. Modifications are replace-then-verify, never
  cancel-then-place.
- Overnight: positional protection is GTT/AMO-refreshed after session ops; expiry-week ITM
  options are auto-squared before cutoffs (cost model covers the STT trap); stock F&O obeys the
  delivery-window guard (05 §3.16) with forced-flatten plans generated at T-4.
- Corporate-action ex-dates: protective orders on affected instruments are re-based per
  instrument-master flags (03 §4.1) before the ex-date open — un-rebased stops around ex-dates
  either misfire or die silently.
- Result: total platform death (power, cloud, code) leaves a book that liquidates itself at
  known worst-case prices — this is the last line of the failure matrix (01 §13).

## 8. TCA (tca-svc)

Per fill: implementation shortfall vs decision price and vs arrival price; slippage vs model;
spread capture; participation achieved; venue/broker attribution; queue-jump analysis (crypto).
Outputs: (a) execution dashboards, (b) calibration data for sim fill models (06 §6), (c) monthly
execution review with algo-mix recommendations, (d) per-strategy cost curves feeding EV_net
(04 §5) — costs are not an afterthought; they are in every EV before any trade.

## 9. Reconciliation (recon-svc)

- **Continuous:** fills stream vs OMS state (each fill matched < 5 s); positions & margins
  snapshot vs broker every 5 min; protection-order presence check every 30 s.
- **EOD:** positions, cash, charges vs broker contract note & bhavcopy-derived valuations;
  crypto: venue account statements vs internal ledger. **Ledger reconciliation** covers T+1
  sale-proceeds availability, blocked vs free margin, and MTM debits — margin checks (05 §3.9)
  always use *available* funds, never raw balance.
- **Break handling:** any mismatch ⇒ instrument freeze + P1 page + runbook; unexplained breaks
  block the next session's trading for that scope (fail-closed). Breaks and resolutions are
  audit events with root-cause tags (broker bug vs our bug vs timing).

## 10. Failure recovery playbooks (drilled quarterly, 08 §9)

| # | Scenario | Automatic behavior | Human runbook |
|---|---|---|---|
| R1 | Process/OMS crash | Restart → journal replay → **reconcile-before-trade** (01 §13 startup sequence) | Verify recon report, release freeze |
| R2 | Broker API down, positions open | Protection already resting broker-side; no new orders; probe loop | Broker terminal/phone desk as manual fallback (pre-formatted tickets on console) |
| R3 | Exchange halt / circuit | Freeze scope; re-plan on reopen with gap logic (no stale plans fire) | Review reopen plans before un-freeze (P2) |
| R4 | Submit timeout (AMBIGUOUS) | Query-first protocol (§2); freeze on unresolved | Resolve via broker order book; document |
| R5 | Feed dead but broker alive | No new entries; manage on protection; attempt vendor failover | Decide flatten vs hold per health |
| R6 | Bus/platform partial outage | Fail-closed per component (01 §13); dead-man invariant holds | Restore order: data → risk → OMS → agents |
| R7 | Crypto venue freeze/withdrawal halt | Venue excluded; exposure there marked stressed; hedge on alternate venue if delta breach | Assess counterparty action; incident report |
| R8 | Fat-finger/duplicate suspicion | Kernel collars + idempotency prevent; any anomaly ⇒ L1 switch | Post-incident audit mandatory |

## 11. Execution observability

Dashboards: live order blotter with state ages; ack/fill latency percentiles; reject/cancel
rates; slippage vs model (rolling); protection-coverage status (the dead-man invariant, green/red
per position); broker health; rate-budget consumption; recon status. Pages (P1): unprotected
position > 30 s, AMBIGUOUS > 30 s, recon break, adapter DEGRADED with open positions, safety-
pipeline auto-pause.

## 12. Open questions for review

1. Manual-fallback policy when broker API is down but you can trade via broker terminal: should the platform *advise* manual orders (pre-formatted tickets, proposed) or stay silent?
2. GTT-as-dead-man on Zerodha vs plain SL orders (GTT survives sessions but isn't margin-blocked; SL is firm but daily): proposal = GTT for positional, SL orders intraday. Confirm.
3. P2 approval channel: console-only, or Telegram inline-approve too (convenience vs security trade-off — recommend console-only for order approval, Telegram for notify)?
4. Crypto smart-order-routing across venues in v1, or single-venue-per-instrument to start (simpler recon — recommended)?
