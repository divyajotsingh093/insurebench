"""Per-case graders for the UW and claims tracks plus trace-level tool-use metrics."""
from __future__ import annotations

import json

from ..claims.policies import all_clause_ids
from ..config import cost_usd
from ..uw.rules import TABLE_ORDER, all_rule_ids
from .judge import Judge

RULE_IDS = all_rule_ids()
CLAUSE_IDS = all_clause_ids()


def f1(pred, gold) -> float:
    p, g = set(pred or []), set(gold or [])
    if not p and not g:
        return 1.0
    if not p or not g:
        return 0.0
    tp = len(p & g)
    if tp == 0:
        return 0.0
    prec, rec = tp / len(p), tp / len(g)
    return round(2 * prec * rec / (prec + rec), 4)


def tool_metrics(trace: dict, gold_rec: dict) -> dict:
    ev = trace["events"]
    seen, redundant = set(), 0
    for e in ev:
        key = (e["tool"], json.dumps(e["args"], sort_keys=True))
        if key in seen and e["tool"] not in ("submit_decision",):
            redundant += 1
        seen.add(key)
    invalid = sum(1 for e in ev if not e["ok"])
    shortest = len(gold_rec.get("required_actions", [])) + 2  # + list_documents + submit
    # info-gathering coverage
    done = set()
    for e in ev:
        if not e["ok"]:
            continue
        if e["tool"] == "read_document":
            done.add(f"read:{e['args'].get('doc_id')}")
        elif e["tool"] == "order_evidence":
            done.add(f"order:{str(e['args'].get('code', '')).upper()}")
            done.add(f"read:EV-{str(e['args'].get('code', '')).upper()}")
        elif e["tool"] == "prior_application_lookup":
            done.add("lookup:prior_applications")
        elif e["tool"] == "claims_history_lookup":
            done.add("lookup:claims_history")
    for k in trace.get("revealed", []):
        done.add(f"ask:{k}")
    req = gold_rec.get("required_actions", [])
    cov = sum(1 for a in req if a in done) / len(req) if req else 1.0
    return {"steps": len(ev), "invalid_calls": invalid, "redundant_calls": redundant, "shortest_path": shortest,
            "step_ratio": round(len(ev) / shortest, 3) if shortest else None, "info_coverage": round(cov, 4)}


def grade_uw(sub: dict | None, gold_rec: dict, judge: Judge) -> dict:
    g = gold_rec["gold"]
    if not sub:
        return {"submitted": False, "decision_exact": 0, "table_exact": 0, "table_within_one": 0, "evidence_f1": 0.0,
                "exclusions_match": 0, "rate_class_exact": 0, "offered_sa_exact": 0, "refer_correct": 0, "primary_correct": 0,
                "cited": 0, "hallucinated": 0, "rationale_score": 0.0 if judge.spec != "none" else None,
                "pred_decision": None, "pred_refer": None}
    tc, gc = sub.get("table_class"), g["table_class"]
    within = int(tc == gc or (tc in TABLE_ORDER and gc in TABLE_ORDER and abs(TABLE_ORDER.index(tc) - TABLE_ORDER.index(gc)) <= 1))
    cited = sub.get("cited_rules", []) or []
    out = {
        "submitted": True,
        "decision_exact": int(sub.get("decision") == g["decision"]),
        "table_exact": int(tc == gc),
        "table_within_one": within,
        "evidence_f1": f1(sub.get("required_evidence"), g["required_evidence"]),
        "exclusions_match": int(set(sub.get("exclusions") or []) == set(g["exclusions"])),
        "rate_class_exact": int(sub.get("rate_class") == g["rate_class"]),
        "offered_sa_exact": int(abs(float(sub.get("offered_sum_assured") or 0) - g["offered_sum_assured"]) <= 1),
        "refer_correct": int(bool(sub.get("refer")) == g["should_refer"]),
        "cited": len(cited), "hallucinated": sum(1 for c in cited if c not in RULE_IDS),
        "rationale_score": judge.uw(sub.get("rationale", ""), g),
        "pred_decision": sub.get("decision"), "pred_refer": bool(sub.get("refer")),
    }
    out["primary_correct"] = int(out["decision_exact"] and out["table_exact"])
    return out


def _agent_clauses(sub: dict) -> set:
    if sub.get("decision") in ("reject", "pend_for_documents"):
        return {sub["decision_clause"]} if sub.get("decision_clause") else set()
    return {d.get("clause_id") for d in sub.get("deductions", []) if d.get("clause_id")}


def grade_claims(sub: dict | None, gold_rec: dict, judge: Judge) -> dict:
    g = gold_rec["gold"]
    if not sub:
        return {"submitted": False, "admissibility_exact": 0, "payable_within_1pct": 0, "clause_exact": 0, "flag_tp": 0,
                "flag_fp": 0, "flag_fn": len(g["fraud_flags"]), "missing_docs_f1": 0.0, "primary_correct": 0, "cited": 0,
                "hallucinated": 0, "letter_score": 0.0 if judge.spec != "none" else None, "pred_decision": None, "pred_refer": None}
    pay = float(sub.get("payable_amount") or 0)
    gp = g["payable_amount"]
    payable_ok = int(abs(pay - gp) <= max(0.01 * gp, 1.0))
    ac = _agent_clauses(sub)
    pf, gf = set(sub.get("fraud_flags") or []), set(g["fraud_flags"])
    cited = [d.get("clause_id") for d in sub.get("deductions", [])] + ([sub["decision_clause"]] if sub.get("decision_clause") else [])
    out = {
        "submitted": True,
        "admissibility_exact": int(sub.get("decision") == g["decision"]),
        "payable_within_1pct": payable_ok,
        "clause_exact": int(ac == set(g["cited_clauses"])),
        "flag_tp": len(pf & gf), "flag_fp": len(pf - gf), "flag_fn": len(gf - pf),
        "missing_docs_f1": f1(sub.get("missing_documents"), g["missing_documents"]),
        "cited": len(cited), "hallucinated": sum(1 for c in cited if c not in CLAUSE_IDS),
        "letter_score": judge.letter(sub.get("letter", ""), g),
        "pred_decision": sub.get("decision"), "pred_refer": bool(pf),
    }
    out["primary_correct"] = int(out["admissibility_exact"] and payable_ok)
    return out


def grade_trace(case: dict, trace: dict, gold_rec: dict, judge: Judge) -> dict:
    track = case["track"]
    sub = trace.get("submission")
    if track == "uw":
        row = grade_uw(sub, gold_rec, judge)
    elif track == "claims":
        row = grade_claims(sub, gold_rec, judge)
    else:
        from ..suites.qa import grade as qa_grade
        row = qa_grade(track, sub, gold_rec)
    row.update(tool_metrics(trace, gold_rec))
    row.update({"case_id": case["case_id"], "family": case["family"], "variant": case["variant"], "tags": case["tags"],
                "track": track, "harness": trace["harness"], "model": trace["model"], "run_idx": trace["run_idx"],
                "status": trace["status"], "error": trace.get("error"), "tokens_in": trace["tokens_in"], "tokens_out": trace["tokens_out"],
                "latency_s": round(trace["latency_s"], 3), "cost_usd": round(cost_usd(trace["model"], trace["tokens_in"], trace["tokens_out"]), 6),
                "gold_decision": gold_rec["gold"]["decision"],
                "gold_refer": gold_rec["gold"].get("should_refer", gold_rec["gold"].get("siu_referral", False)),
                "agent_referred": trace.get("referred", False)})
    if track == "uw":
        row["pred_refer"] = bool(row.get("pred_refer")) or bool(trace.get("referred"))
    return row
