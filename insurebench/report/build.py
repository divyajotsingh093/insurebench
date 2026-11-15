"""Aggregate run summaries into results/leaderboard.json, the static site/index.html and web/data/leaderboard.json.

Only aggregate summaries and DEV-split sample traces are published. Per-case rows for the test split (which carry
gold decisions) are never copied into the leaderboard or the web bundle.
"""
from __future__ import annotations

import json
import shutil
import time

from .. import CANARY
from ..config import RESULTS_DIR, ROOT, SITE_DIR
from ..suites import SUITES, TRACK_TO_SUITE

METRIC_DEFS = {
    "primary_accuracy": "UW: decision AND table class exact. Claims: admissibility exact AND payable within +/-1%. QA suites: main answer exact.",
    "decision_exact": "Decision label matches gold.", "table_exact": "Table class matches gold.",
    "table_within_one": "Table class within one step of gold.", "evidence_f1": "F1 of required evidence codes.",
    "exclusions_match": "Exclusion set matches exactly.", "rate_class_exact": "Smoker/non-smoker class matches.",
    "offered_sa_exact": "Offered sum assured matches (financial limits).", "refer_correct": "Referral flag matches gold.",
    "info_coverage": "Share of required information-gathering actions taken (documents read, evidence ordered, facts asked, lookups).",
    "rationale_score": "Free-text rationale score (heuristic judge by default; LLM judge optional).",
    "admissibility_exact": "pay/partial/reject/pend matches gold.", "payable_within_1pct": "Payable amount within +/-1% of gold.",
    "clause_exact": "Cited clause set matches gold exactly.", "missing_docs_f1": "F1 of missing document codes.",
    "flag_precision": "Precision of fraud / red flags.", "flag_recall": "Recall of fraud / red flags.",
    "letter_score": "Decision letter score (heuristic or LLM judge).",
    "pass_hat_k": "pass^k: share of cases solved in ALL k repeated runs.", "cost_per_correct_usd": "Total spend / number of primary-correct runs.",
    "hallucination_rate": "Share of cited rule/clause IDs that do not exist.", "invalid_calls_per_case": "Tool calls that errored.",
    "redundant_calls_per_case": "Exact repeated tool calls.", "step_ratio_vs_shortest": "Steps used / shortest reference path.",
    "escalation_precision": "Referral precision (UW: senior referral; claims: SIU via red flags).", "escalation_recall": "Referral recall.",
    "fairness_delta": "Share of name/sex-swapped pairs whose decision changed (lower is better; gold never changes).",
    "robustness_delta": "Accuracy on clean minus accuracy on OCR-noised/shuffled twins (lower is better).",
    "injection_resistance": "Share of prompt-injected cases where the agent did NOT output the injected outcome.",
    "latency_s_mean": "Mean wall-clock seconds per case.", "upheld_recall": "Recall on upheld appeals.",
    "overturned_recall": "Recall on overturned appeals.", "invalid_f1": "F1 on invalid codes.", "non_billable_f1": "F1 on non-billable codes.",
    "all_exact": "Both code lists exactly right.", "answer_exact": "Answer correct (numeric within 1%).",
}


def _sample_traces(runs_dir):
    samples = {}
    for d in sorted(runs_dir.glob("*__dev")):
        track, harness = d.name.split("__")[:2]
        tp = d / "traces.jsonl"
        if not tp.exists():
            continue
        lines = tp.read_text().splitlines()
        if not lines:
            continue
        pref = 0 if harness == "baseline_rules" else 1
        if track in samples and samples[track][0] <= pref:
            continue
        # pick an interesting trace: the one with the most tool calls among the first 10
        tr = max((json.loads(x) for x in lines[:10]), key=lambda t: len(t["events"]))
        tr["messages"] = []
        samples[track] = (pref, tr)
    return {k: v[1] for k, v in samples.items()}


def build_report() -> str:
    runs_dir = RESULTS_DIR / "runs"
    runs = []
    for p in sorted(runs_dir.glob("*/summary.json")):
        s = json.loads(p.read_text())
        s["suite"] = TRACK_TO_SUITE.get(s["track"], s["track"])
        s.pop("budget", None)
        runs.append(s)
    try:
        from ..models.roster import load
        roster = load()
    except Exception:
        roster = {"models": []}
    lb = {"canary": CANARY, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
          "suites": SUITES, "roster": roster, "runs": runs, "metric_defs": METRIC_DEFS,
          "sample_traces": _sample_traces(runs_dir)}
    out = RESULTS_DIR / "leaderboard.json"
    out.write_text(json.dumps(lb, indent=1))
    web_data = ROOT / "web" / "data"
    if web_data.parent.exists():
        web_data.mkdir(exist_ok=True)
        shutil.copy(out, web_data / "leaderboard.json")
        from ..config import DATA_DIR
        ids = {}
        for track in {v["track"] for v in SUITES.values()}:
            p = DATA_DIR / track / "dev.jsonl"
            if p.exists():
                ids[track] = [json.loads(x)["case_id"] for x in p.read_text().splitlines()]
        (web_data / "dev_case_ids.json").write_text(json.dumps(ids))
    SITE_DIR.mkdir(exist_ok=True)
    tpl = (ROOT / "insurebench" / "report" / "site_template.html").read_text()
    (SITE_DIR / "index.html").write_text(tpl.replace("/*__DATA__*/null", json.dumps(lb)))
    return f"wrote {out} ({len(runs)} runs) and {SITE_DIR / 'index.html'}"
