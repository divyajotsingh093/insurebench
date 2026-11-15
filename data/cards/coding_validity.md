# Data card: coding_validity

- **Source**: ICD-10-CM FY2026 code descriptions in tabular order (CMS, produced by CDC NCHS).
  URL: https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip. Script: `scripts/fetch_icd10cm.py`.
- **License**: US federal public domain; the full code table is committed as `data/sources/icd10cm_2026.tsv.gz`.
- **Retrieved**: 2026-11-15 (sha256 in `data/sources/icd10cm_meta.json`). 98,186 codes, 74,719 billable.
- **Size**: 40 dev + 40 test synthetic claims, each with 3-6 real billable codes plus 0-2 invented codes (a real code with the last character changed to one that does not exist) and 0-1 non-billable category headers.
- **Gold**: membership and billable flag in the official table.
- **Known limits**: tests code validity only, not clinical coding correctness (diagnosis-to-code matching, sequencing, CPT/HCPCS linkage).
