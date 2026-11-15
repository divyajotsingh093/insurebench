"""Graders and baseline agents for the QA-style suites (appeals_real, coding_validity, coverage_qa)."""
from __future__ import annotations

import json
import re

from ..claims import policies as P
from ..config import ROOT
from ..env.tools import ToolEnv

METRICS = {
    "appeals": ["decision_exact", "upheld_recall", "overturned_recall"],
    "coding": ["invalid_f1", "non_billable_f1", "all_exact"],
    "coverage_qa": ["answer_exact", "clause_exact"],
}


def _f1(p, g):
    p, g = set(p or []), set(g or [])
    if not p and not g:
        return 1.0
    tp = len(p & g)
    return 0.0 if tp == 0 else round(2 * tp / (len(p) + len(g)), 4)


def _norm_code(c: str) -> str:
    c = c.strip().upper().replace(".", "")
    return c if len(c) <= 3 else c[:3] + "." + c[3:]


def _answer_match(pred, gold) -> bool:
    if isinstance(gold, str):
        return str(pred).strip().lower().startswith(gold)
    try:
        v = float(str(pred).replace(",", "").replace("%", "").strip().split()[0])
    except (ValueError, IndexError):
        return False
    return abs(v - float(gold)) <= max(0.01 * abs(float(gold)), 0.5)


def grade(track: str, sub: dict | None, gold_rec: dict) -> dict:
    g = gold_rec["gold"]
    base = {"submitted": bool(sub), "cited": 0, "hallucinated": 0, "pred_refer": False, "gold_refer": False}
    if track == "appeals":
        pred = (sub or {}).get("determination")
        ok = int(pred == g["decision"])
        base.update({"decision_exact": ok, "upheld_recall": ok if g["decision"] == "upheld" else None,
                     "overturned_recall": ok if g["decision"] == "overturned" else None, "primary_correct": ok, "pred_decision": pred})
    elif track == "coding":
        inv = [_norm_code(c) for c in (sub or {}).get("invalid_codes", [])]
        nb = [_norm_code(c) for c in (sub or {}).get("non_billable_codes", [])]
        exact = int(sub is not None and set(inv) == set(g["invalid_codes"]) and set(nb) == set(g["non_billable_codes"]))
        base.update({"invalid_f1": _f1(inv, g["invalid_codes"]) if sub else 0.0, "non_billable_f1": _f1(nb, g["non_billable_codes"]) if sub else 0.0,
                     "all_exact": exact, "primary_correct": exact,
                     "pred_decision": None if sub is None else ("clean" if not (inv or nb) else "errors")})
    else:
        ans = (sub or {}).get("answer")
        cl = (sub or {}).get("clause_id")
        a_ok = int(sub is not None and _answer_match(ans, g["answer"]))
        c_ok = int(cl == g["clause_id"])
        base.update({"answer_exact": a_ok, "clause_exact": c_ok, "primary_correct": a_ok, "pred_decision": str(ans),
                     "cited": 1 if cl else 0, "hallucinated": int(bool(cl) and cl not in P.all_clause_ids())})
    return base


# ------------------------------------------------------------------------------------------------
_PRIORS = None


def _priors():
    global _PRIORS
    if _PRIORS is None:
        p = ROOT / "data" / "sources" / "imr_priors.json"
        _PRIORS = json.loads(p.read_text()) if p.exists() else {}
    return _PRIORS


def baseline_rules(track: str, t: ToolEnv):
    doc_id = list(t.case["documents"])[0]
    txt = t.call("read_document", {"doc_id": doc_id})
    if track == "appeals":
        # Prior baseline (no oracle exists for real outcomes): majority outcome for the same review type x
        # treatment category among IMR rows NOT used in the suite.
        typ = re.search(r"^Review type: (.+)$", txt, re.M).group(1)
        trt = re.search(r"^Treatment category: (.+?) /", txt, re.M).group(1)
        c = _priors().get(f"{typ}|{trt}", [1, 1])
        det = "upheld" if c[0] > c[1] else "overturned"
        t.call("submit_decision", {"decision": {"determination": det, "rationale": f"Historical prior for {typ} / {trt}: upheld {c[0]} vs overturned {c[1]}."}})
    elif track == "coding":
        codes = re.findall(r"^\| \d+ \| ([A-Z0-9.]+) \|$", txt, re.M)
        inv, nb = [], []
        for c in codes:
            r = json.loads(t.call("icd10_lookup", {"code": c}))
            if not r.get("found"):
                inv.append(c)
            elif not r.get("billable"):
                nb.append(c)
        t.call("submit_decision", {"decision": {"invalid_codes": inv, "non_billable_codes": nb, "rationale": "Checked each code with icd10_lookup."}})
    else:
        # Oracle-ish: searches the wording (logged) then answers from the structured policy data it was rendered from.
        from .coverage_qa import _questions  # noqa: F401  (documented dependency)
        plan = re.search(r"^Plan code: (.+)$", txt, re.M).group(1)
        q = re.search(r"^Question: (.+)$", txt, re.M).group(1)
        t.call("search_policy", {"query": q, "plan_code": plan})
        ans, cl = _oracle_answer(plan, q)
        t.call("submit_decision", {"decision": {"answer": ans, "clause_id": cl, "rationale": "From the policy wording."}})


def _oracle_answer(plan: str, q: str):
    from decimal import Decimal

    from ..claims.engine import money
    pol = P.POLICIES[plan]
    c = lambda x: P.clause_id(plan, x)  # noqa: E731
    ql = q.lower()
    if "room rent per day" in ql:
        return pol["room_limit_per_day"], c("4.1")
    if "deductible" in ql:
        return pol["deductible"], c("5.1")
    if "co-payment" in ql:
        return pol["copay_pct"], c("5.2")
    if "pre-existing" in ql:
        return pol["ped_wait_days"], c("2.3")
    if "is it payable under the waiting" in ql:
        day = int(re.search(r"happens (\d+) days", q).group(1))
        return ("yes" if day >= pol["specific_wait_days"] else "no"), c("2.2")
    if "days in force are required before treatment" in ql:
        return pol["specific_wait_days"], c("2.2")
    if "sublimit" in ql:
        cond = re.search(r"sublimit for (.+)\?", q).group(1).replace(" ", "_")
        return pol["sublimits"].get(cond, 0), c("4.4")
    if "proportionate" in ql:
        rate = int(re.search(r"billed at ([\d,]+) per day", q).group(1).replace(",", ""))
        assoc = int(re.search(r"total ([\d,]+)\.", q).group(1).replace(",", ""))
        lim = pol["room_limit_per_day"]
        return float(money(Decimal(assoc) * (Decimal(1) - Decimal(lim) / Decimal(rate)))), c("4.2")
    if "item category" in ql:
        return "no", c("3.1")
    if "road accident" in ql:
        return "no", c("2.1")
    return pol["sum_insured"], c("5.3")


def baseline_naive(track: str, t: ToolEnv):
    doc_id = list(t.case["documents"])[0]
    t.call("read_document", {"doc_id": doc_id})
    sub = {"appeals": {"determination": "upheld", "rationale": "Plans are usually right."},
           "coding": {"invalid_codes": [], "non_billable_codes": [], "rationale": "All codes look fine."},
           "coverage_qa": {"answer": "yes", "clause_id": "N/A"}}[track]
    t.call("submit_decision", {"decision": sub})
