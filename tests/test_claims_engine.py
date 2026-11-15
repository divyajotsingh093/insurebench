from insurebench.claims import engine as E
from insurebench.claims import policies as P


def claim(**kw):
    f = {"claim_id": "C1", "policy_code": "MM-HOSP-SILVER", "policy_number": "P1", "member_name": "X", "sex": "F", "age": 40,
         "inception": "2024-01-01", "period_start": "2026-01-01", "period_end": "2026-12-31",
         "admission": "2026-05-01", "discharge": "2026-05-03", "claim_form_admission": "2026-05-01", "claim_form_discharge": "2026-05-03",
         "hospital": "H", "diagnosis": {"key": "x", "label": "x", "group": None, "surgical": False, "accident": False},
         "ped": None, "ped_related": False, "prior_claims": [],
         "line_items": [
             {"code": "RM", "description": "room", "category": "room", "qty": 2, "unit_price": 4000.0, "ref": None},
             {"code": "SUR", "description": "surgeon", "category": "surgeon_fee", "qty": 1, "unit_price": 20000.0, "ref": None},
             {"code": "NUR", "description": "nursing", "category": "nursing", "qty": 1, "unit_price": 1000.0, "ref": None},
             {"code": "MED", "description": "meds", "category": "medicines", "qty": 1, "unit_price": 5000.0, "ref": None},
             {"code": "TOIL", "description": "toiletries", "category": "toiletries", "qty": 1, "unit_price": 300.0, "ref": None}],
         "submitted_docs": ["CLAIM_FORM", "DISCHARGE_SUMMARY", "ITEMISED_BILL", "ID_PROOF", "PHARMACY_INVOICES"]}
    f.update(kw)
    return f


def test_hand_worked_payable():
    pol = P.POLICIES["MM-HOSP-SILVER"]
    assert pol["room_limit_per_day"] == 3000 and pol["copay_pct"] == 10
    ded = pol["deductible"]
    # billed 34,300; non-payable 300; room excess (4000-3000)x2 = 2,000; proportionate on associated (20,000+1,000) x (1-3000/4000) = 5,250
    g = E.adjudicate(claim())
    assert g["claimed_amount"] == 34300.0
    by = {d["clause_id"]: d["amount"] for d in g["deductions"]}
    assert by["SLV-3.1"] == 300.0 and by["SLV-4.1"] == 2000.0 and by["SLV-4.2"] == 5250.0
    after = 34300 - 300 - 2000 - 5250 - ded
    assert by["SLV-5.2"] == round(after * 0.10, 2)
    assert g["payable_amount"] == round(after - round(after * 0.10, 2), 2)
    assert g["decision"] == "partial"


def test_initial_waiting_edges_and_accident():
    base = dict(inception="2026-04-01", period_start="2026-04-01", period_end="2027-03-31")
    assert E.adjudicate(claim(**base, admission="2026-04-30"))["reject_clause"] == "SLV-2.1"     # day 29
    assert E.adjudicate(claim(**base, admission="2026-05-01"))["decision"] != "reject"           # day 30
    acc = claim(**base, admission="2026-04-05", diagnosis={"key": "f", "label": "f", "group": None, "surgical": False, "accident": True},
                submitted_docs=["CLAIM_FORM", "DISCHARGE_SUMMARY", "ITEMISED_BILL", "ID_PROOF", "PHARMACY_INVOICES", "POLICE_REPORT"])
    assert E.adjudicate(acc)["decision"] == "partial"


def test_missing_docs_pend_and_duplicate_reject():
    g = E.adjudicate(claim(submitted_docs=["CLAIM_FORM", "DISCHARGE_SUMMARY", "ITEMISED_BILL"]))
    assert g["decision"] == "pend_for_documents" and set(g["missing_documents"]) == {"ID_PROOF", "PHARMACY_INVOICES"}
    dup = claim(prior_claims=[{"claim_id": "C0", "admission": "2026-05-01", "hospital": "H", "billed": 34300.0, "paid": 0.0, "status": "paid"}])
    g = E.adjudicate(dup)
    assert g["decision"] == "reject" and g["reject_clause"] == "SLV-6.2" and "DUPLICATE_CLAIM" in g["fraud_flags"]


def test_sum_insured_cap():
    pc = [{"claim_id": "C0", "admission": "2026-02-01", "hospital": "Z", "billed": 1.0, "paid": 290000.0, "status": "paid"}]
    g = E.adjudicate(claim(prior_claims=pc))
    assert g["payable_amount"] == 10000.0 and "SLV-5.3" in g["cited_clauses"]
