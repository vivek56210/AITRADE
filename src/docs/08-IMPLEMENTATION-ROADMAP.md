# 08 · Implementation Roadmap, Testing, Governance & Operations

> **ATIS Design Doc 08 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: all docs. This one turns the architecture into a build sequence with gates.

---

## 1. Delivery philosophy

- **Thin vertical slices:** every phase ends with the *whole loop* running (data → state →
  decision → record → learn) at increasing depth — never "we'll integrate later."
- **Sim-first:** the twin/paper environments are built *before* the intelligence that needs them.
- **Gates, not dates:** durations below are estimates; the exit gates are the contract. A phase
  that misses its gate does not advance because the calendar says so.
- **Buy vs build:** chassis spike (P0-D1), Feast, MLflow, Redpanda, Neo4j = buy/adopt;
  detectors, risk kernel, committee, adapters (India) = build.
- Assumed team: 1–2 engineers + AI-assisted development + you as PM/risk owner. (Confirm.)

## 2. Phase 0 — Foundations (≈ 6–8 weeks)

**Build:** repo + CI + IaC; bus + schema registry; instrument master; md-connector (Kite) +
normalizer + dq-sentinel v1; bar/profile builders; lake archiver + replayer (golden days
captured immediately); ClickHouse/PG/Redis up; ops-console skeleton; notifier; limits-registry +
config + audit-log v1; **chassis spike (P0-D1)** and **vendor decision (P0-D2)**; historical-backfill procurement +
load kick-off (critical path for P1 validation, 03 §10); broker onboarding checklist including
written confirmation of the API-automation stance and scoping of the SEBI algo-registration path.

**Exit gate G0:** replay any recorded session deterministically with bit-identical bars/profiles;
DQ engine demonstrably quarantines injected bad data; golden-day CI green; one week of continuous
live capture (NSE) with zero unexplained gaps.

## 3. Phase 1 — Recommendation Mode (≈ 10–14 weeks) → **P1 live**

**Build:** agent-runtime + perception v1 (structure, liquidity, profile, VWAP, regime, health);
order-flow agent for crypto (Tier A) and India per P0-D2; options-analytics v1 (chain, OI, IVR);
news pipeline v1 (exchange announcements + RSS + embargo calendar); confidence engine
(bootstrap weights); 2–3 seed strategies through full validation (04 §10) to PAPER; trade-planner
+ Devil's Advocate v1; risk kernel v1 (checks 1–15, ladder, sizing); DecisionRecords end-to-end;
console: recommendations with full reasoning + no-trade reasons; outcome-tracker incl. user
actions; paper auto-execution baseline; review-agent daily notes.

