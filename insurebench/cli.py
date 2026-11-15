"""InsureBench command line.

  python -m insurebench build-data
  python -m insurebench run --suite uw_synthetic|claims_synthetic|appeals_real|coding_validity|coverage_qa|all
                            --harness baseline_rules --model none --split dev --k 1 [--max-usd 5]
  python -m insurebench sweep --suites all --models roster[:N] --harnesses react_raw --split dev --k 1 --max-usd 10
  python -m insurebench estimate --suites all --models roster --harnesses react_raw,langgraph_react --split dev --k 3
  python -m insurebench roster refresh|validate|show
  python -m insurebench report
  python -m insurebench mcp --track uw --case UW-001
"""
from __future__ import annotations

import argparse
import json
import sys

from .config import TOKEN_ESTIMATES, available_providers, price_for
from .suites import ALL_TRACKS, SUITES, resolve


def _tracks(spec: str) -> list[str]:
    spec = spec.replace("track:", "")
    if spec == "all":
        return list(ALL_TRACKS)
    return [resolve(s.strip()) for s in spec.split(",") if s.strip()]


def _models(spec: str) -> list[str]:
    if spec.startswith("roster"):
        from .models.roster import load
        ms = [m["id"] for m in load()["models"]]
        if ":" in spec:
            ms = ms[: int(spec.split(":")[1])]
        return ms
    return [m.strip() for m in spec.split(",") if m.strip()]


def _count_cases(track: str, split: str) -> int:
    from .config import DATA_DIR
    p = DATA_DIR / track / f"{split}.jsonl"
    return sum(1 for _ in open(p)) if p.exists() else 0


def cmd_estimate(a) -> float:
    tracks, models, harnesses = _tracks(a.suites), _models(a.models), a.harnesses.split(",")
    total, rows = 0.0, []
    for m in models:
        pi, po = price_for(m)
        mc = 0.0
        for t in tracks:
            n = _count_cases(t, a.split)
            ti, to = TOKEN_ESTIMATES[t]
            mc += n * a.k * len(harnesses) * (ti * pi + to * po) / 1e6
        rows.append((m, pi, po, mc)); total += mc
    rows.sort(key=lambda r: -r[3])
    print(f"Projected sweep cost: {len(models)} models x {len(harnesses)} harnesses x {', '.join(f'{t}({_count_cases(t, a.split)})' for t in tracks)} cases x k={a.k}")
    print(f"{'model':45s} {'$/1M in':>8s} {'$/1M out':>9s} {'projected $':>12s}")
    for m, pi, po, c in rows:
        print(f"{m:45s} {pi:8.3f} {po:9.3f} {c:12.2f}")
    print(f"{'TOTAL':45s} {'':8s} {'':9s} {total:12.2f}")
    print("Token assumptions per case (in, out):", {t: TOKEN_ESTIMATES[t] for t in tracks})
    return total


def main(argv=None):
    ap = argparse.ArgumentParser(prog="insurebench")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("build-data")

    def add_run_args(p, multi=False):
        if multi:
            p.add_argument("--suites", default="all")
            p.add_argument("--models", default="roster:3")
            p.add_argument("--harnesses", default="react_raw")
        else:
            p.add_argument("--suite", "--track", dest="suite", default="all",
                           help="suite or track name (uw|claims|appeals|coding|coverage_qa) or 'all'")
            p.add_argument("--harness", required=True)
            p.add_argument("--model", default="none")
        p.add_argument("--split", default="dev")
        p.add_argument("--k", type=int, default=1)
        p.add_argument("--judge", default="heuristic", help="heuristic | none | llm:<model>")
        p.add_argument("--limit", type=int, default=None)
        p.add_argument("--max-usd", type=float, default=None, help="hard spend cap (whole command)")
        p.add_argument("--max-steps", type=int, default=None)
        p.add_argument("--user", default="rule", choices=["rule", "llm"])

    add_run_args(sub.add_parser("run"))
    add_run_args(sub.add_parser("sweep"), multi=True)
    e = sub.add_parser("estimate")
    e.add_argument("--suites", default="all"); e.add_argument("--models", default="roster")
    e.add_argument("--harnesses", default="react_raw,langgraph_react,openai_agents_sdk"); e.add_argument("--split", default="dev")
    e.add_argument("--k", type=int, default=3)
    r = sub.add_parser("roster"); r.add_argument("action", choices=["refresh", "validate", "show"])
    sub.add_parser("report")
    m = sub.add_parser("mcp"); m.add_argument("--track", required=True); m.add_argument("--case", required=True); m.add_argument("--split", default="dev")
    a = ap.parse_args(argv)

    if a.cmd == "build-data":
        from .config import DATA_DIR
        from .gen.build import build
        print(json.dumps(build(DATA_DIR), indent=1))
        print("appeals_real and coding_validity are built by scripts/fetch_imr.py and scripts/fetch_icd10cm.py")
    elif a.cmd in ("run", "sweep"):
        from .runner import run
        budget = {"max_steps": a.max_steps} if a.max_steps else None
        tracks = _tracks(a.suite if a.cmd == "run" else a.suites)
        models = [a.model] if a.cmd == "run" else _models(a.models)
        harnesses = [a.harness] if a.cmd == "run" else a.harnesses.split(",")
        spent = 0.0
        print("providers with keys:", {k: v for k, v in available_providers().items()} | {"openrouter": bool(__import__("os").environ.get("OPENROUTER_API_KEY"))})
        for mdl in models:
            for h in harnesses:
                for t in tracks:
                    remaining = None if a.max_usd is None else max(0.0, a.max_usd - spent)
                    if remaining is not None and remaining <= 0:
                        print(f"--max-usd {a.max_usd} reached; stopping."); return
                    s = run(t, h, mdl, a.split, a.k, a.judge, budget, a.limit, remaining, a.user)
                    spent += s.get("spent_usd", 0.0)
        print(f"total spent: ${spent:.4f}")
    elif a.cmd == "estimate":
        cmd_estimate(a)
    elif a.cmd == "roster":
        from .models import roster
        if a.action == "refresh":
            r = roster.refresh(); print(f"wrote {roster.ROSTER_PATH}: {r['n_models']} models ({r['n_open']} open-weight); rejected: {r['rejected']}")
        errs = roster.validate()
        if a.action in ("validate", "refresh"):
            print("roster OK" if not errs else "\n".join(errs))
            if errs:
                sys.exit(1)
        if a.action == "show":
            for mm in roster.load()["models"]:
                print(f"{mm['id']:42s} {'open' if mm['open_weights'] else 'closed':6s} ctx={mm['context_length']:>8} in=${mm['usd_per_1m_input']}/M out=${mm['usd_per_1m_output']}/M")
    elif a.cmd == "report":
        from .report.build import build_report
        print(build_report())
    elif a.cmd == "mcp":
        sys.argv = ["mcp", "--track", a.track, "--case", a.case, "--split", a.split]
        from .env.mcp_server import main as mcp_main
        mcp_main()


if __name__ == "__main__":
    main()
