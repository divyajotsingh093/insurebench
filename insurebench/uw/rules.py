"""Synthetic underwriting rules for Meridian Mutual term life ("Meridian Term").

This module is the single source of truth. The engine (engine.py) evaluates these tables and the
manual (manual.py) is rendered from them, so the two can never drift apart. Every rule row has a
stable ID that agents are expected to cite.

All thresholds are invented for benchmarking and are NOT medical or actuarial guidance.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------------------------
# Build (BMI). BMI = weight_kg / height_m^2, rounded to 1 decimal. Bands are [lo, hi).
# ---------------------------------------------------------------------------------------------
BMI_TABLE = [
    # id, lo, hi, debits, outcome
    ("UW-BMI-1", 0.0, 17.0, 50, None),
    ("UW-BMI-2", 17.0, 18.5, 25, None),
    ("UW-BMI-3", 18.5, 30.0, 0, None),
    ("UW-BMI-4", 30.0, 35.0, 25, None),
    ("UW-BMI-5", 35.0, 40.0, 75, None),
    ("UW-BMI-6", 40.0, 45.0, 150, None),
    ("UW-BMI-7", 45.0, 999.0, None, "decline"),
]

# ---------------------------------------------------------------------------------------------
# Blood pressure (mmHg). The band is the WORSE of the systolic band and the diastolic band.
# Bands are inclusive upper bounds.
# ---------------------------------------------------------------------------------------------
BP_TABLE = [
    # id, systolic_max, diastolic_max, debits, outcome
    ("UW-BP-1", 140, 90, 0, None),
    ("UW-BP-2", 150, 95, 25, None),
    ("UW-BP-3", 160, 100, 50, None),
    ("UW-BP-4", 175, 105, 100, None),
    ("UW-BP-5", 999, 999, None, "postpone"),
]

# ---------------------------------------------------------------------------------------------
# Type 2 diabetes. Debits by HbA1c (%) band [lo, hi), plus adjustments.
# ---------------------------------------------------------------------------------------------
DM_HBA1C_TABLE = [
    ("UW-DM-1", 0.0, 7.0, 50, None),
    ("UW-DM-2", 7.0, 8.0, 100, None),
    ("UW-DM-3", 8.0, 10.0, 150, None),
    ("UW-DM-4", 10.0, 99.0, None, "decline"),
]
DM_RECENT_DX_MONTHS = 12          # diagnosed < 12 months ago -> postpone
DM_RECENT_DX_ID = "UW-DM-5"
DM_LONG_DURATION_YEARS = 15       # duration > 15 years -> +50
DM_LONG_DURATION_DEBITS = 50
DM_LONG_DURATION_ID = "UW-DM-6"
DM_INSULIN_DEBITS = 25
DM_INSULIN_ID = "UW-DM-7"
DM_LAB_THRESHOLD = 6.5            # HbA1c >= 6.5 on blood profile with no declared diabetes -> treated as diabetic
DM_UNDECLARED_ID = "UW-DM-8"

# ---------------------------------------------------------------------------------------------
# Lipids: total cholesterol / HDL ratio, inclusive upper bounds. Only rated when a blood profile
# (BLD) is part of the required evidence.
# ---------------------------------------------------------------------------------------------
LIPID_TABLE = [
    ("UW-LIP-1", 5.0, 0),
    ("UW-LIP-2", 6.5, 25),
    ("UW-LIP-3", 8.0, 50),
    ("UW-LIP-4", 999.0, 75),
]

# ---------------------------------------------------------------------------------------------
# Family history
# ---------------------------------------------------------------------------------------------
FAMILY_HISTORY_DEBITS = 25
FAMILY_HISTORY_ID = "UW-FH-1"   # parent or sibling died of heart disease before age 60

# ---------------------------------------------------------------------------------------------
# Smoker status -> rate class (not debits)
# ---------------------------------------------------------------------------------------------
SMOKER_QUIT_MONTHS = 12
SMOKER_RULES = {
    "UW-SMK-1": "Current smokers (any tobacco or nicotine product in the last 12 months) are rated on the smoker rate class.",
    "UW-SMK-2": "Ex-smokers who quit 12 or more months before application are rated non-smoker. Fewer than 12 months -> smoker.",
    "UW-SMK-3": "A positive cotinine result on the blood profile overrides a non-smoker declaration: rate as smoker and treat as a material non-disclosure (see UW-ND-1).",
}

# ---------------------------------------------------------------------------------------------
# Occupations. Classes 1-4 plus D (declined). Class 3 -> +25 debits, class 4 -> flat extra.
# ---------------------------------------------------------------------------------------------
OCCUPATIONS = {
    "accountant": "1", "software engineer": "1", "teacher": "1", "pharmacist": "1", "lawyer": "1",
    "graphic designer": "1", "bank officer": "1", "civil servant": "1",
    "nurse": "2", "retail manager": "2", "chef": "2", "electrician": "2", "delivery driver": "2",
    "plumber": "2", "physiotherapist": "2",
    "construction worker": "3", "warehouse operative": "3", "long-haul truck driver": "3",
    "welder": "3", "farm worker": "3",
    "offshore oil rig worker": "4", "underground miner": "4", "commercial fisher": "4",
    "high-rise window cleaner": "4",
    "explosives handler": "D", "professional stunt performer": "D",
}
OCCUPATION_RULES = {
    "1": ("UW-OCC-1", 0, 0.0, "Office / professional: no loading."),
    "2": ("UW-OCC-2", 0, 0.0, "Light manual: no loading."),
    "3": ("UW-OCC-3", 25, 0.0, "Heavy manual: +25 debits."),
    "4": ("UW-OCC-4", 0, 2.5, "Hazardous: flat extra 2.5 per mille of sum assured; occupation questionnaire (OQ) required."),
    "D": ("UW-OCC-5", None, None, "Declined occupation: decline."),
}

# ---------------------------------------------------------------------------------------------
# Hazardous hobbies. Each rule: (id, threshold, outcome, value) where outcome is
# "none", "flat" (per mille) or "exclusion" (exclusion code). Thresholds are inclusive upper bounds.
# ---------------------------------------------------------------------------------------------
HOBBIES = {
    "scuba diving": {
        "metric": "max_depth_m", "unit": "metres (maximum depth)",
        "bands": [("UW-HOB-1", 30, "none", None), ("UW-HOB-2", 40, "flat", 2.0), ("UW-HOB-3", 10**9, "exclusion", "EXC-DIVE")],
    },
    "mountaineering": {
        "metric": "max_altitude_m", "unit": "metres (maximum altitude)",
        "bands": [("UW-HOB-4", 4000, "none", None), ("UW-HOB-5", 6000, "flat", 2.5), ("UW-HOB-6", 10**9, "exclusion", "EXC-MOUNT")],
    },
    "skydiving": {
        "metric": "jumps_per_year", "unit": "jumps per year",
        "bands": [("UW-HOB-7", 50, "flat", 2.0), ("UW-HOB-8", 10**9, "exclusion", "EXC-AIRSPORT")],
    },
    "private aviation": {
        "metric": "logged_hours", "unit": "total logged flying hours",
        # fewer than 100 logged hours -> exclusion; 100+ -> flat extra 3 per mille
        "bands": [("UW-HOB-9", 99, "exclusion", "EXC-AVIATION"), ("UW-HOB-10", 10**9, "flat", 3.0)],
    },
    "motor racing": {
        "metric": "races_per_year", "unit": "races per year",
        "bands": [("UW-HOB-11", 10**9, "exclusion", "EXC-MOTOR")],
    },
}
EXCLUSIONS = {
    "EXC-DIVE": "Death arising from underwater diving below 40 metres is excluded.",
    "EXC-MOUNT": "Death arising from mountaineering above 6,000 metres is excluded.",
    "EXC-AIRSPORT": "Death arising from parachuting, skydiving or other air sports is excluded.",
    "EXC-AVIATION": "Death arising from aviation other than as a fare-paying passenger on a scheduled airline is excluded.",
    "EXC-MOTOR": "Death arising from motor racing, speed trials or rallying is excluded.",
}

# ---------------------------------------------------------------------------------------------
# Recent / ongoing conditions -> postpone
# ---------------------------------------------------------------------------------------------
POSTPONE_CONDITIONS = {
    "chest pain under investigation": ("UW-PP-1", "Undiagnosed chest pain with investigations pending: postpone until diagnosis is complete."),
    "cancer treatment completed within 24 months": ("UW-PP-2", "Any malignancy with treatment completed less than 24 months ago: postpone."),
    "surgery scheduled": ("UW-PP-3", "Surgery scheduled or awaited: postpone until recovered."),
}

# ---------------------------------------------------------------------------------------------
# Debits -> table class
# ---------------------------------------------------------------------------------------------
TABLE_BANDS = [
    # id, max_debits (inclusive), class, extra_premium_pct
    ("UW-TBL-1", 25, "Standard", 0),
    ("UW-TBL-2", 75, "T2", 50),
    ("UW-TBL-3", 125, "T4", 100),
    ("UW-TBL-4", 175, "T6", 150),
    ("UW-TBL-5", 225, "T8", 200),
    ("UW-TBL-6", 10**9, "Decline", None),
]
TABLE_ORDER = ["Standard", "T2", "T4", "T6", "T8", "Decline"]

# ---------------------------------------------------------------------------------------------
# Eligibility, financial limits, authority
# ---------------------------------------------------------------------------------------------
MIN_AGE, MAX_AGE = 18, 65
ELIGIBILITY_ID = "UW-ELIG-1"

FINANCIAL_MULTIPLES = [
    # id, max_age (inclusive), income multiple
    ("UW-FIN-1", 39, 25),
    ("UW-FIN-2", 49, 20),
    ("UW-FIN-3", 59, 15),
    ("UW-FIN-4", 65, 10),
]
FINANCIAL_ROUND = 1000           # offered amount rounded DOWN to the nearest 1,000
FINANCIAL_NO_CAPACITY_ID = "UW-FIN-5"  # existing cover already at/above limit -> decline (financial)

AUTHORITY_LIMIT = 2_000_000      # total requested sum assured above this -> refer to senior underwriter
AUTHORITY_ID = "UW-AUTH-1"
NONDISCLOSURE_ID = "UW-ND-1"     # material non-disclosure detected -> refer
MIB_DECLINE_MONTHS = 36
MIB_ID = "UW-MIB-1"              # prior decline at any carrier within 36 months -> refer

# ---------------------------------------------------------------------------------------------
# Evidence grid: age band x sum-assured band -> routine evidence codes.
# ---------------------------------------------------------------------------------------------
EVIDENCE_CODES = {
    "BLD": "Blood profile (lipids, HbA1c, cotinine)",
    "URN": "Urinalysis",
    "PMR": "Paramedical examination (measured height, weight, blood pressure)",
    "ECG": "Resting ECG",
    "TECG": "Treadmill (exercise) ECG",
    "APS": "Attending physician statement",
    "FIN": "Financial questionnaire",
    "INSP": "Inspection report",
    "HQ": "Hazardous pursuits questionnaire",
    "OQ": "Occupation questionnaire",
}
AGE_BANDS = [("18-40", 18, 40), ("41-50", 41, 50), ("51-65", 51, 65)]
SA_BANDS = [("<=250k", 250_000), ("<=500k", 500_000), ("<=1M", 1_000_000), ("<=2M", 2_000_000), (">2M", 10**12)]
EVIDENCE_GRID = {
    "18-40": [[], ["BLD", "URN"], ["PMR", "BLD", "URN"], ["PMR", "BLD", "URN", "ECG", "FIN"], ["PMR", "BLD", "URN", "TECG", "FIN", "INSP"]],
    "41-50": [["BLD", "URN"], ["PMR", "BLD", "URN"], ["PMR", "BLD", "URN", "ECG"], ["PMR", "BLD", "URN", "ECG", "FIN"], ["PMR", "BLD", "URN", "TECG", "FIN", "INSP"]],
    "51-65": [["PMR", "BLD", "URN"], ["PMR", "BLD", "URN", "ECG"], ["PMR", "BLD", "URN", "ECG"], ["PMR", "BLD", "URN", "TECG", "FIN"], ["PMR", "BLD", "URN", "TECG", "FIN", "INSP"]],
}
EVIDENCE_GRID_ID = "UW-EV-1"
EVIDENCE_TRIGGERS = {
    "UW-EV-2": "Declared diabetes or declared hypertension -> APS.",
    "UW-EV-3": "Any hazardous hobby declared -> HQ.",
    "UW-EV-4": "Occupation class 4 -> OQ.",
    "UW-EV-5": "HbA1c >= 6.5 on blood profile without declared diabetes -> APS (added after the blood result).",
}
EVIDENCE_SOURCE_RULES = {
    "UW-SRC-1": "Build and blood pressure are rated on PMR measurements when a PMR is required; otherwise build is rated on declared height/weight and blood pressure on APS readings (if an APS is held), else not rated.",
    "UW-SRC-2": "Lipids are rated only when a blood profile (BLD) is required. Diabetes is rated on APS values where an APS is held, otherwise on BLD HbA1c.",
}


def all_rule_ids() -> set[str]:
    ids = set()
    for t in (BMI_TABLE, BP_TABLE, DM_HBA1C_TABLE, LIPID_TABLE, TABLE_BANDS, FINANCIAL_MULTIPLES):
        ids.update(r[0] for r in t)
    ids.update([DM_RECENT_DX_ID, DM_LONG_DURATION_ID, DM_INSULIN_ID, DM_UNDECLARED_ID, FAMILY_HISTORY_ID,
                ELIGIBILITY_ID, FINANCIAL_NO_CAPACITY_ID, AUTHORITY_ID, NONDISCLOSURE_ID, MIB_ID, EVIDENCE_GRID_ID])
    ids.update(SMOKER_RULES)
    ids.update(r[0] for r in OCCUPATION_RULES.values())
    for h in HOBBIES.values():
        ids.update(b[0] for b in h["bands"])
    ids.update(v[0] for v in POSTPONE_CONDITIONS.values())
    ids.update(EVIDENCE_TRIGGERS)
    ids.update(EVIDENCE_SOURCE_RULES)
    ids.update(EXCLUSIONS)
    return ids
