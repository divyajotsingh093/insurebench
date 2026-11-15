"""Expose a case's ToolEnv as an MCP server (mcp Python SDK v2, MCPServer).

Run over stdio:  python -m insurebench.env.mcp_server --track uw --case UW-001 [--split dev]
Every call is logged to the same Trace format as the in-process harnesses; on exit the trace is
written to results/mcp_traces/<case>.json.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from ..common import Trace
from .tools import ToolEnv, tool_specs


def build_server(env: ToolEnv):
    from mcp.server.mcpserver import MCPServer

    server = MCPServer(name=f"insurebench-{env.track}", instructions=env.case["task"])
    names = {t["name"]: t["description"] for t in tool_specs(env.track)}

    def reg(fn, name):
        if name in names:
            server.add_tool(fn, name=name, description=names[name])

    def list_documents() -> str:
        return env.call("list_documents", {})

    def read_document(doc_id: str) -> str:
        return env.call("read_document", {"doc_id": doc_id})

    def search_manual(query: str, k: int = 3) -> str:
        return env.call("search_manual", {"query": query, "k": k})

    def search_policy(query: str, plan_code: str, k: int = 3) -> str:
        return env.call("search_policy", {"query": query, "plan_code": plan_code, "k": k})

    def debit_calculator(factor: str, height_cm: float | None = None, weight_kg: float | None = None,
                         systolic: float | None = None, diastolic: float | None = None, hba1c: float | None = None,
                         total_cholesterol: float | None = None, hdl: float | None = None) -> str:
        args = {k: v for k, v in dict(factor=factor, height_cm=height_cm, weight_kg=weight_kg, systolic=systolic, diastolic=diastolic,
                                      hba1c=hba1c, total_cholesterol=total_cholesterol, hdl=hdl).items() if v is not None}
        return env.call("debit_calculator", args)

    def calculator(expression: str) -> str:
        return env.call("calculator", {"expression": expression})

    def prior_application_lookup(applicant_id: str) -> str:
        return env.call("prior_application_lookup", {"applicant_id": applicant_id})

    def claims_history_lookup(policy_number: str) -> str:
        return env.call("claims_history_lookup", {"policy_number": policy_number})

    def order_evidence(code: str) -> str:
        return env.call("order_evidence", {"code": code})

    def ask_user(question: str) -> str:
        return env.call("ask_user", {"question": question})

    def refer_to_senior(reason: str) -> str:
        return env.call("refer_to_senior", {"reason": reason})

    def submit_decision(decision: dict[str, Any]) -> str:
        return env.call("submit_decision", {"decision": decision})

    for fn in (list_documents, read_document, search_manual, search_policy, debit_calculator, calculator,
               prior_application_lookup, claims_history_lookup, order_evidence, ask_user, refer_to_senior, submit_decision):
        reg(fn, fn.__name__)
    return server


def main():
    from ..config import DATA_DIR, RESULTS_DIR
    from ..gen.build import load_cases

    ap = argparse.ArgumentParser()
    ap.add_argument("--track", required=True, choices=["uw", "claims"])
    ap.add_argument("--case", required=True)
    ap.add_argument("--split", default="dev")
    a = ap.parse_args()
    case = next(c for c in load_cases(DATA_DIR, a.track, a.split) if c["case_id"] == a.case)
    trace = Trace(case_id=case["case_id"], track=a.track, harness="mcp_external", model="external")
    env = ToolEnv(case, trace)
    server = build_server(env)
    try:
        server.run("stdio")
    finally:
        out = RESULTS_DIR / "mcp_traces"
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{case['case_id']}.json").write_text(json.dumps(trace.to_dict(), indent=1))


if __name__ == "__main__":
    main()
