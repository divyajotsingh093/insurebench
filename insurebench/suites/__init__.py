"""Suite registry. A suite is a named dataset bound to a track (tool set + submit schema + grader)."""
from __future__ import annotations

SUITES = {
    "uw_synthetic": {"track": "uw", "kind": "agentic", "source": "synthetic rules engine (Meridian Mutual)",
                     "license": "CC-BY-4.0 (InsureBench)", "card": "data/cards/uw_synthetic.md",
                     "description": "Life underwriting: debits, table class, evidence, exclusions, financial limits, referral."},
    "claims_synthetic": {"track": "claims", "kind": "agentic", "source": "synthetic policy engine; deductibles calibrated on CMS Marketplace PUF",
                         "license": "CC-BY-4.0 (InsureBench); CMS PUF public domain", "card": "data/cards/claims_synthetic.md",
                         "description": "Hospitalisation claims: admissibility, payable amount, clause citations, red flags, missing docs."},
    "appeals_real": {"track": "appeals", "kind": "qa", "source": "California DMHC Independent Medical Review determinations (data.ca.gov)",
                     "license": "CC-BY", "card": "data/cards/appeals_real.md",
                     "description": "Predict whether an independent reviewer upheld or overturned a real health-plan denial."},
    "coding_validity": {"track": "coding", "kind": "qa", "source": "ICD-10-CM FY2026 code set (CMS / CDC NCHS)",
                        "license": "US public domain", "card": "data/cards/coding_validity.md",
                        "description": "Find invalid and non-billable ICD-10-CM codes on a claim."},
    "coverage_qa": {"track": "coverage_qa", "kind": "qa", "source": "synthetic Meridian policy wordings",
                    "license": "CC-BY-4.0 (InsureBench)", "card": "data/cards/coverage_qa.md",
                    "description": "Policy-wording interpretation questions with clause citation."},
}
TRACK_TO_SUITE = {v["track"]: k for k, v in SUITES.items()}
ALL_TRACKS = [v["track"] for v in SUITES.values()]


def resolve(name: str) -> str:
    """Accept a suite name or a track name; return the track."""
    if name in SUITES:
        return SUITES[name]["track"]
    if name in TRACK_TO_SUITE:
        return name
    raise KeyError(f"unknown suite/track '{name}'. Suites: {list(SUITES)}")
