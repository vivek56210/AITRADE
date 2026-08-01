# 01 · System Architecture

> **ATIS Design Doc 01 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [00-VISION](00-VISION.md) · Downstream: all subsystem docs (02–07)

---

## 1. Overview

ATIS is an **event-driven, event-sourced system of six planes** riding a single durable event bus.
Every fact the platform ever observes or decides is an immutable event; every service is a
consumer/producer with an explicit contract; the entire platform can be replayed deterministically
from the log (this is what makes the digital twin, the audit trail, and backtest/live parity the
*same mechanism* rather than three features).

```
┌───────────────────────────────  CONTROL PLANE  ───────────────────────────────┐
│  mode-manager · limits-registry · kill-switch-svc · config-svc · audit-log    │
│  (governs everything below; all state changes are audited events)             │
└───────▲───────────────▲───────────────────▲──────────────────▲────────────────┘
        │               │                   │                  │
┌───────┴──────┐ ┌──────┴────────┐ ┌────────┴────────┐ ┌───────┴────────┐
│  DATA PLANE  │ │ INTELLIGENCE  │ │  DECISION PLANE │ │ EXECUTION PLANE│
│              │ │    PLANE      │ │                 │ │                │
│ connectors   │ │ perception    │ │ confidence eng. │ │ OMS            │
│ normalizer   ├▶│ agents        ├▶│ opportunity     ├▶│ exec algos     │
│ dq-sentinel  │ │ regime/health │ │ ranker          │ │ broker         │
│ bar/profile  │ │ news/sent NLP │ │ trade committee │ │ adapters       │
│ builders     │ │ options intel │ │ trade planner   │ │ safety pipeline│
│ feature-eng  │ │ knowledge     │ │ RISK KERNEL     │ │ TCA · recon    │
│ feature store│ │ graph         │ │ portfolio mgr   │ │                │
└──────▲───────┘ └───────────────┘ └─────────────────┘ └───────┬────────┘
       │                                                       │ fills/outcomes
       │              ┌──────────  LEARNING PLANE  ──────────┐ │
       └──────────────┤ outcome-tracker · attribution        │◀┘
                      │ review agent · drift monitors        │
                      │ research workbench · model registry  │
                      │ digital twin / replay                │
                      └──────────────────────────────────────┘

            All planes publish/subscribe via the EVENT BUS (Redpanda/Kafka).
            Nothing bypasses the bus except intra-plane hot caches.
```

## 2. Architectural principles

1. **Event-sourced core.** The bus is the system of record for *what happened*; databases are
   projections. Rebuild any view by replay.
2. **Single writer per aggregate.** Exactly one service owns writes for each domain object
   (OMS owns orders, risk-kernel owns verdicts, mode-manager owns modes). No shared-write tables.
3. **Deterministic replay = parity.** The engine consumes events identically whether they come
   from live connectors, the replayer, or the simulator. Backtest, paper, and live are deployment
   configurations, not separate codebases.
4. **Hot path is LLM-free.** LLM-backed agents run out-of-band and publish TTL'd Evidence; the
   decision path consumes their *latest published* output and never blocks on them (02 §7).
5. **Independent risk kernel.** Deterministic, C0-critical, minimal dependencies, sized to be
   auditable line-by-line. It subscribes to plans and portfolio state, and nothing can suppress
   its verdicts.
6. **Idempotent side effects.** Every order command carries a deterministic idempotency key;
   retries can never double-submit (07 §2).
7. **Config is versioned data.** All parameters, limits, thresholds live in the limits/config
   registry (git-backed, checksummed, hot-reloaded with audit events). No magic numbers in code.
8. **Degrade to safety.** Any component failure maps to a defined degraded behavior whose
   worst case is "stop trading, protect positions" — never "keep trading blind" (§13).

## 3. Plane & service decomposition

