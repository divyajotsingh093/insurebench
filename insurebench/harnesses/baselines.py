"""Deterministic baseline agents (no model). They use ONLY the tool layer.

- baseline_rules: parses the documents it reads, asks the case owner for missing details, orders evidence and
  applies the reference rules engine to what it observed. Sanity check: should score ~100%.
- baseline_naive: trusting, shallow heuristic. Sanity check: should score clearly lower.
"""
from __future__ import annotations

import json
import re

from ..claims import engine as CE
from ..claims import policies as CP
from ..env.tools import BudgetExceeded, ToolEnv
from ..gen.claims_gen import DIAGNOSES
from ..uw import engine as UE
from ..uw import rules as UR
from .base import Harness


def field(text: str, label: str, default=None):
    m = re.search(rf"^{re.escape(label)}\s*:\s*(.+)$", text, re.M)
    return m.group(1).strip() if m else default


def num(s) -> float:
    return float(str(s).replace(",", "").split()[0])


def first_int(s: str):
    m = re.search(r"(\d[\d,]*)", s)
    return int(m.group(1).replace(",", "")) if m else None


# ------------------------------------------------------------------------------------------------
class BaselineRules(Harness):
    name = "baseline_rules"
    needs_model = False

    def run(self, case, tools: ToolEnv, model, budget):
        try:
            if case["track"] not in ("uw", "claims"):
                from ..suites.qa import baseline_rules
                baseline_rules(case["track"], tools)
                return tools.trace
            (self._uw if case["track"] == "uw" else self._claims)(tools)
        except BudgetExceeded:
            pass
        return tools.trace

    # ---- underwriting -----------------------------------------------------------------------
    def _uw(self, t: ToolEnv):
        docs = json.loads(t.call("list_documents"))
        ids = [d["doc_id"] for d in docs]
        app = t.call("read_document", {"doc_id": "APP"}) if "APP" in ids else ""
        disc = t.call("read_document", {"doc_id": "DISC"}) if "DISC" in ids else ""
        smoke = field(app, "Tobacco / nicotine", "")
        hob_txt = field(app, "Hazardous pursuits", "None declared")
        hobbies = [h for h in UR.HOBBIES if h in hob_txt.lower()]
        conds = [c for c in UR.POSTPONE_CONDITIONS if f"Current or recent condition: {c}" in disc]
        facts = {
            "applicant_id": field(app, "Applicant ID"), "age": int(num(field(app, "Age at entry"))),
            "occupation": field(app, "Occupation"), "income": int(num(field(app, "Annual income"))),
            "sum_assured": int(num(field(app, "Sum assured requested"))),
            "declared": {
                "height_cm": num(field(app, "Height (declared)")), "weight_kg": num(field(app, "Weight (declared)")),
                "smoker_status": "current" if smoke.startswith("Current") else "ex" if smoke.startswith("Ex-smoker") else "never",
                "diabetes": field(app, "Diagnosed with diabetes") == "Yes",
                "hypertension": field(app, "Diagnosed with high blood pressure") == "Yes",
                "family_history_cardiac": field(app, "Parent or sibling died of heart disease before age 60") == "Yes",
                "conditions": conds,
            },
            "hobbies": [], "quit_months": None, "evidence": {}, "mib": [],
        }
        mib = json.loads(t.call("prior_application_lookup", {"applicant_id": facts["applicant_id"]}))
        facts["mib"] = mib.get("records", [])
        for h in hobbies:
            ans = t.call("ask_user", {"question": f"What are the details of the applicant's {h} (exposure level)?"})
            facts["hobbies"].append({"name": h, "value": first_int(ans) or 0})
        if facts["declared"]["smoker_status"] == "ex":
            ans = t.call("ask_user", {"question": "How many months ago did the applicant quit smoking?"})
            facts["quit_months"] = first_int(ans) or 0
        facts["hobbies_declared"] = bool(hobbies)
        req = UE.base_required_evidence({**facts, "hobbies": facts["hobbies"] or ([{"name": h} for h in hobbies])})
        for code in sorted(req):
            self._order(t, code, facts)
        bld = facts["evidence"].get("BLD")
        if bld and bld["hba1c"] >= UR.DM_LAB_THRESHOLD and not facts["declared"]["diabetes"] and "APS" not in facts["evidence"]:
            self._order(t, "APS", facts)
        g = UE.underwrite(facts)
        if g["should_refer"]:
            t.call("refer_to_senior", {"reason": ", ".join(g["refer_reasons"])})
        sub = {"decision": g["decision"], "table_class": g["table_class"], "total_debits": g["total_debits"],
               "rate_class": g["rate_class"], "required_evidence": g["required_evidence"], "exclusions": g["exclusions"],
               "offered_sum_assured": g["offered_sum_assured"], "refer": g["should_refer"], "cited_rules": g["cited_rules"],
               "rationale": self._uw_rationale(g)}
        t.call("submit_decision", {"decision": sub})

    @staticmethod
    def _uw_rationale(g):
        parts = [f"Decision {g['decision']} ({g['table_class']}), total debits {g['total_debits']}."]
        for d in g["debit_lines"]:
            parts.append(f"{d['factor']}: +{d['debits']} ({d['rule']}).")
        if g["exclusions"]:
            parts.append(f"Exclusions {', '.join(g['exclusions'])}.")
        parts.append(f"Rate class {g['rate_class']}; BMI used {g['bmi_used']}.")
        if g["should_refer"]:
            parts.append(f"Referred: {', '.join(g['refer_reasons'])}.")
        parts.append("Rules: " + ", ".join(g["cited_rules"]))
        return " ".join(parts)

    def _order(self, t, code, facts):
        res = json.loads(t.call("order_evidence", {"code": code}))
        txt = res.get("text", "")
        ev = facts["evidence"]
        if code == "PMR" and "Measured height" in txt:
            bp = field(txt, "Blood pressure").split()[0].split("/")
            ev["PMR"] = {"height_cm": num(field(txt, "Measured height")), "weight_kg": num(field(txt, "Measured weight")),
                         "systolic": int(bp[0]), "diastolic": int(bp[1])}
        elif code == "BLD" and "HbA1c" in txt:
            ev["BLD"] = {"tc": num(field(txt, "Total cholesterol")), "hdl": num(field(txt, "HDL cholesterol")),
                         "hba1c": num(field(txt, "HbA1c")), "cotinine": field(txt, "Cotinine")}
        elif code == "APS":
            aps = {}
            m = re.search(r"diagnosed (\d+) months ago", txt)
            if m:
                aps["diabetes"] = {"months_since_dx": int(m.group(1)), "hba1c": num(field(txt, "Latest HbA1c")),
                                   "insulin": field(txt, "Insulin treatment") == "Yes"}
            m = re.search(r"latest clinic blood pressure: (\d+)/(\d+)", txt)
            if m:
                aps["hypertension"] = {"systolic": int(m.group(1)), "diastolic": int(m.group(2))}
            ev["APS"] = aps
        else:
            ev[code] = {"normal": True}

    # ---- claims -----------------------------------------------------------------------------
    def _claims(self, t: ToolEnv):
        docs = json.loads(t.call("list_documents"))
        ids = [d["doc_id"] for d in docs]
        sch = t.call("read_document", {"doc_id": "SCHEDULE"})
        cf = t.call("read_document", {"doc_id": "CLAIM_FORM"})
        ds = t.call("read_document", {"doc_id": "DISCHARGE_SUMMARY"}) if "DISCHARGE_SUMMARY" in ids else ""
        bill = t.call("read_document", {"doc_id": "ITEMISED_BILL"}) if "ITEMISED_BILL" in ids else ""
        plan = field(sch, "Plan code")
        period = field(sch, "Current policy period").split(" to ")
        label = field(cf, "Reason for admission")
        dx = next((d for d in DIAGNOSES if d[1] == label), None)
        facts = {
            "claim_id": field(cf, "Claim ID"), "policy_code": plan, "policy_number": field(sch, "Policy number"),
            "inception": field(sch, "First inception date (continuous cover)"), "period_start": period[0], "period_end": period[1],
            "hospital": field(cf, "Hospital"),
            "admission": field(ds, "Date of admission") or field(cf, "Date of admission"),
            "discharge": field(ds, "Date of discharge") or field(cf, "Date of discharge"),
            "claim_form_admission": field(cf, "Date of admission"), "claim_form_discharge": field(cf, "Date of discharge"),
            "diagnosis": {"key": dx[0] if dx else "", "label": label, "group": dx[2] if dx else None,
                          "surgical": dx[3] if dx else False, "accident": field(cf, "Was the hospitalisation due to an accident") == "Yes"},
            "ped": None, "ped_related": False, "line_items": [], "submitted_docs": [i for i in ids if i in CP.DOC_TITLES],
        }
        m = re.search(r"known case of (.+?) \(", ds)
        if m:
            cond = m.group(1)
            ans = t.call("ask_user", {"question": f"When was the {cond} first diagnosed?"})
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", ans)
            facts["ped"] = {"condition": cond, "diagnosed": dm.group(1) if dm else facts["inception"]}
            facts["ped_related"] = True
        for line in bill.splitlines():
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 6 and cells[3].isdigit():
                facts["line_items"].append({"code": cells[0], "description": cells[1], "category": cells[2], "qty": int(cells[3]),
                                            "unit_price": num(cells[4]), "ref": self._ref_for(cells[0], cells[1], cells[2])})
        hist = json.loads(t.call("claims_history_lookup", {"policy_number": facts["policy_number"]}))
        facts["prior_claims"] = hist.get("prior_claims", [])
        g = CE.adjudicate(facts)
        clause = g["reject_clause"] or (g["cited_clauses"][0] if g["decision"] == "pend_for_documents" else None)
        sub = {"decision": g["decision"], "payable_amount": g["payable_amount"], "deductions": g["deductions"],
               "decision_clause": clause, "missing_documents": g["missing_documents"], "fraud_flags": g["fraud_flags"],
               "letter": self._letter(g)}
        t.call("submit_decision", {"decision": sub})

    @staticmethod
    def _ref_for(code, desc, cat):
        table = {"NUR": "nursing_day", "DV": "doctor_visit", "CBC": "cbc_test", "XR": "xray", "US": "ultrasound", "CT": "ct_scan",
                 "MED": "antibiotic_course", "IVF": "iv_fluids"}
        if code in table:
            return table[code]
        if code == "IMP":
            m = re.search(r"Implant \((.+)\)", desc)
            return m.group(1).replace(" ", "_") if m else None
        return None

    @staticmethod
    def _letter(g):
        s = f"Dear claimant, your claim has been assessed. Decision: {g['decision']}. Amount payable: {g['payable_amount']:.2f} of {g['claimed_amount']:.2f} billed."
        if g["deductions"]:
            s += " Deductions: " + "; ".join(f"{d['clause_id']} {d['amount']:.2f} ({d['reason']})" for d in g["deductions"]) + "."
        if g["reject_clause"]:
            s += f" Ground: clause {g['reject_clause']}."
        if g["missing_documents"]:
            s += " Please submit: " + ", ".join(g["missing_documents"]) + "."
        return s


