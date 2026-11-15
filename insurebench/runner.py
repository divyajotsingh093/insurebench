"""Run a harness x model over a suite split, grade, and write results."""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from .common import Trace
from .config import DATA_DIR, DEFAULT_BUDGET, RESULTS_DIR, cost_usd
from .env.tools import ToolEnv
from .gen.build import load_cases, load_gold
from .grade.graders import grade_trace
from .grade.judge import Judge
from .grade.metrics import summarize
from .harnesses import get_harness


def slug(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", s)


def run_dir(track, harness, model, split) -> Path:
    return RESULTS_DIR / "runs" / f"{track}__{harness}__{slug(model)}__{split}"


def run(track: str, harness_name: str, model: str, split: str = "dev", k: int = 1, judge: str = "heuristic",
        budget: dict | None = None, limit: int | None = None, max_usd: float | None = None, user_kind: str = "rule",
        verbose: bool = True) -> dict:
    harness = get_harness(harness_name)
    model = model if harness.needs_model else "none"
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    cases = load_cases(DATA_DIR, track, split)
    if limit:
        cases = cases[:limit]
    gold = load_gold(DATA_DIR, track, split)
    j = Judge(judge)
    out = run_dir(track, harness_name, model, split)
    out.mkdir(parents=True, exist_ok=True)
    rows, traces, spent = [], [], 0.0
    stopped = None
    for rep in range(k):
        for case in cases:
            if max_usd is not None and spent >= max_usd:
                stopped = f"max_usd {max_usd} reached after ${spent:.4f}"
                break
            trace = Trace(case_id=case["case_id"], track=track, harness=harness_name, model=model, run_idx=rep)
            env = ToolEnv(case, trace, budget, user_kind=user_kind)
            t0 = time.time()
            try:
                harness.run(case, env, model, budget)
            except Exception as e:  # harness bug: record, keep going
                trace.status, trace.error = "error", f"{type(e).__name__}: {e}"[:500]
            trace.latency_s = time.time() - t0
            if trace.submission is None and trace.status == "ok":
                trace.status = "no_submission"
            td = trace.to_dict()
            td["revealed"] = sorted(env.user.revealed)
            traces.append(td)
            spent += cost_usd(model, trace.tokens_in, trace.tokens_out)
            if case["case_id"] in gold:
                rows.append(grade_trace(case, td, gold[case["case_id"]], j))
        if stopped:
            break
    with open(out / "traces.jsonl", "w") as f:
        for t in traces:
            f.write(json.dumps(t) + "\n")
    with open(out / "results.jsonl", "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    summary = summarize(rows) if rows else {"track": track, "harness": harness_name, "model": model, "n_cases": len(cases),
                                            "note": "no gold available for this split; traces written for submission"}
    summary.update({"split": split, "judge": judge, "budget": budget, "stopped": stopped, "spent_usd": round(spent, 4),
                    "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
    (out / "summary.json").write_text(json.dumps(summary, indent=1))
    if verbose:
        keys = [x for x in ("primary_accuracy", "decision_exact", "admissibility_exact", "payable_within_1pct", "pass_hat_k",
                            "injection_resistance", "fairness_delta", "robustness_delta") if summary.get(x) is not None]
        msg = "SKIPPED: " + str(summary.get("skip_reason")) if summary.get("skipped") else " ".join(f"{x}={summary[x]}" for x in keys)
        print(f"[{track}/{split}] {harness_name} x {model}: {msg}")
    return summary
