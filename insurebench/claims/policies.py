"""Synthetic Meridian Mutual hospitalisation policy variants. Single source of truth for both the
claims engine and the rendered policy wordings. All figures are invented."""
from __future__ import annotations

import json
from pathlib import Path

# Real-world calibration: deductibles are the median in-network individual deductibles from the CMS Marketplace
# Plan Attributes PUF (PY2025) - Bronze -> BASIC, Silver -> SILVER, Platinum -> GOLD. See scripts/fetch_cms_puf.py
# and data/cards/claims_synthetic.md. Fallback constants equal the committed values so generation is deterministic.
_CMS = Path(__file__).resolve().parents[2] / "data" / "sources" / "cms_plan_params.json"
_DED = {"Bronze": 7500, "Silver": 3500, "Platinum": 0}
if _CMS.exists():
    _DED.update({k: int(v) for k, v in json.loads(_CMS.read_text())["median_individual_deductible"].items() if k in _DED})

# Clause numbering is shared across variants; the clause ID is "<PREFIX>-<number>".
CLAUSES = {
    "1.1": "Policy period",
    "2.1": "Initial waiting period",
    "2.2": "Specific disease waiting period",
    "2.3": "Pre-existing disease waiting period",
    "3.1": "Non-payable items",
    "4.1": "Room rent limit",
    "4.2": "Proportionate deduction",
    "4.3": "ICU limit",
    "4.4": "Disease sublimits",
    "5.1": "Deductible",
    "5.2": "Co-payment",
    "5.3": "Sum insured (annual limit)",
    "6.1": "Claim documentation",
    "6.2": "Duplicate and fraudulent claims",
    "6.3": "Order of application",
    "6.4": "Special investigation referral",
}

POLICIES = {
    "MM-HOSP-BASIC": {
        "name": "Meridian Hospital Care Basic",
        "prefix": "BSC",
        "sum_insured": 150_000,
        "deductible": _DED["Bronze"],
        "copay_pct": 20,
        "room_limit_per_day": 1_500,
        "icu_limit_per_day": 3_000,
        "initial_wait_days": 30,
        "specific_wait_days": 730,
        "ped_wait_days": 1095,
        "sublimits": {"cataract": 20_000, "hernia": 30_000, "knee_replacement": 60_000, "kidney_stone": 25_000},
    },
    "MM-HOSP-SILVER": {
        "name": "Meridian Hospital Care Silver",
        "prefix": "SLV",
        "sum_insured": 300_000,
        "deductible": _DED["Silver"],
        "copay_pct": 10,
        "room_limit_per_day": 3_000,
        "icu_limit_per_day": 6_000,
        "initial_wait_days": 30,
        "specific_wait_days": 730,
        "ped_wait_days": 1460,
        "sublimits": {"cataract": 40_000, "knee_replacement": 120_000},
    },
    "MM-HOSP-GOLD": {
        "name": "Meridian Hospital Care Gold",
        "prefix": "GLD",
        "sum_insured": 1_000_000,
        "deductible": _DED["Platinum"],
        "copay_pct": 0,
        "room_limit_per_day": 8_000,
        "icu_limit_per_day": 16_000,
        "initial_wait_days": 30,
        "specific_wait_days": 365,
        "ped_wait_days": 730,
        "sublimits": {},
    },
}

# Conditions subject to the specific-disease waiting period (2.2)
SPECIFIC_WAIT_CONDITIONS = {"cataract", "hernia", "knee_replacement", "kidney_stone"}

# Non-payable items (Annex A). Line items with these categories are fully deducted under 3.1.
NON_PAYABLE = {
    "admission_kit": "Admission / patient kit",
    "toiletries": "Toiletries and personal comfort items",
    "attendant_food": "Food and beverages for attendants",
    "registration_fee": "Registration and file-opening charges",
    "telephone": "Telephone and television charges",
}

# Categories that attract proportionate deduction (4.2) when room rent exceeds the limit
ASSOCIATED_CATEGORIES = {"surgeon_fee", "anaesthetist_fee", "ot_charges", "nursing", "doctor_visits", "investigations"}
# Categories that never attract proportionate deduction
NON_ASSOCIATED_CATEGORIES = {"medicines", "consumables", "implants", "icu"}

# Annex C: reasonable & customary reference unit charges. A line item billed at more than
# INFLATION_FACTOR x the reference unit charge is flagged INFLATED_ITEM (6.4).
REFERENCE_CHARGES = {
    "ct_scan": 4_000, "mri_scan": 7_000, "cbc_test": 400, "xray": 600, "ultrasound": 1_500, "ecg": 300,
    "iv_fluids": 150, "antibiotic_course": 2_500, "intraocular_lens": 12_000, "mesh_implant": 9_000,
    "knee_implant": 60_000, "stent": 30_000, "dj_stent": 5_000, "cast": 2_000, "nursing_day": 800,
    "doctor_visit": 700,
}
INFLATION_FACTOR = 2.5

REQUIRED_DOCS_BASE = ["CLAIM_FORM", "DISCHARGE_SUMMARY", "ITEMISED_BILL", "ID_PROOF"]
REQUIRED_DOCS_CONDITIONAL = {
    "OPERATION_NOTES": "surgical procedure performed",
    "POLICE_REPORT": "hospitalisation due to accident (police report / medico-legal certificate)",
    "INVESTIGATION_REPORTS": "any investigation (lab or imaging) billed",
    "PHARMACY_INVOICES": "any medicines billed",
}
DOC_TITLES = {
    "CLAIM_FORM": "Claim form",
    "DISCHARGE_SUMMARY": "Discharge summary",
    "ITEMISED_BILL": "Itemised hospital bill",
    "ID_PROOF": "Identity proof",
    "OPERATION_NOTES": "Operation notes",
    "POLICE_REPORT": "Police report / medico-legal certificate",
    "INVESTIGATION_REPORTS": "Investigation reports",
    "PHARMACY_INVOICES": "Pharmacy invoices",
}

FRAUD_FLAGS = {
    "INFLATED_ITEM": "A line item is billed above 2.5x the Annex C reference charge.",
    "OUTSIDE_POLICY_PERIOD": "Treatment dates fall outside the policy period.",
    "DUPLICATE_CLAIM": "Same insured, hospital, admission date and billed amount as a previously submitted claim.",
    "DATE_MISMATCH": "Admission or discharge dates on the claim form differ from the hospital records.",
}


def clause_id(policy_code: str, num: str) -> str:
    return f"{POLICIES[policy_code]['prefix']}-{num}"


def all_clause_ids() -> set[str]:
    return {f"{p['prefix']}-{n}" for p in POLICIES.values() for n in CLAUSES}