Criticality: **C0** never wrong (correctness > availability), **C1** trading halts without it,
**C2** quality degrades, **C3** offline/batch. Languages: **Py** Python 3.12, **Rs** Rust
(fallback Go), **TS** TypeScript.

### Data plane

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| md-connector-{venue} | One per venue (kite-ws, dhan-ws, binance-ws, bybit-ws, delta-ws, mcx-via-broker): raw feed → `md.raw.*`, heartbeats, gap/sequence tracking | C1 | Rs |
| news-connector | Exchange announcements, RSS, filings, calendars → `intel.news.raw` | C2 | Py |
| social-connector | X/Reddit/Telegram/YouTube collectors → `intel.social.raw` | C2 | Py |
| onchain-connector | On-chain metrics, funding, liquidations, whale/stablecoin flows | C2 | Py |
| normalizer | Raw → canonical schemas (03 §4), symbology mapping, timestamp discipline | C1 | Rs |
| dq-sentinel | Data Quality Engine: validation, scoring, quarantine, halt signals (03 §5) | C1 | Rs |
| bar-builder | Canonical ticks → bars (1s→1d), session logic per venue calendar | C1 | Rs |
| profile-builder | Market/volume profiles (session + composite), VWAP suite | C1 | Py |
| feature-engine | Streaming feature computation → online store + `feat.*` topics | C1 | Py |
| feature-store | Feast: offline (lake) + online (Redis) feature serving, PIT-correct | C1 | Py |
| archiver | Bus → lake (Parquet/Iceberg) continuous archival, replay source | C1 | Py |

### Intelligence plane (agents detailed in 02)

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| agent-runtime | Hosts quantitative perception agents (liquidity, profile, order-flow, structure…) as supervised workers with a uniform contract | C1 | Py |
| regime-svc | Market Regime Agent: HMM + classifier ensemble + BOCPD | C1 | Py |
| health-svc | Market Health Engine: composite tradability score & gates (05 §9) | C1 | Py |
| news-nlp | Dedup, entity-link, classify, score news (LLM + classic ensemble) | C2 | Py |
| sentiment-nlp | Social/sentiment scoring pipelines | C2 | Py |
| options-analytics | Chain analytics: OI/ΔOI, PCR, IV surface, IVR/IVP, max pain, GEX | C2 | Py |
| kg-svc | Knowledge graph API + nightly relationship recompute (03 §8) | C2 | Py |

### Decision plane

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| confidence-engine | Evidence aggregation → calibrated confidence (02 §5) | C1 | Py |
| opportunity-ranker | Scores & ranks opportunities, top-K selection (04 §6) | C1 | Py |
| trade-committee | Orchestrates plan → contra-case → risk → governance sequence (02 §4) | C1 | Py |
| trade-planner | Builds full TradePlans from opportunities (04 §7) | C1 | Py |
| **risk-kernel** | Pre-trade checks, sizing caps, vetoes, drawdown governor (05) | **C0** | Rs |
| portfolio-svc | Positions, exposures, Greeks, correlation state (05 §5) | C0 | Py→Rs |
| allocation-svc | Capital/risk budgets per strategy (05 §6) | C1 | Py |

### Execution plane (detailed in 07)

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| oms | Order state machine, idempotency, journal | **C0** | Rs |
| exec-agent | Algo selection, slicing, venue routing, live trade management executor | C0 | Rs |
| broker-adapter-{broker} | kite, dhan, binance, bybit, delta…: uniform adapter contract | C0 | Rs |
| safety-pipeline | P3 pre-flight checks (10-point) + auto-pause triggers | **C0** | Rs |
| tca-svc | Slippage/implementation-shortfall analytics → learning | C2 | Py |
| recon-svc | Continuous + EOD reconciliation vs broker truth | C0 | Py |

