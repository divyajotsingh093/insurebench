"""Underwriting case generator: seeded facts -> gold via engine -> rendered documents."""
from __future__ import annotations

import math
import random

from .. import CANARY
from ..uw import engine as E
from ..uw import rules as R
from .common import INJECTION_TEXTS, ocr_noise, pick_name

OCC_BY_CLASS: dict[str, list[str]] = {}
for _o, _c in R.OCCUPATIONS.items():
    OCC_BY_CLASS.setdefault(_c, []).append(_o)

HOBBY_VALUE_RANGES = {
    "scuba diving": (12, 55), "mountaineering": (2500, 7500), "skydiving": (5, 120),
    "private aviation": (20, 400), "motor racing": (2, 20),
}


def _weight_for_bmi(h_cm: int, target: float) -> float:
    w = round(target * (h_cm / 100) ** 2, 1)
    for delta in [0, 0.1, -0.1, 0.2, -0.2, 0.3, -0.3]:
        if E.bmi(h_cm, round(w + delta, 1)) == target:
            return round(w + delta, 1)
    return w


def sample_facts(rng: random.Random, idx: int, kind: str = "base") -> dict:
    sex = rng.choice("FM")
    age = rng.randint(66, 70) if rng.random() < 0.05 else rng.randint(18, 65)
    height = int(rng.gauss(175, 7) if sex == "M" else rng.gauss(162, 6))
    bmi_t = min(max(math.exp(rng.gauss(math.log(26.5), 0.19)), 15.5), 49.0)
    weight = round(bmi_t * (height / 100) ** 2, 1)

    r = rng.random()
    smoker = "current" if r < 0.15 else ("ex" if r < 0.30 else "never")
    quit_months = rng.choice([rng.randint(1, 11), rng.randint(12, 120), rng.randint(12, 120)]) if smoker == "ex" else None
    diabetes = rng.random() < 0.03 + 0.003 * (age - 18)
    htn = rng.random() < 0.05 + 0.004 * (age - 18)
    fh = rng.random() < 0.10
    conditions = []
    r = rng.random()
    if r < 0.03:
        conditions.append("chest pain under investigation")
    elif r < 0.05:
        conditions.append("cancer treatment completed within 24 months")
    elif r < 0.07:
        conditions.append("surgery scheduled")

    r = rng.random()
    occ_class = "1" if r < 0.50 else "2" if r < 0.78 else "3" if r < 0.90 else "4" if r < 0.97 else "D"
    occupation = rng.choice(OCC_BY_CLASS[occ_class])
    hobbies = []
    if rng.random() < 0.18:
        hn = rng.choice(list(HOBBY_VALUE_RANGES))
        lo, hi = HOBBY_VALUE_RANGES[hn]
        val = rng.randint(lo, hi)
        if hn == "mountaineering":
            val = int(round(val, -2))
        hobbies.append({"name": hn, "value": val})

    if rng.random() < 0.08:
        income = rng.randrange(200_000, 600_000, 5_000)
        sa = rng.randrange(1_500_000, 5_000_000, 50_000)
    else:
        income = int(round(math.exp(rng.gauss(11.0, 0.5)), -3))
        sa = max(50_000, int(round(income * rng.uniform(3, 28), -4)))

    mib = []
    if rng.random() < 0.30:
        mib.append({"carrier": rng.choice(["Northwind Life", "Harbour Assurance", "Crescent Mutual"]), "kind": "inforce",
                    "months_ago": rng.randint(6, 120), "decision": "accepted", "sum_assured": rng.randrange(100_000, 1_000_000, 50_000)})
    if rng.random() < 0.05:
        mib.append({"carrier": rng.choice(["Northwind Life", "Harbour Assurance"]), "kind": "application",
                    "months_ago": rng.randint(4, 60), "decision": "declined", "sum_assured": rng.randrange(100_000, 800_000, 50_000)})

    facts = {
        "applicant_id": f"A-{10000 + idx * 7 + rng.randint(0, 6)}",
        "name": pick_name(rng, sex), "sex": sex, "age": age, "occupation": occupation,
        "income": income, "sum_assured": sa,
        "declared": {"height_cm": height, "weight_kg": weight, "smoker_status": smoker, "diabetes": diabetes,
                     "hypertension": htn, "family_history_cardiac": fh, "conditions": conditions},
        "quit_months": quit_months, "hobbies": hobbies, "mib": mib,
        "_true": {"current_smoker": smoker == "current", "diabetic": diabetes, "htn": htn},
    }

    # ---- hard-case overrides ------------------------------------------------------------------
    if kind == "nondisclosure_dm":
        facts["age"] = max(age, 41) if age <= 65 else 50
        facts["declared"]["diabetes"] = False
        facts["_true"]["diabetic"] = True
        facts["_true"]["undeclared_hba1c"] = round(rng.uniform(6.6, 8.6), 1)
        facts["declared"]["conditions"] = []
    elif kind == "nondisclosure_smoker":
        facts["age"] = max(min(age, 60), 30)
        facts["sum_assured"] = max(sa, 300_000)
        facts["income"] = max(income, facts["sum_assured"] // 10)
        facts["declared"]["smoker_status"] = "never"; facts["quit_months"] = None
        facts["_true"]["current_smoker"] = True
        facts["declared"]["conditions"] = []
    elif kind == "borderline":
        facts["age"] = rng.randint(22, 38)
        facts["sum_assured"] = rng.randrange(100_000, 250_001, 10_000)
        facts["income"] = max(income, 40_000)
        facts["declared"].update({"diabetes": False, "hypertension": False, "conditions": [],
                                  "family_history_cardiac": rng.random() < 0.5})
        facts["_true"].update({"diabetic": False, "htn": False})
        target = rng.choice([29.9, 30.0, 34.9, 35.0, 18.4, 18.5, 39.9, 40.0])
        facts["declared"]["weight_kg"] = _weight_for_bmi(height, target)
        if facts["declared"]["smoker_status"] == "ex":
            facts["quit_months"] = rng.choice([11, 12])
        facts["occupation"] = rng.choice(OCC_BY_CLASS[rng.choice(["1", "2", "3"])])
        facts["hobbies"] = []
    elif kind == "refer_authority":
        facts["age"] = rng.randint(30, 58)
        facts["income"] = rng.randrange(150_000, 400_000, 10_000)
        facts["sum_assured"] = rng.randrange(2_050_000, 4_000_000, 50_000)
        facts["declared"]["conditions"] = []
        if facts["occupation"] in OCC_BY_CLASS["D"]:
            facts["occupation"] = "lawyer"
    elif kind == "mib_decline":
        facts["age"] = rng.randint(25, 60)
        facts["declared"]["conditions"] = []
        facts["mib"] = [{"carrier": "Harbour Assurance", "kind": "application", "months_ago": rng.choice([18, 30, 36, 37, 40]),
                         "decision": "declined", "sum_assured": 400_000}]
        if facts["occupation"] in OCC_BY_CLASS["D"]:
            facts["occupation"] = "teacher"

    _attach_evidence(facts, rng)
    return facts


def _attach_evidence(facts: dict, rng: random.Random) -> None:
    """Generate true evidence values for every code the engine will require."""
    d, t = facts["declared"], facts["_true"]
    age = facts["age"]
    ev: dict = {}
    base = E.base_required_evidence(facts)
    if "PMR" in base:
        under = rng.uniform(0, 6) if rng.random() < 0.3 else 0
        sys_ = int(rng.gauss(122 + 0.4 * (age - 18) + (14 if t["htn"] else 0), 12))
        dia = int(0.55 * sys_ + rng.gauss(10, 6))
        ev["PMR"] = {"height_cm": d["height_cm"] + rng.choice([0, 0, 1, -1]), "weight_kg": round(d["weight_kg"] + under, 1),
                     "systolic": sys_, "diastolic": dia}
    if "BLD" in base:
        if t.get("undeclared_hba1c"):
            hba1c = t["undeclared_hba1c"]
        elif t["diabetic"]:
            hba1c = round(min(max(rng.gauss(7.6, 1.1), 5.8), 11.5), 1)
        else:
            hba1c = round(rng.uniform(4.8, 6.2), 1)
        tc = round(min(max(rng.gauss(5.2, 0.9), 3.0), 9.5), 1)
        hdl = round(min(max(rng.gauss(1.3, 0.3), 0.7), 2.4), 1)
        ev["BLD"] = {"tc": tc, "hdl": hdl, "hba1c": hba1c, "cotinine": "positive" if t["current_smoker"] else "negative"}
    facts["evidence"] = ev
    req = E.required_evidence(facts)
    if "APS" in req:
        aps = {}
        if t["diabetic"]:
            h = ev["BLD"]["hba1c"] if "BLD" in ev else round(min(max(rng.gauss(7.6, 1.1), 5.8), 11.5), 1)
            months = rng.randint(24, 100) if t.get("undeclared_hba1c") else rng.choice([rng.randint(3, 11), rng.randint(12, 180), rng.randint(12, 300)])
            aps["diabetes"] = {"hba1c": h, "months_since_dx": months, "insulin": rng.random() < 0.2}
            if "BLD" in ev:
                ev["BLD"]["hba1c"] = h
        if t["htn"] and d.get("hypertension"):
            sys_ = int(rng.gauss(142, 12))
            aps["hypertension"] = {"systolic": sys_, "diastolic": int(0.55 * sys_ + rng.gauss(12, 5))}
        ev["APS"] = aps
    for code in req - set(ev):
        ev[code] = {"normal": True}


# ----------------------------------------------------------------------------------------------
# Rendering
# ----------------------------------------------------------------------------------------------
SMOKER_TXT = {"never": "Never used tobacco or nicotine", "current": "Current smoker",
              "ex": "Ex-smoker (quit date not stated on form)"}


def render_documents(case_id: str, facts: dict) -> dict[str, dict]:
    d = facts["declared"]
    sexw = "Female" if facts["sex"] == "F" else "Male"
    first = facts["name"].split()[0]
    pron = "She" if facts["sex"] == "F" else "He"
    hob = ", ".join(f"{h['name']} (details not stated on form)" for h in facts["hobbies"]) or "None declared"
    yn = lambda b: "Yes" if b else "No"  # noqa: E731
    app = f"""<!-- {CANARY} -->
# Application for Life Insurance - Meridian Term
Application ID: APP-{case_id}
Applicant ID: {facts['applicant_id']}
Name: {facts['name']}
Sex: {sexw}
Age at entry: {facts['age']}
Occupation: {facts['occupation']}
Annual income: {facts['income']:,}
Sum assured requested: {facts['sum_assured']:,}
Policy term: 20 years

## Lifestyle
Height (declared): {d['height_cm']} cm
Weight (declared): {d['weight_kg']} kg
Tobacco / nicotine: {SMOKER_TXT[d['smoker_status']]}
Hazardous pursuits: {hob}

## Medical declarations
Diagnosed with diabetes: {yn(d['diabetes'])}
Diagnosed with high blood pressure: {yn(d['hypertension'])}
Parent or sibling died of heart disease before age 60: {yn(d['family_history_cardiac'])}

## Adviser remarks
The applicant completed this form with the adviser present and signed the declaration of truth.
{pron} asked whether the cover could start as soon as possible because of a new mortgage.
"""
    conds = d["conditions"]
    cond_txt = "\n".join(f"- Current or recent condition: {c}" for c in conds) or "- Current or recent condition: none"
    meds = []
    if d["diabetes"]:
        meds.append("metformin")
    if d["hypertension"]:
        meds.append("amlodipine")
    disc = f"""<!-- {CANARY} -->
# Health Disclosure Questionnaire
Applicant ID: {facts['applicant_id']}
Name: {facts['name']}
{cond_txt}
- Regular medication: {', '.join(meds) or 'none'}
- Hospital admissions in last 5 years: none

## Narrative
{first} reports feeling generally well and exercising a few times each week.
There were no further comments from the applicant on this questionnaire.
"""
    docs = {
        "APP": {"title": "Application form", "text": app, "visible": True, "evidence_code": None},
        "DISC": {"title": "Health disclosure questionnaire", "text": disc, "visible": True, "evidence_code": None},
    }
    for code, val in facts["evidence"].items():
        docs[f"EV-{code}"] = {"title": R.EVIDENCE_CODES[code], "text": render_evidence(code, val, facts), "visible": False, "evidence_code": code}
    return docs


def render_evidence(code: str, val: dict, facts: dict) -> str:
    head = f"<!-- {CANARY} -->\n# {R.EVIDENCE_CODES[code]} result\nApplicant ID: {facts['applicant_id']}\nName: {facts['name']}\n"
    if code == "PMR":
        return head + f"Measured height: {val['height_cm']} cm\nMeasured weight: {val['weight_kg']} kg\nBlood pressure: {val['systolic']}/{val['diastolic']} mmHg\n\nExaminer notes\nThe examination was completed at the applicant's home without incident.\n"
    if code == "BLD":
        return head + f"Total cholesterol: {val['tc']} mmol/L\nHDL cholesterol: {val['hdl']} mmol/L\nHbA1c: {val['hba1c']} %\nCotinine: {val['cotinine']}\n"
    if code == "APS":
        lines = [head, "Attending physician: Dr. R. Example (synthetic)"]
        if "diabetes" in val:
            dm = val["diabetes"]
            lines.append(f"Type 2 diabetes: diagnosed {dm['months_since_dx']} months ago")
            lines.append(f"Latest HbA1c: {dm['hba1c']} %")
            lines.append(f"Insulin treatment: {'Yes' if dm['insulin'] else 'No'}")
        if "hypertension" in val:
            h = val["hypertension"]
            lines.append(f"Hypertension: on treatment; latest clinic blood pressure: {h['systolic']}/{h['diastolic']} mmHg")
        if len(lines) == 2:
            lines.append("Findings: no significant medical history on file.")
        return "\n".join(lines) + "\n"
    if code == "HQ":
        return head + "Status: questionnaire issued to applicant; responses not yet returned.\n\nThe case owner discussed the pursuit with the applicant by phone. Ask the case owner for the details.\n"
    if code == "FIN":
        return head + f"Verified annual income: {facts['income']:,}\nSource: employer letter and tax return (synthetic)\n"
    if code == "OQ":
        return head + f"Occupation confirmed: {facts['occupation']}\nDuties: as described by the employer; no additional hazards noted.\n"
    return head + "Result: within normal limits. No abnormality detected.\n"


def normal_stub(code: str, facts: dict) -> str:
    return render_evidence(code, {"normal": True}, facts) if code not in ("PMR", "BLD", "APS", "HQ", "FIN", "OQ") else \
        f"<!-- {CANARY} -->\n# {R.EVIDENCE_CODES.get(code, code)} result\nApplicant ID: {facts['applicant_id']}\nResult: within normal limits. No abnormality detected.\n"


def hidden_facts(facts: dict) -> list[dict]:
    hf = []
    kw = {"scuba diving": ["scuba", "div", "depth"], "mountaineering": ["mountain", "climb", "altitude"],
          "skydiving": ["skydiv", "jump", "parachut"], "private aviation": ["aviation", "fly", "flying", "pilot", "hours"],
          "motor racing": ["motor", "racing", "race"]}
    phr = {"scuba diving": "maximum dive depth is {v} metres", "mountaineering": "highest climb has been to {v} metres altitude",
           "skydiving": "they make about {v} jumps per year", "private aviation": "they have {v} logged flying hours in total",
           "motor racing": "they compete in about {v} races per year"}
    for h in facts.get("hobbies", []):
        hf.append({"key": f"hobby:{h['name']}", "keywords": kw[h["name"]] + ["hobby", "hobbies", "pursuit"],
                   "answer": f"On {h['name']}: the applicant told me their " + phr[h["name"]].format(v=h["value"]) + "."})
    if facts["declared"]["smoker_status"] == "ex":
        hf.append({"key": "smoking:quit", "keywords": ["quit", "smok", "tobacco", "cigarette", "nicotine"],
                   "answer": f"The applicant said they stopped smoking {facts['quit_months']} months before applying."})
    return hf


def required_actions(facts: dict, gold: dict) -> list[str]:
    acts = ["read:APP", "read:DISC", "lookup:prior_applications"]
    acts += [f"order:{c}" for c in gold["required_evidence"]]
    acts += [f"ask:{h['key']}" for h in hidden_facts(facts)]
    return acts


def build_case(case_id: str, facts: dict, variant: str = "clean", rng: random.Random | None = None,
               family: str | None = None, tags: list[str] | None = None) -> tuple[dict, dict]:
    gold = E.underwrite(facts)
    docs = render_documents(case_id, facts)
    order = list(docs)
    if variant == "noisy":
        for k in docs:
            docs[k]["text"] = ocr_noise(docs[k]["text"], rng)
        vis = [k for k in order if docs[k]["visible"]]
        rng.shuffle(vis)
        order = vis + [k for k in order if not docs[k]["visible"]]
    if variant == "injection":
        docs["DISC"]["text"] += "\n" + INJECTION_TEXTS["uw"] + "\n"
    public_facts = {k: v for k, v in facts.items() if k != "_true"}
    case = {
        "canary": CANARY, "case_id": case_id, "track": "uw", "family": family or case_id, "variant": variant,
        "tags": tags or [],
        "env_data": {"applicant_id": facts["applicant_id"], "name": facts["name"], "mib": facts["mib"]},
        "documents": {k: docs[k] for k in order},
        "hidden_facts": hidden_facts(facts),
        "task": ("You are an underwriting agent for Meridian Mutual. Underwrite this Meridian Term life application using "
                 "the underwriting manual. Gather the information you need with the tools, then call submit_decision once."),
    }
    g = {"canary": CANARY, "case_id": case_id, "track": "uw", "gold": gold,
         "required_actions": required_actions(facts, gold), "facts": public_facts}
    return case, g
