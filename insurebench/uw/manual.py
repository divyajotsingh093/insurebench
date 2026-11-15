"""Render the Meridian Mutual underwriting manual (markdown) from the rule tables in rules.py."""
from __future__ import annotations

from .. import CANARY, CARRIER
from . import rules as R


def _fmt_int(n: int) -> str:
    return f"{n:,}"


def sections() -> list[tuple[str, str, str]]:
    """Return manual sections as (section_id, title, markdown_body). Used by search_manual."""
    out: list[tuple[str, str, str]] = []

    out.append(("UW-0", "Purpose, scope and order of assessment", f"""
This manual governs individual term life underwriting for {CARRIER} ("Meridian Term"). All amounts are in
generic currency units. Assess each application in this order:

1. Eligibility ({R.ELIGIBILITY_ID}) and declined occupations (UW-OCC-5) -> decline.
2. Knock-out medical findings: build UW-BMI-7, diabetes UW-DM-4 -> decline.
3. Postpone triggers: UW-PP-*, UW-BP-5, {R.DM_RECENT_DX_ID} -> postpone. A decline trigger takes precedence over a postpone trigger.
4. Sum debits from build, blood pressure, diabetes, lipids, family history and occupation class 3, then map total debits to a table class (UW-TBL-*).
5. Apply hazardous-hobby and occupation flat extras and exclusions (accepted cases only).
6. Apply financial limits (UW-FIN-*) to set the offered sum assured.
7. Determine smoker rate class (UW-SMK-*).
8. Determine whether the case must be referred to a senior underwriter ({R.AUTHORITY_ID}, {R.NONDISCLOSURE_ID}, {R.MIB_ID}).

Debits are additive. Flat extras and exclusions do not add debits. Cite rule IDs in your rationale.
""".strip()))

    rows = "\n".join(
        f"| {rid} | {lo:.1f} | {'and above' if hi > 100 else f'< {hi:.1f}'} | {('+' + str(d)) if d is not None else '-'} | {o or 'rate by debits'} |"
        for rid, lo, hi, d, o in R.BMI_TABLE)
    out.append(("UW-BMI", "Build (BMI) table", f"""
BMI = weight (kg) / height (m)^2, rounded to one decimal place. {R.EVIDENCE_SOURCE_RULES['UW-SRC-1']}

| Rule | BMI from | BMI to | Debits | Outcome |
|---|---|---|---|---|
{rows}
""".strip()))

    rows = "\n".join(
        f"| {rid} | {'> 175' if s > 900 else f'<= {s}'} | {'> 105' if di > 900 else f'<= {di}'} | {('+' + str(d)) if d is not None else '-'} | {o or 'rate by debits'} |"
        for rid, s, di, d, o in R.BP_TABLE)
    out.append(("UW-BP", "Blood pressure", f"""
Take the band for the systolic reading and the band for the diastolic reading separately; rate on the WORSE (higher) band.

| Rule | Systolic | Diastolic | Debits | Outcome |
|---|---|---|---|---|
{rows}
""".strip()))

    rows = "\n".join(
        f"| {rid} | {lo:.1f} | {'and above' if hi > 50 else f'< {hi:.1f}'} | {('+' + str(d)) if d is not None else '-'} | {o or 'rate by debits'} |"
        for rid, lo, hi, d, o in R.DM_HBA1C_TABLE)
    out.append(("UW-DM", "Type 2 diabetes", f"""
Rate on HbA1c (%). {R.EVIDENCE_SOURCE_RULES['UW-SRC-2']}

| Rule | HbA1c from | HbA1c to | Debits | Outcome |
|---|---|---|---|---|
{rows}

Adjustments (in addition to the HbA1c debits):
- {R.DM_RECENT_DX_ID}: diagnosed fewer than {R.DM_RECENT_DX_MONTHS} months ago -> postpone.
- {R.DM_LONG_DURATION_ID}: duration since diagnosis more than {R.DM_LONG_DURATION_YEARS} years -> +{R.DM_LONG_DURATION_DEBITS} debits.
- {R.DM_INSULIN_ID}: treated with insulin -> +{R.DM_INSULIN_DEBITS} debits.
- {R.DM_UNDECLARED_ID}: HbA1c >= {R.DM_LAB_THRESHOLD} on the blood profile where diabetes was NOT declared: treat as diabetic,
  rate per the HbA1c table, obtain an APS (UW-EV-5) and treat as a material non-disclosure ({R.NONDISCLOSURE_ID}).
""".strip()))

    rows = "\n".join(f"| {rid} | {'> 8.0' if mx > 100 else f'<= {mx:.1f}'} | {('+' + str(d)) if d else '0'} |" for rid, mx, d in R.LIPID_TABLE)
    out.append(("UW-LIP", "Lipids (cholesterol ratio)", f"""
Ratio = total cholesterol / HDL, rounded to one decimal. Rated only when a blood profile (BLD) is required evidence.

| Rule | TC/HDL ratio | Debits |
|---|---|---|
{rows}
""".strip()))

    out.append(("UW-FH", "Family history", f"""
{R.FAMILY_HISTORY_ID}: a parent or sibling died of heart disease before age 60 -> +{R.FAMILY_HISTORY_DEBITS} debits.
""".strip()))

    out.append(("UW-SMK", "Smoker status and rate class", "\n".join(f"- {k}: {v}" for k, v in R.SMOKER_RULES.items()) +
                "\n\nThe smoker/non-smoker rate class is independent of the table class. Ask how long ago an ex-smoker quit if it is not documented."))

    occ_rows = "\n".join(f"| {rid} | Class {c} | {desc} |" for c, (rid, _, _, desc) in R.OCCUPATION_RULES.items())
    occ_list = "\n".join(f"- {o}: class {c}" for o, c in sorted(R.OCCUPATIONS.items(), key=lambda x: (x[1], x[0])))
    out.append(("UW-OCC", "Occupation classes", f"""
| Rule | Class | Treatment |
|---|---|---|
{occ_rows}

Occupation list:
{occ_list}

Occupations not listed: treat as class 2.
""".strip()))

    hb = []
    for name, spec in R.HOBBIES.items():
        lines = []
        prev = None
        for rid, mx, outcome, val in spec["bands"]:
            rng = (f"<= {mx}" if prev is None else f"{prev + 1} to {mx}") if mx < 10**8 else (f">= {prev + 1}" if prev is not None else "any")
            treat = {"none": "no loading", "flat": f"flat extra {val} per mille", "exclusion": f"exclusion {val}"}[outcome]
            lines.append(f"| {rid} | {name} | {rng} {spec['unit']} | {treat} |")
            prev = mx
        hb.extend(lines)
    exc = "\n".join(f"- {k}: {v}" for k, v in R.EXCLUSIONS.items())
    out.append(("UW-HOB", "Hazardous hobbies, flat extras and exclusions", f"""
The application only names the pursuit; the detail (depth, altitude, jumps, hours, races) must be obtained (hazardous
pursuits questionnaire HQ, or ask the case owner). Flat extras and exclusions apply only to accepted cases.

| Rule | Pursuit | Exposure | Treatment |
|---|---|---|---|
{chr(10).join(hb)}

Exclusion wordings:
{exc}
""".strip()))

    pp = "\n".join(f"- {rid}: {desc} (condition key: \"{k}\")" for k, (rid, desc) in R.POSTPONE_CONDITIONS.items())
    out.append(("UW-PP", "Postpone triggers", f"""
{pp}
- UW-BP-5: blood pressure above the highest rateable band -> postpone.
- {R.DM_RECENT_DX_ID}: diabetes diagnosed fewer than {R.DM_RECENT_DX_MONTHS} months ago -> postpone.
""".strip()))

    tb = "\n".join(f"| {rid} | {'>= ' + str(R.TABLE_BANDS[i-1][1] + 1) if mx > 10**8 else ('0' if i == 0 else str(R.TABLE_BANDS[i-1][1] + 1)) + (' to ' + str(mx) if mx < 10**8 else '')} | {cls} | {('+' + str(p) + '%') if p is not None else '-'} |"
                   for i, (rid, mx, cls, p) in enumerate(R.TABLE_BANDS))
    out.append(("UW-TBL", "Debits to table class", f"""
| Rule | Total debits | Class | Extra premium |
|---|---|---|---|
{tb}

Decision vocabulary: accept_standard (class Standard), accept_rated (T2-T8), postpone, decline.
""".strip()))

    fr = "\n".join(f"| {rid} | <= {mx} | {m}x annual income |" for rid, mx, m in R.FINANCIAL_MULTIPLES)
    out.append(("UW-FIN", "Financial limits", f"""
Maximum total cover = annual income x multiple below, LESS existing in-force cover at all carriers (see the MIB-style prior
application lookup). If the requested sum assured exceeds the remaining capacity, offer the remaining capacity rounded DOWN to
the nearest {_fmt_int(R.FINANCIAL_ROUND)}. {R.FINANCIAL_NO_CAPACITY_ID}: if the remaining capacity is zero or less, decline on financial grounds.

| Rule | Age | Multiple |
|---|---|---|
{fr}
""".strip()))

    out.append(("UW-REF", "Referral to senior underwriter", f"""
Refer (refer_to_senior and set refer=true in the decision) when ANY of the following apply. Still record the decision you recommend.
- {R.AUTHORITY_ID}: requested sum assured above {_fmt_int(R.AUTHORITY_LIMIT)}.
- {R.NONDISCLOSURE_ID}: material non-disclosure detected (e.g. UW-SMK-3, {R.DM_UNDECLARED_ID}).
- {R.MIB_ID}: a decline by any carrier within the last {R.MIB_DECLINE_MONTHS} months on the prior application lookup.
Do not refer for any other reason.
""".strip()))

    hdr = "| Age band | " + " | ".join(n for n, _ in R.SA_BANDS) + " |"
    sep = "|---" * (len(R.SA_BANDS) + 1) + "|"
    grid_rows = "\n".join(f"| {ab} | " + " | ".join(", ".join(c) or "none (declaration only)" for c in R.EVIDENCE_GRID[ab]) + " |" for ab, _, _ in R.AGE_BANDS)
    codes = "\n".join(f"- {k}: {v}" for k, v in R.EVIDENCE_CODES.items())
    trig = "\n".join(f"- {k}: {v}" for k, v in R.EVIDENCE_TRIGGERS.items())
    out.append(("UW-EV", "Evidence requirements", f"""
{R.EVIDENCE_GRID_ID}: routine evidence by age at entry and requested sum assured.

{hdr}
{sep}
{grid_rows}

Additional triggered evidence:
{trig}

Evidence codes:
{codes}

Use order_evidence(code) to obtain results. Ordering evidence that is not required wastes budget.
""".strip()))
    return out


def render_manual() -> str:
    parts = [f"<!-- {CANARY} -->", f"# {CARRIER} Underwriting Manual - Meridian Term (synthetic, v0)", "",
             "> Synthetic manual for the InsureBench benchmark. Not real underwriting guidance.", ""]
    for sid, title, body in sections():
        parts += [f"## [{sid}] {title}", "", body, ""]
    return "\n".join(parts)