### Learning plane (detailed in 06)

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| outcome-tracker | Labels every plan/trade/no-trade with outcomes, MAE/MFE | C2 | Py |
| attribution-svc | PnL decomposition: signal, timing, sizing, execution, luck | C3 | Py |
| review-agent | Automated post-trade/daily/weekly review documents | C3 | Py |
| drift-monitor | Feature/concept/performance drift detection | C2 | Py |
| research-workbench | Sandboxed research env + experiment tracking | C3 | Py |
| model-registry | MLflow: models, prompts, detector versions, promotion state | C1 | Py |
| twin-svc | Replayer + scenario generator + paper environment | C1 | Py |

### Control plane

| Service | Purpose | Crit | Lang |
|---|---|---|---|
| mode-manager | Per-market mode state machine (P1/P2/P3), 2-step confirmation | **C0** | Rs |
| limits-registry | Versioned limits/thresholds, checksummed, hot-reload with audit | **C0** | Rs |
| kill-switch-svc | 4-level kill switches; trip = instant, reset = human + checklist | **C0** | Rs |
| config-svc | Non-limit config distribution, feature flags | C1 | Py |
| audit-log | Append-only hash-chained DecisionRecords + control events | **C0** | Rs |
| ops-console | Web UI: dashboards, approvals (P2), kill switches, mode control | C1 | TS |
| notifier | Telegram/email/push for recommendations & alerts | C1 | Py |

~35 logical services. **Deployment note:** v1 collapses these into ~10–12 processes (e.g., one
`agent-runtime` hosts many agents; one `data-spine` binary hosts connector+normalizer+dq per
venue). Logical boundaries stay intact so services can be split out when scale demands.

## 4. Event backbone

**Broker:** Redpanda (Kafka-compatible, single-binary ops). Schema registry with **Protobuf**
schemas, backward-compatible evolution enforced in CI.

### Envelope (all topics)

```json
{
  "event_id":      "01J9XW…  (ULID, unique, time-sortable)",
  "schema":        "atis.md.bar.v2",
  "ts_event":      "2026-07-11T09:15:00.412Z  (source time)",
  "ts_ingest":     "…  (platform receive time)",
  "producer":      "bar-builder@2.3.1",
  "key":           "NSE:RELIANCE  (partition key)",
  "correlation_id":"plan_01J9… (traces a decision chain)",
  "causation_id":  "event that directly caused this one",
  "payload":       { }
}
```

### Topic taxonomy

| Topic family | Content | Partition key | Retention |
|---|---|---|---|
| `md.raw.{venue}` | Feed as received (opaque) | instrument | 7 d (lake has forever) |
| `md.tick.{market}` / `md.depth.{market}` | Canonical ticks/depth | instrument | 7 d |
| `md.bar.{tf}` | 1s/1m/5m/15m/1h/1d bars | instrument | 30 d |
| `md.chain.{underlying}` | Option chain snapshots | underlying | 7 d |
| `intel.news.raw` / `intel.news.scored` | News pipeline | entity | 90 d |
| `intel.social.raw` / `intel.sentiment.scored` | Sentiment pipeline | entity | 30 d |
| `intel.onchain.*` / `intel.macro.events` | Crypto & macro intel | asset/event | 90 d |
| `state.market` | MarketState updates | instrument | 7 d |
| `state.regime` / `state.health` | Regime & health | market | 30 d |
| `signal.evidence` | Evidence objects from all agents | instrument | 30 d |
| `signal.opportunity` | Scored opportunities (incl. rejected — for learning) | instrument | 90 d |
| `decision.plan.*` | proposed / contra / verdict / approved | plan_id | ∞ (compacted to PG+lake) |
| `risk.verdict` / `risk.alert` | Risk kernel outputs | plan_id/scope | ∞ |
| `exec.order.cmd` / `exec.order.evt` / `exec.fill` | Order flow | order_id | ∞ |
| `portfolio.snapshot` | Positions/exposures (1 Hz + on change) | book | 30 d |
| `learn.outcome` / `learn.review` / `learn.drift` | Learning plane | plan_id | ∞ |
| `ops.heartbeat` / `ops.mode` / `ops.kill` / `ops.audit` | Control | service/scope | ∞ |

