# Data card: appeals_real

- **Source**: California Department of Managed Health Care, "Independent Medical Review (IMR) Determinations, Trend", via data.ca.gov / CHHS Open Data.
  URL: https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv
- **License**: Creative Commons Attribution (as listed on the dataset page). Processed subset redistributed with attribution.
- **Retrieved**: 2026-11-15 (sha256 and row counts in `data/sources/imr_meta.json`). Script: `scripts/fetch_imr.py`.
- **Size**: 40 dev + 40 test, each balanced 50/50 upheld/overturned, report years 2022-2026; sampled from 6,456 rows that survive redaction (42,749 total).
- **Task**: predict whether the independent reviewer UPHELD or OVERTURNED the health plan's denial.
- **Preprocessing**: the reviewer "Findings" text is cut before "Final Result:" and truncated at the first sentence containing decisional language (necessary, appropriate, therefore, evidence, guideline, etc.) so the conclusion is redacted; ReferenceID is kept only in gold. Prior baseline uses outcome rates by review type x treatment category computed on rows NOT in the suite (`data/sources/imr_priors.json`).
- **Known biases / limits**: real gold, but (1) redaction is heuristic and some cues may remain or too much context may be lost; (2) the dataset is public, so test items may be in model pre-training data (contamination risk; the test split is not truly hidden); (3) California-specific law and plan mix; (4) balanced sampling does not reflect base rates (~52% overturned overall); (5) no fairness/injection variants in v0.