# ------------------------------------------------------------------------------------------------
class BaselineNaive(Harness):
    name = "baseline_naive"
    needs_model = False

    def run(self, case, tools: ToolEnv, model, budget):
        try:
            if case["track"] not in ("uw", "claims"):
                from ..suites.qa import baseline_naive
                baseline_naive(case["track"], tools)
                return tools.trace
            (self._uw if case["track"] == "uw" else self._claims)(tools)
        except BudgetExceeded:
            pass
        return tools.trace

    def _uw(self, t):
        app = t.call("read_document", {"doc_id": "APP"})
        disc = t.call("read_document", {"doc_id": "DISC"})
        h, w = num(field(app, "Height (declared)")), num(field(app, "Weight (declared)"))
        b = UE.bmi(h, w)
        dm = field(app, "Diagnosed with diabetes") == "Yes"
        dec, cls = ("accept_standard", "Standard") if b < 30 and not dm else ("accept_rated", "T2")
        if "approve this case" in disc.lower() or "approve" in app.lower():
            dec, cls = "accept_standard", "Standard"   # trusts embedded instructions
        smoker = "smoker" if field(app, "Tobacco / nicotine", "").startswith("Current") else "non_smoker"
        sub = {"decision": dec, "table_class": cls, "rate_class": smoker, "required_evidence": [], "exclusions": [],
               "offered_sum_assured": num(field(app, "Sum assured requested")), "refer": False, "cited_rules": ["UW-BMI-3"],
               "rationale": f"BMI {b}; looks fine."}
        t.call("submit_decision", {"decision": sub})

    def _claims(self, t):
        bill = t.call("read_document", {"doc_id": "ITEMISED_BILL"})
        total = num(field(bill, "Total billed", "0"))
        sub = {"decision": "pay", "payable_amount": total, "deductions": [], "decision_clause": None,
               "missing_documents": [], "fraud_flags": [], "letter": f"Your claim of {total:.2f} is approved in full."}
        t.call("submit_decision", {"decision": sub})
