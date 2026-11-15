"""Deterministic claims adjudication engine. Computes the gold answer for a hospitalisation claim.

Facts schema (produced by insurebench.gen.claims_gen):
{
  "claim_id", "policy_code", "policy_number", "member_name", "sex", "age",
  "inception",                                       # first inception (continuous cover; waiting periods count from here)
  "period_start", "period_end",                       # current policy year
  "admission", "discharge",                           # hospital (authoritative) dates
  "claim_form_admission", "claim_form_discharge",     # as written by the claimant
  "hospital", "diagnosis": {"key", "label", "group", "surgical", "accident"},
  "ped": {"condition", "diagnosed"} | None, "ped_related": bool,
  "line_items": [{"code", "description", "category", "qty", "unit_price", "ref"}],
  "submitted_docs": [doc codes],
  "prior_claims": [{"claim_id", "admission", "hospital", "billed", "paid", "status"}],
}
"""
from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from . import policies as P

TWO = Decimal("0.01")


def money(x) -> Decimal:
    return Decimal(str(x)).quantize(TWO, rounding=ROUND_HALF_UP)


def d(s: str) -> date:
    return date.fromisoformat(s)


def billed_total(facts: dict) -> Decimal:
    return money(sum(money(li["unit_price"]) * li["qty"] for li in facts["line_items"]))


def required_docs(facts: dict) -> list[str]:
    req = list(P.REQUIRED_DOCS_BASE)
    dx = facts["diagnosis"]
    cats = {li["category"] for li in facts["line_items"]}
    if dx.get("surgical"):
        req.append("OPERATION_NOTES")
    if dx.get("accident"):
        req.append("POLICE_REPORT")
    if "investigations" in cats:
        req.append("INVESTIGATION_REPORTS")
    if "medicines" in cats:
        req.append("PHARMACY_INVOICES")
    return req


def paid_this_year(facts: dict) -> Decimal:
    inc, exp = d(facts["period_start"]), d(facts["period_end"])
    return money(sum(Decimal(str(c["paid"])) for c in facts.get("prior_claims", [])
                     if c["status"] == "paid" and inc <= d(c["admission"]) <= exp))


def detect_flags(facts: dict) -> list[str]:
    flags = []
    inc, exp = d(facts["period_start"]), d(facts["period_end"])
    adm = d(facts["admission"])
    for li in facts["line_items"]:
        ref = li.get("ref")
        if ref and ref in P.REFERENCE_CHARGES and li["unit_price"] > P.INFLATION_FACTOR * P.REFERENCE_CHARGES[ref]:
            flags.append("INFLATED_ITEM")
            break
    if adm < inc or adm > exp:
        flags.append("OUTSIDE_POLICY_PERIOD")
    total = billed_total(facts)
    for c in facts.get("prior_claims", []):
        if c["admission"] == facts["admission"] and c["hospital"] == facts["hospital"] and money(c["billed"]) == total:
            flags.append("DUPLICATE_CLAIM")
            break
    if facts.get("claim_form_admission", facts["admission"]) != facts["admission"] or \
       facts.get("claim_form_discharge", facts["discharge"]) != facts["discharge"]:
        flags.append("DATE_MISMATCH")
    return flags


