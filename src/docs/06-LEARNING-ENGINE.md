# 06 · Learning, Research & Self-Improvement Engine

> **ATIS Design Doc 06 · v0.2-draft · 2026-07-11 · Status: awaiting review (validation pass applied — see [09](09-VALIDATION-REVIEW.md))**
> Upstream: [04-STRATEGY-ENGINE](04-STRATEGY-ENGINE.md) (validation gates), [02-AGENTS](02-AGENTS.md) (calibration duty)
> Principle: *the platform's real product is a compounding knowledge base; PnL is interest on it.*

---

## 1. The learning loop

```
every plan / trade / abstention / recommendation
        │
        ▼
┌─────────────────┐   ┌──────────────────┐   ┌───────────────────┐
│ OUTCOME CAPTURE │──▶│  ATTRIBUTION     │──▶│  REVIEW (LLM)     │
│ labels, MAE/MFE │   │ signal/timing/   │   │ per-trade, daily, │
│ counterfactuals │   │ size/exec/luck   │   │ weekly synthesis  │
└─────────────────┘   └──────────────────┘   └─────────┬─────────┘
        │                                              │ findings
        ▼                                              ▼
┌─────────────────┐   ┌──────────────────┐   ┌───────────────────┐
│ DRIFT MONITORS  │──▶│ SELF-REFLECTION  │──▶│ RESEARCH BACKLOG  │
│ feature/concept/│   │ scheduled audits │   │ hypotheses ranked │
│ performance     │   │ of assumptions   │   │ by info gain      │
└─────────────────┘   └──────────────────┘   └─────────┬─────────┘
        │                                              │
        ▼                                              ▼
┌──────────────────────────────────────────────────────────────────┐
│ KNOWLEDGE UPDATES — all gated by validation (04 §10) + twin (§10)│
│ evidence weights · calibration maps · regime models · strategy   │
│ params (new versions) · detector status · management policies    │
└──────────────────────────────────────────────────────────────────┘
```

Nothing updates itself directly from live outcomes on the hot path — **learning proposes,
validation disposes, governance promotes.**

## 2. Outcome capture (outcome-tracker)

Every TradePlan — executed or not — is labeled at horizon end:

```jsonc
{ "plan_id":"…", "executed": true|false, "user_action": "taken|modified|ignored",  // P1/P2 gold
  "entry": {"planned_zone":[..], "actual":.., "entry_quality_R":..},
  "exit":  {"actual":.., "policy_followed": true, "deviation_reason": null},
  "pnl_R": +1.42, "pnl_net": .., "costs_actual": ..,
  "mae_R": -0.38, "mfe_R": +2.10,                       // max adverse/favorable excursion
  "stop_quality": {"hit": false, "would_have_survived_wider": null, "inside_pool": false},
  "target_quality": {"t1_hit": true, "mfe_beyond_t2_R": 0.2},
  "slippage_vs_model_bps": +3.1,
  "context": {"regime_at_entry":.., "health":.., "news_during": [..]},
  "counterfactuals": {                                   // computed via replay (twin)
     "no_trade": 0, "hold_to_t2_R": +1.9, "exit_on_choch_R": +1.6,
     "half_size_R": +0.71, "if_user_ignored_market_did": "+1.1R" } }
```

- **Recommendation-mode gold:** in P1/P2, user take/modify/ignore actions + subsequent market
  outcome build the acceptance model *and* measure whether the human or the machine was right —
  both directions are logged and reported monthly.
- **Missed opportunities:** every candidate the ranker rejected and every quorum near-miss is
  labeled at the same horizon (cheap in replay) — the abstention policy is itself a model under
  evaluation.

## 3. Attribution engine

Monthly (and per-strategy rolling), decompose performance into:

| Component | Method |
|---|---|
| Signal edge | Realized R vs matched no-skill baseline (random entries, same instrument/time/hold, block-bootstrapped) |
| Timing | Entry-quality distribution (fill position within zone; MAE profile) |
| Sizing | Realized vs constant-size counterfactual (did conf_scalar help?) |
| Management | Policy-followed exits vs plan-static exits (counterfactual replay) |
| Execution | Slippage & costs vs model (TCA feed, 07 §8) |
| Luck | Bootstrap CI on the residual; PSR/DSR trend per strategy |

Skill claims require the luck component's CI to exclude the observed edge being zero — this is
what stands between us and celebrating variance.

## 4. Trade Review Agent (LLM-backed, claude-fable-5)

- **Per trade:** structured review — thesis vs what happened, evidence that worked/failed,
  contra-case in hindsight, management decisions vs counterfactuals, one-line lesson, tags.
- **Daily:** 10-minute-read synthesis: what the platform believed, did, got right/wrong; open
  concerns; calibration snapshot.
- **Weekly:** cross-trade patterns ("sweep-reversals underperform Wednesdays-expiry"; "News agent
  early on RBI days"), each pattern auto-filed as a *hypothesis* with supporting record IDs —
  **reviews generate research tickets, not direct parameter changes.**
- All reviews embedded into narrative memory (03 §9) — retrievable by Devil's Advocate ("similar
  past failures") and Research.

## 5. Self-Reflection Engine (scheduled audits, Governance-owned)

| Cadence | Audit | Output |
|---|---|---|
| Daily | Calibration snapshot (final confidence + per-agent), DQ review, execution deviations | Flags on console |
| Weekly | Strategy health: rolling expectancy CI vs dossier, regime-affinity check, capacity drift | WATCH-list changes |
| Monthly | Full calibration council — hierarchical per 02 §5: evidence-level with real power, decision-level via bootstrap CIs (never point-ECE on thin samples); evidence-weight refit proposal; anti-metric anomaly scan (win-rate/turnover creep) | Weight-update proposal → validation |
| Quarterly | **Assumption audit:** which of the design's stated hypotheses (04 detectors, regime taxonomy, cost model, fill model) drifted? Feature power review (IC decay); reverse stress test (05 §10); "what would make us stop trading X?" pre-mortems | Written report + registry actions |

The quarterly audit answers the master-prompt questions verbatim: which assumptions failed,
which strategies deteriorated, which features lost power, what should be added, what retrained,
what retired.

## 6. Drift detection (drift-monitor)

| Monitor | Method | Default trigger (P) | Action |
|---|---|---|---|
| Feature drift | PSI / KS vs training window | PSI > 0.2 warn, > 0.3 act | Affected models → WATCH; retrain ticket |
| Concept drift | Rolling IC / AUC of model vs outcomes | CI excludes training value | Model → challenger review |
| Calibration drift | Rolling ECE per agent & final | > 0.05 for 2 windows | Weight shrinkage; threshold auto-raise (02 §5) |
| Performance drift | CUSUM on per-strategy expectancy | h = 4σ | Strategy → WATCH (04 §10) |
| Regime dependency shift | Per-regime performance re-test | Sign flip in best regime | Affinity re-estimation |
| Cost/slippage drift | TCA realized vs model | > 1.25× model for 20 trades | Fill/cost model recalibration; sizing haircut |

## 7. Model lifecycle (model-registry, MLflow)

- **Registered artifacts:** ML models, detector versions, evidence-weight sets, calibration maps,
  LLM prompts (with eval sets), management policies, cost/fill models.
- **Pipeline:** data snapshot (versioned) → training (Dagster/Ray, deterministic seeds) →
  offline eval (04 §9 protocols) → **shadow** (live inputs, no influence, ≥ 4 weeks) →
  **challenger** (ε-weight canary) → **champion** promotion.
- **Promotion gates:** statistically superior or equal-with-simpler; calibration ≥ champion;
  no unexplained divergence days in shadow; Governance sign-off (human approval in P1–P3 for
  anything touching sizing or thresholds).
- **Rollback:** one-command champion revert (previous version stays warm); every DecisionRecord
  pins model versions, so post-rollback analysis is exact.
- **Retraining triggers:** drift monitors (§6), scheduled refresh (quarterly default), or
  research promotion — never silent, always via the pipeline.

## 8. Strategy evolution

- **Parameter re-optimization:** scheduled per strategy (quarterly P) through the full WFO
  protocol; new params = new version at VALIDATED gate; plateau requirement prevents
  chasing-the-noise updates.
- **Combination:** meta-labeling (ML filter on top of a validated rule strategy's signals) and
  ensemble sizing across correlated strategies — treated as new strategies with full dossiers.
- **Discovery:** research sandbox may run guided search (Bayesian/genetic over detector
  combinations & params) **with every trial logged** for multiplicity accounting (04 §9);
  survivors face DSR with the *true* trial count.
- **Retirement:** per 04 §10; retired dossiers + post-mortems stay in memory as negative
  knowledge ("we tried X in 2026; it failed because Y") — the Research Agent checks new ideas
  against this graveyard first.

## 9. Research Engine

- **Backlog:** every hypothesis is a ticket: `{claim, falsifiable test, data needed, expected
  information gain, cost, source (review finding / anomaly / literature / human idea)}`,
  prioritized by info-gain per unit cost, reviewed at the weekly research council (08 §9).
- **Sandbox:** research-workbench with lake read access, feature store PIT API, backtest engine,
  experiment tracker (every run logged: params, dataset versions, results) — *no* prod
  credentials, *no* path to live except through 04 §10 gates.
- **Research Agent (LLM):** drafts hypotheses from review findings, anomaly logs, KG changes,
  and literature; writes the falsifiable-test section; humans approve tickets before compute is
  spent. It also maintains the "graveyard index" of failed ideas.
- **Standing research tracks (v1):** fill/slippage model calibration; regime taxonomy v2;
  evidence-weight learning; meta-labeling on seed families; execution-policy RL (offline, on
  logged management decisions); GEX validation for India; sentiment crowding as risk-modifier.

## 10. Digital Twin & simulation (twin-svc)

- **Deterministic replay:** any recorded period re-runs through the *production* containers
  (01 §7); used for counterfactuals (§2), regression (golden days), incident forensics, and
  "same code" enforcement — a release that diverges on golden days without a version-explained
  diff cannot ship.
- **Scenario generator:** block-bootstrap return paths; regime-conditioned resampling;
  synthetic shocks (gap opens, vol spikes, liquidity evaporation — spread ×k, depth ÷k);
  event-window libraries (RBI days, expiry days, FOMC nights for crypto).
- **Paper environment:** live feeds + simulated broker with calibrated fill/latency models —
  the mandatory residence for every strategy (04 §10) and every platform release.
- **Stress & chaos schedule:** monthly chaos drill in twin (broker API dies mid-order; bus
  partition; feed silently freezes; risk-kernel restart under load) — pass criteria are the
  documented recovery behaviors (07 §10).
- **Pre-deployment checklist (any change touching decisions/execution):** golden-day regression
  ✓, twin scenario suite ✓, paper soak (length by change class) ✓, rollback rehearsed ✓,
  Governance sign-off ✓.

## 11. What gets written back to memory

Every learning artifact persists (03 §9): outcome records, attribution reports, reviews
(embedded), drift events, audit reports, dossiers, graveyard entries, KG edge updates (with
provenance), calibration history. Retrieval interfaces: SQL (CH/PG), vector search (narratives),
graph queries (KG), and the console's "why did we…?" timeline built from DecisionRecords.

## 12. Open questions for review

1. Human-approval scope for model promotions: everything (safest, proposed) vs only
   sizing/threshold-touching models after 6 clean months?
2. Counterfactual replay depth: full L2-fidelity for crypto (costly) or bar-level for all (P)?
3. Monthly "machine vs human" report in P1/P2 (recommendations you ignored that won/lost) —
   want it prominent (recommended) or private?
4. Execution-policy RL: keep as research track (proposed) or explicitly out of scope for year 1?
