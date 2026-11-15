"""Deterministic underwriting engine. Computes the gold answer for a UW case from its facts.

Facts schema (produced by insurebench.gen.uw_gen):
{
  "applicant_id", "name", "sex", "age", "occupation", "income", "sum_assured",
  "declared": {"height_cm", "weight_kg", "smoker_status": never|current|ex, "diabetes": bool,
               "hypertension": bool, "family_history_cardiac": bool, "conditions": [str]},
  "quit_months": int|None,                       # ex-smokers only; held back by the junior UW
  "hobbies": [{"name": str, "value": number}],   # value held back by the junior UW
  "evidence": {"PMR": {...}, "BLD": {...}, "APS": {...}, ...},
  "mib": [{"carrier", "kind": inforce|application, "months_ago", "decision", "sum_assured"}],
}
"""
from __future__ import annotations

from typing import Any

from . import rules as R


def bmi(height_cm: float, weight_kg: float) -> float:
    h = height_cm / 100.0
    return round(weight_kg / (h * h) + 1e-9, 1)


def bmi_rule(b: float):
    for rid, lo, hi, debits, outcome in R.BMI_TABLE:
        if lo <= b < hi:
            return rid, debits, outcome
    raise ValueError(b)


def bp_rule(sys_: int, dia: int):
    def band(v, idx):
        for i, row in enumerate(R.BP_TABLE):
            if v <= row[idx]:
                return i
        return len(R.BP_TABLE) - 1
    i = max(band(sys_, 1), band(dia, 2))
    rid, _, _, debits, outcome = R.BP_TABLE[i]
    return rid, debits, outcome


def hba1c_rule(v: float):
    for rid, lo, hi, debits, outcome in R.DM_HBA1C_TABLE:
        if lo <= v < hi:
            return rid, debits, outcome
    raise ValueError(v)


def lipid_rule(ratio: float):
    ratio = round(ratio, 1)
    for rid, mx, debits in R.LIPID_TABLE:
        if ratio <= mx:
            return rid, debits
    raise ValueError(ratio)


def hobby_rule(name: str, value: float):
    spec = R.HOBBIES[name]
    for rid, mx, outcome, val in spec["bands"]:
        if value <= mx:
            return rid, outcome, val
    raise ValueError((name, value))


def table_for(debits: int):
    for rid, mx, cls, pct in R.TABLE_BANDS:
        if debits <= mx:
            return rid, cls
    raise ValueError(debits)


def age_band(age: int) -> str:
    for name, lo, hi in R.AGE_BANDS:
        if lo <= age <= hi:
            return name
    return R.AGE_BANDS[-1][0] if age > 65 else R.AGE_BANDS[0][0]


def sa_band_index(sa: int) -> int:
    for i, (_, mx) in enumerate(R.SA_BANDS):
        if sa <= mx:
            return i
    return len(R.SA_BANDS) - 1


def grid_evidence(age: int, sa: int) -> list[str]:
    return list(R.EVIDENCE_GRID[age_band(age)][sa_band_index(sa)])


def base_required_evidence(facts: dict) -> set[str]:
    """Evidence required BEFORE any results are known (grid + declaration triggers)."""
    d = facts["declared"]
    req = set(grid_evidence(facts["age"], facts["sum_assured"]))
    if d.get("diabetes") or d.get("hypertension"):
        req.add("APS")
    if facts.get("hobbies"):
        req.add("HQ")
    if R.OCCUPATIONS.get(facts["occupation"]) == "4":
        req.add("OQ")
    return req


def required_evidence(facts: dict) -> set[str]:
    req = base_required_evidence(facts)
    bld = facts.get("evidence", {}).get("BLD")
    if "BLD" in req and bld and bld.get("hba1c", 0) >= R.DM_LAB_THRESHOLD and not facts["declared"].get("diabetes"):
        req.add("APS")
    return req


def financial_limit(age: int, income: int) -> tuple[str, int]:
    for rid, mx, mult in R.FINANCIAL_MULTIPLES:
        if age <= mx:
            return rid, income * mult
    rid, _, mult = R.FINANCIAL_MULTIPLES[-1]
    return rid, income * mult


def existing_cover(facts: dict) -> int:
    return sum(m["sum_assured"] for m in facts.get("mib", []) if m["kind"] == "inforce")