Ordering is guaranteed per partition key only — all consumers MUST tolerate cross-key reordering.
Consumers are idempotent by `event_id`.

## 5. Canonical domain objects

Full field lists live in the owning docs; shapes here are the contract. All objects carry
`schema`, `version`, `ts`, and IDs linking the chain: Evidence → Opportunity → TradePlan →
RiskVerdict → DecisionRecord → Orders → Fills → Outcome.

```jsonc
// Evidence (02 §2) — the atomic unit of market opinion
{ "evidence_id": "…", "agent": "liquidity@1.4.0", "instrument": "NFO:NIFTY-FUT",
  "type": "liquidity_sweep", "direction": "long", "p": 0.63,        // calibrated
  "valid_until": "…", "features_ref": "…", "provenance": ["event ids"],
  "detector_validation_ref": "vreg://liquidity_sweep/1.3" }

// MarketState (04 §3) — per instrument, continuously updated
{ "instrument": "…", "regime": {"trend":0.61,"range":0.24,"volatile":0.15},
  "structure": {"bias":"up","last_bos":…,"swings":[…]},
  "profile": {"poc":…, "vah":…, "val":…, "ib":…, "acceptance":"inside_value"},
  "liquidity": {"pools_above":[…],"pools_below":[…]},
  "flow": {"cvd_slope":…, "absorption":null}, "vol": {"rv":…, "atr":…},
  "health": 0.82, "data_quality": 0.999, "narratives": ["news ids"] }

// TradePlan (04 §7) — everything needed to act and to explain
{ "plan_id":"…","strategy":"nifty_sweep_reversal@2.1.0","instrument":"…","side":"long",
  "entry":{"style":"limit_zone","zone":[22412,22428],"max_price":22436},
  "stop":{"price":22368,"basis":"beyond_sweep_extreme"},
  "targets":[{"price":22492,"size_pct":50,"basis":"POC"},{"price":22561,"size_pct":50,"basis":"VAH"}],
  "size":{"qty":150,"risk_R":9000,"risk_pct":0.36,"caps_applied":["kelly","liquidity"]},
  "horizon":"intraday","confidence":0.67,"p_win":0.58,"rr_t1":1.9,"ev_net_R":0.31,
  "reasoning":{"thesis":"…","evidence":[…],"contra":[…],"invalidation":"…","alternatives":[…]},
  "mode":"P2","management_policy":"range_reversal_v3" }

// RiskVerdict (05 §3) — deterministic, reasoned
{ "verdict":"APPROVE_RESIZED","plan_id":"…","adjustments":{"qty":120},
  "checks":[{"check":"max_order_value","pass":true},…], "risk_state_ref":"…" }

// DecisionRecord (audit) — immutable, hash-chained
{ "record_id":"…","plan":{…},"evidence_bundle":[…],"contra_case":{…},
  "risk_verdict":{…},"governance":{"agent":"pass","human":null},
  "agent_versions":{…},"config_checksum":"…","prev_hash":"…","hash":"…" }
```

## 6. Storage architecture

