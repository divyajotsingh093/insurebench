# Data card: coverage_qa

- **Source**: `insurebench/suites/coverage_qa.py`, questions templated over the synthetic Meridian policy wordings (`data/policies/*.md`).
- **License**: CC-BY-4.0. **Generated**: 2026-11-15. **Size**: 30 dev + 30 test.
- **Templates**: room limit, deductible, co-pay, specific/PED waiting periods, coverage at a given day, sublimits, proportionate-deduction arithmetic, non-payable items, accident exemption, sum insured.
- **Gold**: answer computed from the policy data + supporting clause ID.
- **Known limits**: templated questions, narrow phrasing; a real public standard wording (IRDAI Arogya Sanjeevani) was evaluated but not integrated (see README "Sources considered").