**Exit gate G1 (to build P2):** ≥ 60 sessions of live recommendations; calibration per the
hierarchical scheme (02 §5) — evidence-level ECE ≤ 0.05 on ≥ 5,000 instances **and**
decision-level calibration bootstrap-CI consistent with tolerance on ≥ 200 decisions (P1 simply
runs longer if samples don't exist yet — gates, not dates); paper expectancy > 0 with PF ≥ 1.2
on ≥ 80 paper trades; 100% decisions carry complete records; zero risk-check bypass incidents;
user-facing reasoning judged useful (your sign-off).

## 4. Phase 2 — Assisted Execution (≈ 8–10 weeks) → **P2 live**

**Build:** OMS + journal + idempotency; kite adapter (orders) + sim adapter parity; order
groups + protection invariant (dead-man); staging + one-click approval UX; recon-svc
(continuous + EOD); TCA v1; exec algos (passive/marketable/slicing v1); kill-switch drills
begin (monthly); dhan adapter warm.

**Exit gate G2 (to build P3):** ≥ 3 months P2 operation; ≥ 100 assisted executions;
execution error rate < 0.5%; zero unresolved recon breaks; realized slippage within 1.25× model;
protection invariant never violated > 30 s (audited); all R1–R8 playbooks drilled in twin at
least once; live expectancy > 0 net.

## 5. Phase 3 — Constrained Autonomy (≈ 8–12 weeks build + compliance-path dependent)

**Build:** safety pipeline (10-point); P3 mode plumbing + caps; crypto venue adapters live
(policy per 00 §11); India compliance route — **default Path A: under-threshold operation**
(≤5 orders/s governor, generic algo-ID, static-IP deployment, broker written concurrence;
verified framework details in [09 §3.1](09-VALIDATION-REVIEW.md)); Path B (exchange registration
via broker) only if order rates ever require it; chaos drills monthly; attribution v1;
drift monitors v1; allocation engine v1.

**Exit gate G3 (P3 on, smallest capital slice):** all G2 conditions still green; safety pipeline
property-tested + chaos-tested; dead-man drill passed ("pull the plug" in paper with live feeds);
India: compliance route confirmed in writing — Path A concurrence or Path B registration complete
(or India stays P2 while crypto goes P3); governance sign-off with written risk acceptance.

**Capital scaling gates thereafter:** slice grows stepwise (e.g., 5% → 10% → 25% → 50% of
allocated trading capital) only on: 30+ trades at current slice, expectancy > 0, no ladder trips
level ≥ 3, no safety-pipeline misses. Any hard-stop event resets one step down.

## 6. Phase 4+ — Depth & breadth (continuous)

MCX + commodity intelligence; fundamental agent + position-trade universe; sentiment expansion
(X paid tier decision); KG maturity (supplier/customer extraction); learning automation
(weight refits, meta-labeling); research-track items (06 §9); Flink/scale-out only when 01 §10
triggers fire; additional markets by the expansion contract (00 §5).

## 7. Workstream map (who builds what, by phase)

| Workstream | P0 | P1 | P2 | P3 |
|---|---|---|---|---|
| Data spine | connectors, DQ, bars, lake, replay | +chains, news, crypto feeds | +vendor tick (P0-D2 path) | +MCX, on-chain |
| Intelligence | — | perception v1, regime, health, news v1 | sentiment v1 | fundamental, commodity, crypto intel v2 |
| Decision | — | confidence, ranker, planner, DA, committee | — | allocation engine |
| Risk | registry, audit skeleton | kernel v1 (full checks + ladder) | portfolio-svc v1 | VaR/stress nightly, adaptive mult |
| Execution | sim adapter | paper autoexec | OMS, kite, recon, TCA, algos | safety pipeline, crypto venues, dhan live |
| Learning | golden days | outcomes, reviews, calibration | TCA feedback | attribution, drift, twin scenarios, research engine |
| Control/UX | console skeleton, notifier | recommendation UX | approval UX, kill drills | P3 dashboards, scaling gates |

## 8. Testing strategy

| Layer | Method |
|---|---|
| Detectors & analytics | Property-based tests (invariants: VA covers 70%±ε, swings alternate, CVD sums) + golden fixtures |
| Risk kernel & safety pipeline | Exhaustive unit + property tests; mutation testing; formal review of every change (C0 policy) |
| Determinism | Golden-day replay in CI — bit-identical outputs or version-explained diff (blocks merge) |
| Integration | Twin scenario suite (06 §10): trend/range/crash/expiry/gap/illiquid days |
| Execution | Sim-broker conformance suite per adapter (state machine, idempotency, AMBIGUOUS drills); testnet/paper venue runs |
| Chaos | Monthly: kill components mid-flow in twin; quarterly: full R1–R8 playbook rehearsal |
| Shadow | Every new model/agent version shadows ≥ 4 weeks before canary (06 §7) |
| Performance | Latency budget tests per tier (01 §8) under 2× design load |
| "No code until docs approved" | This doc set is the spec; PRs reference doc sections; departures require doc PRs first |

## 9. Operating model & rituals

| Cadence | Ritual |
|---|---|
| Pre-open (15 min) | Checklist: **broker session login (daily interactive TOTP — human step, 01 §11)**, DQ green, feeds live, calendars loaded, embargo list, limits checksum, broker health, yesterday's recon closed |
| EOD (15 min) | Auto-generated review read; recon confirm; outcome labels sanity check |
| Weekly (2 h) | Research council: review-agent synthesis, backlog triage, WATCH list, calibration snapshot |
| Monthly | Calibration council; kill-switch drill; broker/TCA review; cost review |
| Quarterly | Assumption audit (06 §5); reverse stress test; DR drill; secrets rotation; playbook rehearsal |

## 10. Governance & audit framework

- **Change management:** any change to strategies, models, limits, or execution behavior =
  versioned artifact + validation evidence + sign-off recorded in audit log. Emergency changes
  (risk-reducing only) may ship immediately with retrospective review within 24 h.
- **Model risk management (SR 11-7 spirit):** every model has an owner, purpose statement,
  validation dossier, monitoring plan, and retirement criteria — enforced by the registry schema.
- **Limits governance:** limits-registry changes require written rationale; raising any risk
  limit requires cooling period (24 h) + explicit sign-off; lowering is instant.
- **Audit:** hash-chained DecisionRecords + control events; daily chain-head anchored externally;
  5-year retention (SEBI-aligned); quarterly self-audit: sample 20 decisions → verify full
  reconstruction (evidence → reasoning → verdict → orders → outcome).
- **Incident management:** severity classes, blameless post-mortems (filed to memory), action
  items tracked to closure; any C0 incident freezes related scope until post-mortem approved.
- **Human authority map:** you = risk owner (limits, modes, promotions, kill reset); platform =
  everything else within policy.

## 11. Disaster recovery

| Asset | Protection | RPO | RTO |
|---|---|---|---|
| Lake (events, forever) | Object-store versioning + cross-region replication | ~0 | hours |
| Postgres (decisions, orders, registries) | WAL shipping + daily snapshot restore-tested | ≤ 5 min | ≤ 1 h |
| ClickHouse | Rebuildable projection from lake | n/a | ≤ 1 day (non-blocking) |
| Bus | Retention-window loss acceptable (lake has all) | ≤ 1 min | ≤ 15 min |
| Secrets | Encrypted, escrowed offline copy | 0 | ≤ 1 h |
| **Open positions** | **Dead-man invariant (07 §7) — safe with zero platform** | n/a | n/a |

Quarterly DR drill: restore the full platform to a clean environment from backups and replay to
current — measured against the RTOs above.

## 12. Cost envelope (monthly, indicative — pick a tier in review)

| Tier | Infra | Market data | News/social/on-chain | LLM | Total ballpark |
|---|---|---|---|---|---|
| Lean (P1) | $150–300 (1 fat node + object storage) | Kite Connect ₹500 + Dhan ₹499 (often waived); execution keys free | Free tiers + Coinglass $30 | $50–150 | **~₹30–55k** |
| Standard (P2–P3) | $300–700 (HA-ish k3s) | +TrueData tick feed ~₹2–10k/segment (quote-based, verified [09 §3.2](09-VALIDATION-REVIEW.md)) | +CryptoQuant tier $100–300, X API? | $150–400 | **~₹70–140k** |
| Heavy (scale) | $1k+ | +tick archives, +25-depth | +Glassnode pro etc. | $500+ | ₹2L+ |

One-time: historical data backfill ₹25k–1.5L depending on P0-D2 depth. (All figures ±40%;
firmed up during P0 procurement.)

## 13. Risk register (project-level, top 10)

| # | Risk | Mitigation |
|---|---|---|
| 1 | Overfitting/false discovery in research | Trial logging + DSR/PSR/SPA gates (04 §9); graveyard memory |
| 2 | India order-flow data insufficient for flow strategies | Tier system (03 §2); families that don't need flow; P0-D2 vendor |
| 3 | SEBI algo-framework friction/changes | P1/P2 deliver value without P3; compliance path started early; crypto P3 decoupled |
| 4 | LLM hallucination into decisions | Structured outputs + citation verifier + no-numeric-path invariant (02 §7) |
| 5 | Broker API instability | Dual-broker, dead-man invariant, playbooks R2/R4 |
| 6 | Cost drag kills expectancy at pilot capital | Costs inside EV pre-trade; capacity-aware families; tier review at G1 |
| 7 | Crypto venue/counterparty & tax regime | Policy-gated venues, sleeve caps, exposure limits (05 §5); entity/tax decision up front |
| 8 | Key-person (solo operator) | Runbooks, dead-man design, "platform survives ignoring you" defaults (fail-closed) |
| 9 | Scope creep pre-P1 | Gates; seed-strategy cap (2–3); this doc set as contract |
| 10 | Correlated regime shift breaking all families at once | Regime-stratified validation, allocation floors/ceilings, ladder (05 §7), stress library |
| 11 | Physical-delivery mishap on stock F&O | Delivery-window hard veto (05 §3.16); forced-flatten plans (07 §7) |
| 12 | Calibration gates statistically meaningless at low trade counts | Hierarchical calibration (02 §5); sample-aware gates (G1) |
| 13 | News strategies overfit to hindsight narratives | Live-forward-only validation (04 §4); own PIT news archive from day one (03 §3.4) |
| 14 | India crypto regulatory reversal (prohibition-leaning signals, 2026) | FIU-registered venues only; derivatives-first; venue-balance minimization; kill-switch + withdrawal-first playbook; monitor policy events ([09](09-VALIDATION-REVIEW.md) R-C8) |

## 14. Consolidated open questions (decisions needed to freeze v0.2)

**Capital & scope:** pilot capital band & market split (00 Q1); market priority order (00 Q4);
overnight positions in P1/P2 (05 Q2); crypto sleeve cap (05 Q3); BSE (SENSEX weeklies) inclusion
timing.
**Compliance & venues:** crypto venue/entity policy (00 Q2); broker pair (01 Q5); crypto SOR
now vs later (07 Q4).
**Build choices:** chassis spike preference (01 Q1); India data vendor & backfill depth
(01 Q2 / 03 Q1–Q2); Rust vs Go (01 Q3); cloud vs metal (01 Q4).
**Risk appetite:** ladder & base risk numbers (05 Q1); options selling in scope (00 Q5 / 05 Q4);
flatten-vs-protect default on L3/L4 (05 Q5); unattended-hours window defaults (05 §8).
**Intelligence:** X API paid tier (02 Q4 / 03 Q3); on-chain vendor tier (03 Q4); DA veto power
(02 Q1); extra agents (02 Q5).
**Process:** targets in 00 §9 (00 Q3); WFO windows (04 Q3); promotion approval scope (06 Q1);
machine-vs-human report visibility (06 Q3); P2 approval channel (07 Q3).

## 15. Definition of Done — Platform v1

All of: G0–G2 gates passed and P2 live for 3+ months · ≥ 3 strategy families SCALED or PILOT
with positive net expectancy · risk kernel with zero bypass incidents ever · 100%
decision-record coverage · calibration within tolerance for 2 consecutive months · monthly kill
drills green · DR drill passed · learning loop demonstrably closed (≥ 1 validated improvement
promoted from review findings, ≥ 1 strategy or detector retired by evidence) · this doc set
updated to as-built v1.0.