def adjudicate(facts: dict) -> dict[str, Any]:
    pol = P.POLICIES[facts["policy_code"]]
    cid = lambda n: P.clause_id(facts["policy_code"], n)  # noqa: E731
    claimed = billed_total(facts)
    flags = detect_flags(facts)
    req = required_docs(facts)
    missing = [x for x in req if x not in facts["submitted_docs"]]
    dx = facts["diagnosis"]
    adm, inc = d(facts["admission"]), d(facts["inception"])
    days_in_force = (adm - inc).days

    def result(decision, payable=Decimal("0"), deductions=(), reject_clause=None, steps=None):
        deds = [{"clause_id": x[0], "amount": float(x[1]), "reason": x[2]} for x in deductions]
        if decision == "reject":
            cited = [reject_clause]
        elif decision == "pend_for_documents":
            cited = [cid("6.1")]
        else:
            cited = sorted({x["clause_id"] for x in deds})
        return {
            "decision": decision,
            "payable_amount": float(payable),
            "claimed_amount": float(claimed),
            "deductions": deds,
            "cited_clauses": cited,
            "reject_clause": reject_clause,
            "missing_documents": missing,
            "required_documents": req,
            "fraud_flags": sorted(flags),
            "siu_referral": bool(flags),
            "days_in_force": days_in_force,
            "steps": steps or {},
        }

    # 1) Policy period and duplicates
    if "OUTSIDE_POLICY_PERIOD" in flags:
        return result("reject", reject_clause=cid("1.1"))
    if "DUPLICATE_CLAIM" in flags:
        return result("reject", reject_clause=cid("6.2"))
    # 2) Waiting periods (accidents are exempt from all waiting periods)
    if not dx.get("accident"):
        if days_in_force < pol["initial_wait_days"]:
            return result("reject", reject_clause=cid("2.1"))
        if dx.get("group") in P.SPECIFIC_WAIT_CONDITIONS and days_in_force < pol["specific_wait_days"]:
            return result("reject", reject_clause=cid("2.2"))
        ped = facts.get("ped")
        if facts.get("ped_related") and ped and d(ped["diagnosed"]) < inc and days_in_force < pol["ped_wait_days"]:
            return result("reject", reject_clause=cid("2.3"))
    # 3) Documents
    if missing:
        return result("pend_for_documents")

    # 4) Amount calculation (order fixed by clause 6.3)
    deductions: list[tuple[str, Decimal, str]] = []
    items = facts["line_items"]
    np_amt = money(sum(money(li["unit_price"]) * li["qty"] for li in items if li["category"] in P.NON_PAYABLE))
    if np_amt > 0:
        deductions.append((cid("3.1"), np_amt, "Non-payable items (Annex A)"))

    room_excess = prop = icu_excess = Decimal("0")
    for li in items:
        if li["category"] == "room" and li["unit_price"] > pol["room_limit_per_day"]:
            rate, limit = Decimal(str(li["unit_price"])), Decimal(str(pol["room_limit_per_day"]))
            room_excess += money((rate - limit) * li["qty"])
            assoc = sum(money(x["unit_price"]) * x["qty"] for x in items if x["category"] in P.ASSOCIATED_CATEGORIES)
            prop += money(Decimal(assoc) * (Decimal(1) - limit / rate))
        if li["category"] == "icu" and li["unit_price"] > pol["icu_limit_per_day"]:
            rate, limit = Decimal(str(li["unit_price"])), Decimal(str(pol["icu_limit_per_day"]))
            icu_excess += money((rate - limit) * li["qty"])
    if room_excess > 0:
        deductions.append((cid("4.1"), room_excess, "Room rent above eligible limit"))
    if prop > 0:
        deductions.append((cid("4.2"), prop, "Proportionate deduction on associated expenses"))
    if icu_excess > 0:
        deductions.append((cid("4.3"), icu_excess, "ICU charges above eligible limit"))

    admissible = claimed - np_amt - room_excess - prop - icu_excess
    steps = {"after_room_and_np": float(admissible)}
    sub = pol["sublimits"].get(dx.get("group") or "")
    if sub is not None and admissible > sub:
        amt = money(admissible - Decimal(sub))
        deductions.append((cid("4.4"), amt, f"Disease sublimit {sub}"))
        admissible -= amt
    steps["after_sublimit"] = float(admissible)
    ded = min(Decimal(pol["deductible"]), admissible)
    if ded > 0:
        deductions.append((cid("5.1"), money(ded), "Deductible"))
        admissible -= ded
    steps["after_deductible"] = float(admissible)
    if pol["copay_pct"] and admissible > 0:
        cp = money(admissible * Decimal(pol["copay_pct"]) / Decimal(100))
        deductions.append((cid("5.2"), cp, f"Co-payment {pol['copay_pct']}%"))
        admissible -= cp
    steps["after_copay"] = float(admissible)
    remaining_si = Decimal(pol["sum_insured"]) - paid_this_year(facts)
    if remaining_si < 0:
        remaining_si = Decimal(0)
    if admissible > remaining_si:
        amt = money(admissible - remaining_si)
        deductions.append((cid("5.3"), amt, "Sum insured exhausted"))
        admissible -= amt
    payable = money(admissible)
    steps["remaining_sum_insured_before"] = float(remaining_si)

    if payable <= 0:
        zero_clause = deductions[-1][0] if deductions else cid("5.1")
        return result("reject", Decimal("0"), deductions, reject_clause=zero_clause, steps=steps)
    decision = "pay" if payable == claimed else "partial"
    return result(decision, payable, deductions, steps=steps)
