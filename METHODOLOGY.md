# InsureBench methodology (v0)

## 1. Gold answers come from code or public records

- **Synthetic suites** (`uw_synthetic`, `claims_synthetic`, `coverage_qa`): seeded sampling produces structured facts. The
  gold is computed by a deterministic engine (`insurebench/uw/engine.py`, `insurebench/claims/engine.py`). Documents are
  rendered from those facts. The underwriting manual and the policy wordings are rendered from the **same** rule tables
  (`uw/rules.py`, `claims/policies.py`), so the text an agent reads always agrees with the grader.
- **Real suites**: `appeals_real` uses the actual outcome of California Independent Medical Reviews. `coding_validity` uses
  membership in the official ICD-10-CM FY2026 table.
- **LLM judges** score only free text (UW rationale, claims letter). They are pluggable (`--judge heuristic|none|llm:<model>`).
  The default heuristic checks that the text mentions the gold drivers (rule/clause IDs, decision, amount). It is transparent but shallow.

## 2. Underwriting rules (synthetic)

Order: eligibility, then knock-out declines, then postpone triggers (decline wins over postpone), then additive debits
(build, BP on the worse of systolic/diastolic band, diabetes HbA1c plus duration/insulin adjustments, lipid ratio,
family history, occupation class 3), then table class (0-25 Standard, 26-75 T2, 76-125 T4, 126-175 T6, 176-225 T8,
226+ Decline). After that come hobby/occupation flat extras and exclusions, financial limits (income multiple by age, less
existing cover from the MIB-style lookup, rounded down to 1,000), smoker rate class, and referral (sum assured above
2,000,000, material non-disclosure, prior decline within 36 months). Evidence requirements come from an age x sum-assured
grid plus triggers. Build and BP use paramedical measurements when a PMR is required.

## 3. Claims rules (synthetic, real-calibrated deductibles)

Order (clause x-6.3): policy period, then duplicate, then waiting periods (initial 30 days, specific disease, pre-existing
disease; accidents exempt), then documents (pend), then non-payable items, then room-rent excess and proportionate deduction on
associated expenses, then ICU excess, then disease sublimit, then deductible, then co-payment, then remaining sum insured. Decimal
arithmetic with half-up rounding at each deduction. Red flags (inflated item at more than 2.5x the reference charge,
outside policy period, duplicate, date mismatch) trigger SIU referral but do not change the amount unless they are a rejection ground.

## 4. Environment

One tool layer (`insurebench/env/tools.py`) is exposed as plain Python and over MCP. A simulated case owner (tau-bench
style, deterministic by default) holds back specific facts (hobby exposure, ex-smoker quit date, date of first diagnosis
of a pre-existing condition) and reveals them only when asked a relevant question. Evidence results appear only after
`order_evidence`. Ordering evidence that is not required returns a normal result, so ordering cannot leak the gold evidence set.
Budget: 40 tool calls and 250k tokens per case, the same for every harness.

## 5. Metrics (separate columns, no blend)

- UW: decision exact, table class exact / within one, evidence-set F1, exclusions exact, rate class, offered sum assured,
  referral correct, info-gathering coverage, rationale score.
- Claims: admissibility exact, payable within +/-1%, clause citation set exact, red-flag precision/recall, missing-docs F1,
  letter score.
- Appeals: accuracy, per-class recall. Coding: invalid/non-billable F1, both-lists exact. Coverage QA: answer exact (numeric within 1%), clause exact.
- Cross-cutting: pass^k (all k runs correct), cost per correct (OpenRouter prices from the roster), hallucination rate
  (cited IDs that do not exist), invalid and redundant calls, steps relative to the shortest reference path, escalation
  precision/recall and over-escalation, fairness delta across counterfactual pairs, robustness delta (clean minus noisy),
  injection resistance, latency.

## 6. Splits and contamination

- Synthetic dev comes from the public seed. Test comes from a **separate stream** keyed by `INSUREBENCH_PRIVATE_SEED`.
  Without that variable, the default test split is reproducible by anyone and is **not hidden**. The official leaderboard
  sets the secret in CI.
- Hidden gold (`data/gold_hidden/`) is gitignored, excluded from the web bundle (enforced by `web/scripts/check-bundle.mjs`),
  and only test **aggregates** are published.
- Every data file carries the canary GUID in `data/CANARY.txt`.
- `appeals_real` and `coding_validity` derive from public sources. Their test items may appear in pre-training data. Treat
  them as contamination-exposed.

## 7. Known limitations

Synthetic thresholds are invented, not actuarial. Documents are markdown, not scanned PDFs. The appeals redaction is
heuristic. The coding suite tests validity, not clinical correctness. Public `hidden_facts` mean a determined agent could
read the user simulator's script from the case file (harnesses only see tool outputs, but submitters run the code locally).
Baseline "rules" agents reuse the reference engine on what they observe, so they validate the environment and graders
rather than represent a realistic competitor.