| Store | Role | Holds | Retention |
|---|---|---|---|
| Redpanda | Transport + short-term replay | All topics | 7–90 d per §4 |
| S3/MinIO + Parquet/**Iceberg** | Data lake — permanent system of record | Every event, archived by `archiver`; research datasets | Forever |
| **ClickHouse** | Time-series analytics | Ticks/bars/chains/features/outcomes for fast query | 2 y hot, rest in lake |
| **Postgres 16** | OLTP + registries | Plans, orders, verdicts, limits registry, strategy/detector registries, DecisionRecords index; `pgvector` for narrative embeddings (v1) | Forever |
| **Redis** | Hot state | Online features, MarketState cache, dedup sets, rate budgets | Ephemeral |
| **Neo4j** (community) | Knowledge graph | Entities & relationships (03 §8) | Forever |
| MLflow (on PG+lake) | Model/prompt registry | Models, detector versions, eval runs | Forever |
| DuckDB | Research access layer | Reads lake Parquet directly, zero-infra analytics | n/a |

Backups: PG WAL-shipped (RPO ≤ 5 min); lake is append-only + versioned; ClickHouse rebuildable
from lake (it is a projection, not a source of truth).

## 7. Environments & deterministic replay

| Env | Feed source | Execution | Purpose |
|---|---|---|---|
| dev | Golden-day fixtures | Sim | Development, CI |
| research | Lake (batch) | Vectorized + event sim | Strategy research (04 §9) |
| **sim/twin** | Replayer (lake → bus, original timing or accelerated) | Sim broker with fill/latency models | Validation, stress, chaos — same containers as prod |
| paper | **Live** feeds | Sim broker | Forward test under real data imperfections |
| prod | Live feeds | Real brokers | P1/P2/P3 |

Golden-day regression: a fixed library of recorded sessions (trend day, range day, expiry, crash
day, crypto weekend illiquidity…) replayed in CI; decision outputs must match pinned snapshots
bit-for-bit unless a version bump explains the diff.

**Replay isolation:** side-effect command topics (`exec.order.cmd`) are environment-scoped, and
live broker adapters exist only in prod and subscribe only to prod-scope commands — a replayed
or twin-originated command physically cannot reach a real broker.

## 8. Latency tiers

| Tier | Path | Budget (p99) | Notes |
|---|---|---|---|
| T0 | venue → canonical tick on bus | ≤ 50 ms | broker WS bound |
| T1 | tick → MarketState update | ≤ 250 ms | streaming aggregation |
| T2 | evidence → committee decision | ≤ 5 s | LLM agents excluded (async, TTL'd) |
| T3 | approved plan → broker ack | ≤ 300 ms + broker | idempotent submit |
| T4 | learning/attribution | minutes–daily | batch |

## 9. Technology stack (recommendation + rationale)

| Concern | Choice | Why | Deferred alternative |
|---|---|---|---|
| Agent/research language | Python 3.12 (pydantic v2, polars, numpy) | ML ecosystem, velocity | — |
| Hot-path language | Rust | Determinism, no GC pauses in OMS/risk/md path | Go (faster to hire/write) |
| UI | TypeScript + React | Ops console, approvals | — |
| Bus | Redpanda | Kafka API without ZK/JVM ops burden | Kafka (MSK) at scale |
| Stream processing | Custom consumers + Bytewax where windowed | Team-sized; Flink is overkill v1 | Flink when >10⁶ events/s |
| TS store | ClickHouse | Best query-speed/ops ratio for market data | QuestDB (ingest-optimized) |
| OLTP | Postgres 16 + pgvector | Boring, correct, vectors included | Qdrant if vector load grows |
| Lake | MinIO/S3 + Parquet + Iceberg | Cheap forever-storage, schema evolution, time travel | Delta Lake |
| Feature store | Feast (lake offline / Redis online) | PIT-correct serving without building it ourselves | Custom thin layer |
| Graph | Neo4j Community | Mature Cypher, small ops footprint | ArangoDB, Apache AGE |
| Orchestration | Dagster | Asset-centric fits data/ML pipelines; great local dev | Prefect |
| Distributed compute | Ray | Parallel backtests, tuning, MC sims | Dask |
| Model registry | MLflow | Standard, self-hosted | W&B (hosted) |
| Backtest/live chassis | **Phase-0 spike decision (P0-D1):** NautilusTrader (Rust core, event-driven, backtest/live parity, crypto adapters exist) vs in-house core | Buy parity if adapter cost for Indian brokers is acceptable | In-house event core |
| LLM | Claude family via API — `claude-fable-5` (deep research/review), `claude-sonnet-5` (news/sentiment scoring), `claude-haiku-4-5` (bulk classification) | Tiered cost/quality; structured outputs | Behind a provider-agnostic gateway |
| Brokers (India) | Zerodha Kite Connect (primary) + Dhan (failover) | API maturity + true failover pair | Fyers, Angel One |
| Venues (crypto) | Binance, Bybit, Delta Exchange India (policy-gated, 00 §11) | Liquidity + India-compliant option | Coinbase |
| Data vendor (India) | TrueData or Global Datafeeds (tick + backfill + greeks) — Phase-0 decision P0-D2 | Broker WS alone caps detector tier | — |
| Infra | Docker Compose (P0) → k3s single node → k3s HA | Grow only when needed | Managed k8s |
| IaC / secrets | Terraform + SOPS/age (P0) → Vault | Right-sized | — |
| Observability | OpenTelemetry + Prometheus + Grafana + Loki | Standard LGTM stack | — |

## 10. Scalability plan

**v1 design load (envelope):** ~300 NSE instruments + ~40 option underlyings (1 s chain
snapshots) + 50 crypto pairs (conflated L2) + 20 MCX contracts ⇒ ~50–150 M events/day, single-digit
GB/day canonical. One beefy node handles this; the ceilings and levers:

- **Partitioning axis is the instrument.** Every hot-path service scales horizontally by
  partition assignment; adding consumers = rebalancing, no code change.
- **Stateless where possible**; stateful services (bar-builder, profile-builder) keep state in
  RocksDB/Redis keyed by instrument → shard freely.
- **Backpressure policy:** enrichment (sentiment, news depth) sheds first; canonical md, state,
  risk, and OMS **never shed** — they alert and, if lag exceeds budget, trip the market-level
  kill switch (stale-data trading is worse than no trading).
- **ClickHouse/lake scale independently** of the trading path (projections).
- Capacity re-planning trigger: sustained bus throughput > 40% of measured single-node ceiling.

## 11. Security architecture

- **Zones:** (a) execution zone — OMS, adapters, risk-kernel, safety-pipeline; broker/exchange
  API keys exist *only* here, held in memory from Vault/SOPS at boot; (b) intelligence/data zone —
  no credentials capable of placing orders; (c) ops zone — console behind VPN + 2FA;
  (d) research zone — read-only lake access, no prod credentials.
- **Least privilege:** broker API keys scoped where brokers allow; separate read-only keys for
  recon; LLM API keys rate- and budget-capped.
- **Kite daily-token flow:** brokers require a daily interactive login (request_token + TOTP),
  and Zerodha's stated position discourages automating it. **Design default (v0.2): the daily
  login is a human pre-open ritual step** (08 §9) — ~30 seconds/day; the platform alerts if no
  valid session exists before market open. TOTP automation is kept only as a documented
  contingency, not the operating mode; the broker's written stance is a P0 onboarding item (08 §2).
- **Audit integrity:** DecisionRecords hash-chained; daily chain-head hash exported to an
  external write-once location.
- **Supply chain:** locked dependencies, image scanning, no dynamic plugin loading in execution zone.
- **Network:** deny-by-default egress; connectors have per-venue allowlists.
- **Secrets rotation:** quarterly + on any suspicion; drill in ops calendar (08 §9).

## 12. Observability

- **OpenTelemetry everywhere**; `correlation_id` from evidence → plan → order → fill gives
  end-to-end decision traces.
- **Golden signals per plane:** data (feed lag, gap count, DQ score), intelligence (evidence
  freshness, agent heartbeat, calibration drift), decision (committee latency, abstention rate,
  veto rate), execution (ack latency, reject rate, slippage vs model, recon breaks), learning
  (outcome lag, drift alarms), control (mode changes, kill events).
- **SLOs (P):** feed lag p99 < 1 s; MarketState staleness < 2 s; committee cycle < 5 s;
  recon cycle < 5 min; DQ clean-rate ≥ 99.9%.
- **Alert matrix:** P1-page = kill-switch trip, recon break, order stuck in ambiguous state,
  in-session feed gap, drawdown-ladder trip, safety-pipeline auto-pause. P2 = agent degraded,
  calibration drift, DQ downgrade. P3 = batch failures.
- **Flight recorder:** last 24 h of all topics always replayable locally in one command — the
  first responder tool for "why did it do that?"

## 13. Failure modes & recovery matrix

| Failure | Detection | Automatic response | RTO |
|---|---|---|---|
| Bus down | Producer errors, heartbeat loss | Trading halted (fail-closed); OMS journals locally; positions protected by broker-side stops (07 §7) | < 15 min |
| Feed gap (one venue) | Sequence/heartbeat gap | Instrument/market marked stale → no new entries; existing positions managed on last-good + protective stops | auto |
| dq-sentinel downgrade | Quality score < threshold | Data-tier downgrade → dependent detectors disabled; below floor → market halt | auto |
| Broker API down | Adapter probes fail | Failover to secondary broker for *new* protection orders; no new entries; alert | < 5 min |
| Risk-kernel crash | Heartbeat | **All trading halts** (C0 fail-closed); supervisor restart; state rebuilt from PG + bus replay | < 2 min |
| LLM API down | Gateway errors | LLM-backed evidence goes stale → TTL expiry → confidence caps / event-window entry blocks; quant path unaffected | auto |
| Process crash (any) | Supervisor | Restart; consumers resume from committed offsets; OMS replays journal then **reconciles with broker before any new order** (07 §10) | < 1 min |
| Postgres down | Health check | No new plans (can't record decisions ⇒ don't decide); open-position management continues from journal | < 15 min |
| Clock skew > 250 ms | NTP sentinel | Trading pause (timestamps are load-bearing) | auto |
| Node/DC loss | Uptime probes | DR restore from lake + PG replica (08 §11); positions safe via broker-side stops (dead-man design) | ≤ 4 h |
| Internet loss at ops site | — | Platform is cloud-hosted (Mumbai region); ops loses *dashboards*, not the platform; broker-side stops as last resort | n/a |

Startup safety sequence (always): reconcile broker state → rebuild journal → verify limits/mode
checksums → resume data → arm risk kernel → only then accept new plans.

## 14. Control plane

- **mode-manager:** per-market mode (P1/P2/P3) state machine; transitions need two-step
  confirmation + gate checklist reference; every change is an audit event. Downgrades are instant
  and unilateral.
- **limits-registry:** every limit/threshold in versioned YAML (git-backed), checksummed;
  services refuse to start on checksum mismatch; hot reload emits audit events. The registry is
  the single place where the numbers marked (P) throughout these docs live.
- **kill-switch-svc:** 4 levels — L1 instrument, L2 strategy, L3 market, L4 platform. Trip
  sources: any human (one click, no confirmation), risk-kernel (automatic on ladder/limit
  breach), safety-pipeline, dq-sentinel. Trip action: cancel resting entry orders, block new
  plans, optionally flatten (policy per level), notify. **Reset requires human + written
  checklist.**
- **audit-log:** append-only, hash-chained; stores DecisionRecords and all control-plane events;
  the compliance artifact for SEBI algo record-keeping (5-year retention, 08 §10).

## 15. Open questions for review

1. **P0-D1 (chassis):** NautilusTrader adapter spike vs in-house event core — any prior preference?
2. **P0-D2 (India data vendor):** TrueData vs Global Datafeeds vs broker-only start (caps order-flow detectors to Tier C)?
3. Rust vs Go for the hot path — Rust proposed; Go acceptable if hiring/velocity matters more.
4. Cloud (AWS ap-south-1 / GCP mumbai) vs owned bare metal for prod?
5. Single primary broker = Zerodha with Dhan failover — agree, or different pair?