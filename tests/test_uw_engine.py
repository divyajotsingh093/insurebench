from insurebench.uw import engine as E


def facts(**kw):
    f = {"applicant_id": "A-1", "name": "Test Person", "sex": "F", "age": 30, "occupation": "accountant", "income": 100_000,
         "sum_assured": 200_000, "declared": {"height_cm": 170, "weight_kg": 70.0, "smoker_status": "never", "diabetes": False,
                                              "hypertension": False, "family_history_cardiac": False, "conditions": []},
         "quit_months": None, "hobbies": [], "evidence": {}, "mib": []}
    for k, v in kw.items():
        if k in f["declared"]:
            f["declared"][k] = v
        else:
            f[k] = v
    return f


def test_bmi_rounding_and_bands():
    assert E.bmi(170, 70.0) == 24.2
    assert E.bmi_rule(30.0)[1] == 25 and E.bmi_rule(29.9)[1] == 0
    assert E.bmi_rule(45.0)[2] == "decline"


def test_bp_uses_worse_band():
    assert E.bp_rule(138, 96) == ("UW-BP-3", 50, None)   # diastolic band 3 is worse than systolic band 1
    assert E.bp_rule(180, 80)[2] == "postpone"


def test_clean_standard():
    g = E.underwrite(facts())
    assert g["decision"] == "accept_standard" and g["table_class"] == "Standard" and g["total_debits"] == 0
    assert g["required_evidence"] == []          # age 18-40, SA <= 250k -> declaration only
    assert g["offered_sum_assured"] == 200_000 and not g["should_refer"]


def test_hand_worked_debit_total():
    # age 45, SA 400k -> PMR+BLD+URN. PMR BMI 31.1 (+25), BP 145/85 (+25), lipids 6.0/1.0=6.0 (+25), family history (+25) = 100 -> T4
    f = facts(age=45, sum_assured=400_000, family_history_cardiac=True)
    f["evidence"] = {"PMR": {"height_cm": 170, "weight_kg": 90.0, "systolic": 145, "diastolic": 85},
                     "BLD": {"tc": 6.0, "hdl": 1.0, "hba1c": 5.4, "cotinine": "negative"}, "URN": {"normal": True}}
    g = E.underwrite(f)
    assert g["total_debits"] == 100
    assert g["table_class"] == "T4" and g["decision"] == "accept_rated"
    assert g["required_evidence"] == ["BLD", "PMR", "URN"]


def test_decline_beats_postpone_and_hobby_exclusion():
    f = facts(conditions=["surgery scheduled"], weight_kg=140.0)   # BMI 48.4 -> decline; surgery -> postpone
    assert E.underwrite(f)["decision"] == "decline"
    f = facts(hobbies=[{"name": "scuba diving", "value": 45}])
    g = E.underwrite(f)
    assert g["exclusions"] == ["EXC-DIVE"] and "HQ" in g["required_evidence"]


def test_financial_cap_and_referral():
    # age 30 -> 25x income = 2.5M; existing 2.2M -> capacity 300k; requested 500k -> offer 300k
    f = facts(income=100_000, sum_assured=500_000, mib=[{"carrier": "X", "kind": "inforce", "months_ago": 10, "decision": "accepted", "sum_assured": 2_200_000}])
    f["evidence"] = {"BLD": {"tc": 4.0, "hdl": 1.5, "hba1c": 5.0, "cotinine": "negative"}, "URN": {"normal": True}}
    assert E.underwrite(f)["offered_sum_assured"] == 300_000
    f = facts(income=200_000, sum_assured=2_500_000)
    assert E.underwrite(f)["should_refer"]


def test_cotinine_nondisclosure():
    f = facts(sum_assured=400_000)
    f["evidence"] = {"BLD": {"tc": 4.0, "hdl": 1.5, "hba1c": 5.0, "cotinine": "positive"}, "URN": {"normal": True}}
    g = E.underwrite(f)
    assert g["rate_class"] == "smoker" and g["should_refer"] and "UW-ND-1" in g["refer_reasons"]