def underwrite(facts: dict) -> dict[str, Any]:
    """Return the gold decision. Pure function of the facts."""
    d = facts["declared"]
    ev = facts.get("evidence", {})
    req = required_evidence(facts)
    fired: list[str] = []          # rule ids that drove the outcome (for rationale grading)
    debit_lines: list[dict] = []   # [{rule, debits, factor}]
    knockouts: list[tuple[str, str]] = []  # (outcome, rule)
    exclusions: list[str] = []
    flat_extras: list[dict] = []
    refer_reasons: list[str] = []
    nondisclosure = False

    age = facts["age"]
    occ_class = R.OCCUPATIONS.get(facts["occupation"], "2")

    # --- eligibility -------------------------------------------------------------------------
    if not (R.MIN_AGE <= age <= R.MAX_AGE):
        knockouts.append(("decline", R.ELIGIBILITY_ID))

    # --- occupation --------------------------------------------------------------------------
    orid, odebits, oflat, _ = R.OCCUPATION_RULES[occ_class]
    if occ_class == "D":
        knockouts.append(("decline", orid))
    elif odebits:
        debit_lines.append({"rule": orid, "debits": odebits, "factor": "occupation"})
    elif oflat:
        flat_extras.append({"rule": orid, "per_mille": oflat, "factor": "occupation"})

    # --- postpone conditions -------------------------------------------------------------------
    for c in d.get("conditions", []):
        if c in R.POSTPONE_CONDITIONS:
            knockouts.append(("postpone", R.POSTPONE_CONDITIONS[c][0]))

    # --- build ---------------------------------------------------------------------------------
    if "PMR" in req and "PMR" in ev:
        b = bmi(ev["PMR"]["height_cm"], ev["PMR"]["weight_kg"])
    else:
        b = bmi(d["height_cm"], d["weight_kg"])
    rid, debits, outcome = bmi_rule(b)
    if outcome:
        knockouts.append((outcome, rid))
    elif debits:
        debit_lines.append({"rule": rid, "debits": debits, "factor": "build"})

    # --- blood pressure ------------------------------------------------------------------------
    bp = None
    if "PMR" in req and "PMR" in ev:
        bp = (ev["PMR"]["systolic"], ev["PMR"]["diastolic"])
    elif "APS" in req and ev.get("APS", {}).get("hypertension"):
        h = ev["APS"]["hypertension"]
        bp = (h["systolic"], h["diastolic"])
    if bp:
        rid, debits, outcome = bp_rule(*bp)
        if outcome:
            knockouts.append((outcome, rid))
        elif debits:
            debit_lines.append({"rule": rid, "debits": debits, "factor": "blood_pressure"})

    # --- diabetes ------------------------------------------------------------------------------
    bld = ev.get("BLD") if "BLD" in req else None
    aps_dm = ev.get("APS", {}).get("diabetes") if "APS" in req else None
    diabetic = bool(d.get("diabetes")) or bool(aps_dm)
    if bld and bld.get("hba1c", 0) >= R.DM_LAB_THRESHOLD and not d.get("diabetes"):
        diabetic = True
        nondisclosure = True
        fired.append(R.DM_UNDECLARED_ID)
    if diabetic:
        hba1c = aps_dm["hba1c"] if aps_dm else (bld["hba1c"] if bld else None)
        if hba1c is not None:
            rid, debits, outcome = hba1c_rule(hba1c)
            if outcome:
                knockouts.append((outcome, rid))
            else:
                debit_lines.append({"rule": rid, "debits": debits, "factor": "diabetes"})
        if aps_dm:
            months = aps_dm["months_since_dx"]
            if months < R.DM_RECENT_DX_MONTHS:
                knockouts.append(("postpone", R.DM_RECENT_DX_ID))
            if months > R.DM_LONG_DURATION_YEARS * 12:
                debit_lines.append({"rule": R.DM_LONG_DURATION_ID, "debits": R.DM_LONG_DURATION_DEBITS, "factor": "diabetes_duration"})
        if aps_dm and aps_dm.get("insulin"):
            debit_lines.append({"rule": R.DM_INSULIN_ID, "debits": R.DM_INSULIN_DEBITS, "factor": "diabetes_insulin"})

    # --- lipids --------------------------------------------------------------------------------
    if bld:
        rid, debits = lipid_rule(bld["tc"] / bld["hdl"])
        if debits:
            debit_lines.append({"rule": rid, "debits": debits, "factor": "lipids"})

    # --- family history ------------------------------------------------------------------------
    if d.get("family_history_cardiac"):
        debit_lines.append({"rule": R.FAMILY_HISTORY_ID, "debits": R.FAMILY_HISTORY_DEBITS, "factor": "family_history"})

    # --- smoker status -------------------------------------------------------------------------
    st = d.get("smoker_status", "never")
    if st == "current":
        rate_class = "smoker"; fired.append("UW-SMK-1")
    elif st == "ex":
        qm = facts.get("quit_months") or 0
        rate_class = "non_smoker" if qm >= R.SMOKER_QUIT_MONTHS else "smoker"
        fired.append("UW-SMK-2")
    else:
        rate_class = "non_smoker"
    if bld and bld.get("cotinine") == "positive" and rate_class == "non_smoker":
        rate_class = "smoker"; nondisclosure = True; fired.append("UW-SMK-3")

    # --- hobbies -------------------------------------------------------------------------------
    for hb in facts.get("hobbies", []):
        rid, outcome, val = hobby_rule(hb["name"], hb["value"])
        if outcome == "flat":
            flat_extras.append({"rule": rid, "per_mille": val, "factor": hb["name"]})
        elif outcome == "exclusion":
            exclusions.append(val); fired.append(rid)
        else:
            fired.append(rid)

    # --- totals --------------------------------------------------------------------------------
    total_debits = sum(x["debits"] for x in debit_lines)
    trid, tclass = table_for(total_debits)

    declines = [r for o, r in knockouts if o == "decline"]
    postpones = [r for o, r in knockouts if o == "postpone"]
    if declines:
        decision, table_class = "decline", "Decline"
        fired += declines
    elif postpones:
        decision, table_class = "postpone", "Postpone"
        fired += postpones
    elif tclass == "Decline":
        decision, table_class = "decline", "Decline"
        fired.append(trid)
    else:
        decision = "accept_standard" if tclass == "Standard" else "accept_rated"
        table_class = tclass
        fired.append(trid)

    # --- financial -----------------------------------------------------------------------------
    frid, limit = financial_limit(age, facts["income"])
    existing = existing_cover(facts)
    capacity = limit - existing
    requested = facts["sum_assured"]
    offered = 0
    if decision.startswith("accept"):
        if capacity < requested:
            fired.append(frid)
            offered = (max(capacity, 0) // R.FINANCIAL_ROUND) * R.FINANCIAL_ROUND
            if offered <= 0:
                decision, table_class, offered = "decline", "Decline", 0
                fired.append(R.FINANCIAL_NO_CAPACITY_ID)
        else:
            offered = requested
    if not decision.startswith("accept"):
        exclusions, flat_extras = [], []

    # --- referral ------------------------------------------------------------------------------
    if requested > R.AUTHORITY_LIMIT:
        refer_reasons.append(R.AUTHORITY_ID)
    if nondisclosure:
        refer_reasons.append(R.NONDISCLOSURE_ID)
    for m in facts.get("mib", []):
        if m.get("decision") == "declined" and m["months_ago"] <= R.MIB_DECLINE_MONTHS:
            refer_reasons.append(R.MIB_ID)
            break

    fired += [x["rule"] for x in debit_lines] + [x["rule"] for x in flat_extras] + refer_reasons
    seen, fired_u = set(), []
    for r in fired:
        if r not in seen:
            seen.add(r); fired_u.append(r)

    return {
        "decision": decision,
        "table_class": table_class,
        "total_debits": total_debits,
        "debit_lines": debit_lines,
        "rate_class": rate_class,
        "required_evidence": sorted(req),
        "exclusions": sorted(set(exclusions)),
        "flat_extras": flat_extras,
        "offered_sum_assured": offered,
        "should_refer": bool(refer_reasons),
        "refer_reasons": refer_reasons,
        "nondisclosure": nondisclosure,
        "bmi_used": b,
        "financial_limit": limit,
        "existing_cover": existing,
        "cited_rules": fired_u,
    }
