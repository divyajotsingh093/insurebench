import filecmp
import json

from insurebench.common import Trace
from insurebench.env.tools import ToolEnv, safe_eval, validate
from insurebench.gen.build import build, load_cases, load_gold
from insurebench.grade.graders import f1, grade_trace
from insurebench.grade.judge import Judge
from insurebench.harnesses import get_harness


def test_generator_determinism(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    build(a); build(b)
    for rel in ["uw/dev.jsonl", "uw/test.jsonl", "claims/dev.jsonl", "gold/claims_dev.jsonl", "gold_hidden/uw_test.jsonl",
                "manual/uw_manual.md", "coverage_qa/dev.jsonl"]:
        assert filecmp.cmp(a / rel, b / rel, shallow=False), rel
    rows = [json.loads(x) for x in open(a / "uw" / "dev.jsonl")]
    assert all("canary" in r for r in rows)
    assert all("facts" not in r for r in rows)          # gold-bearing facts never in public case files


def _run(harness, track, split="dev", tmp=None):
    cases, gold = load_cases("data", track, split), load_gold("data", track, split)
    h, rows = get_harness(harness), []
    for c in cases:
        t = Trace(c["case_id"], track, harness, "none")
        env = ToolEnv(c, t)
        h.run(c, env, "none", env.budget)
        td = t.to_dict(); td["revealed"] = sorted(env.user.revealed)
        rows.append(grade_trace(c, td, gold[c["case_id"]], Judge("heuristic")))
    return sum(r["primary_correct"] for r in rows) / len(rows), rows


def test_graders_discriminate():
    for track in ("uw", "claims", "coverage_qa", "coding"):
        good, rows = _run("baseline_rules", track)
        bad, _ = _run("baseline_naive", track)
        assert good >= 0.99, track
        assert bad < good - 0.3, track
    _, rows = _run("baseline_rules", "uw")
    assert all(r["hallucinated"] == 0 for r in rows)
    assert all(r["info_coverage"] == 1.0 for r in rows)


def test_metric_helpers():
    assert f1([], []) == 1.0 and f1(["A"], []) == 0.0 and f1(["A", "B"], ["B", "C"]) == 0.5
    assert safe_eval("(4000-3000)*2") == 2000
    assert validate({"decision": "pay"}, {"type": "object", "required": ["decision", "x"]})


def test_llm_harness_skips_without_key(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(k, raising=False)
    c = load_cases("data", "uw", "dev")[0]
    for name in ("react_raw", "langgraph_react", "openai_agents_sdk", "claude_agent_sdk"):
        t = Trace(c["case_id"], "uw", name, "anthropic/claude-sonnet-5.5")
        env = ToolEnv(c, t)
        get_harness(name).run(c, env, "anthropic/claude-sonnet-5.5", env.budget)
        assert t.status == "skipped", name


def test_mcp_server_exposes_tools():
    import asyncio

    from insurebench.env.mcp_server import build_server
    c = load_cases("data", "claims", "dev")[0]
    t = Trace(c["case_id"], "claims", "mcp", "x")
    s = build_server(ToolEnv(c, t))
    names = {x.name for x in asyncio.run(s.list_tools())}
    assert {"search_policy", "claims_history_lookup", "submit_decision"} <= names
    asyncio.run(s.call_tool("list_documents", {}))
    assert t.events and t.events[0].tool == "list_documents"


def test_roster():
    from insurebench.models import roster
    assert roster.validate() == []
