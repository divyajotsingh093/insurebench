"""The InsureBench tool layer. One ToolEnv per (case, run). Every call is logged to a Trace.

The same tool specs are exposed as (a) plain Python via ToolEnv.call, (b) provider tool schemas
(OpenAI / Anthropic formats) and (c) an MCP server (insurebench.env.mcp_server).
"""
from __future__ import annotations

import ast
import json
import operator
import time
from typing import Any

from ..claims import policies as CP
from ..claims.wording import sections as policy_sections
from ..common import ToolEvent, Trace
from ..config import DEFAULT_BUDGET
from ..gen.uw_gen import normal_stub
from ..uw import engine as UE
from ..uw import rules as UR
from ..uw.manual import sections as manual_sections
from .search import BM25
from .user_sim import make_user

UW_DECISIONS = ["accept_standard", "accept_rated", "postpone", "decline"]
UW_CLASSES = ["Standard", "T2", "T4", "T6", "T8", "Postpone", "Decline"]
CL_DECISIONS = ["pay", "partial", "reject", "pend_for_documents"]

SUBMIT_SCHEMAS = {
    "uw": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": UW_DECISIONS},
            "table_class": {"type": "string", "enum": UW_CLASSES},
            "total_debits": {"type": "integer"},
            "rate_class": {"type": "string", "enum": ["smoker", "non_smoker"]},
            "required_evidence": {"type": "array", "items": {"type": "string", "enum": list(UR.EVIDENCE_CODES)}},
            "exclusions": {"type": "array", "items": {"type": "string"}},
            "offered_sum_assured": {"type": "number"},
            "refer": {"type": "boolean"},
            "cited_rules": {"type": "array", "items": {"type": "string"}},
            "rationale": {"type": "string"},
        },
        "required": ["decision", "table_class", "rate_class", "required_evidence", "exclusions",
                     "offered_sum_assured", "refer", "cited_rules", "rationale"],
    },
    "claims": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": CL_DECISIONS},
            "payable_amount": {"type": "number"},
            "deductions": {"type": "array", "items": {"type": "object", "properties": {
                "clause_id": {"type": "string"}, "amount": {"type": "number"}, "reason": {"type": "string"}},
                "required": ["clause_id", "amount"]}},
            "decision_clause": {"type": ["string", "null"]},
            "missing_documents": {"type": "array", "items": {"type": "string"}},
            "fraud_flags": {"type": "array", "items": {"type": "string", "enum": list(CP.FRAUD_FLAGS)}},
            "letter": {"type": "string"},
        },
        "required": ["decision", "payable_amount", "deductions", "missing_documents", "fraud_flags", "letter"],
    },
}

SUBMIT_SCHEMAS["appeals"] = {"type": "object", "properties": {
    "determination": {"type": "string", "enum": ["upheld", "overturned"]}, "rationale": {"type": "string"}},
    "required": ["determination", "rationale"]}
SUBMIT_SCHEMAS["coding"] = {"type": "object", "properties": {
    "invalid_codes": {"type": "array", "items": {"type": "string"}}, "non_billable_codes": {"type": "array", "items": {"type": "string"}},
    "rationale": {"type": "string"}}, "required": ["invalid_codes", "non_billable_codes"]}
SUBMIT_SCHEMAS["coverage_qa"] = {"type": "object", "properties": {
    "answer": {"type": ["string", "number"]}, "clause_id": {"type": "string"}, "rationale": {"type": "string"}},
    "required": ["answer", "clause_id"]}

SUBMIT_DESC = {
    "appeals": "Submit determination: 'upheld' (the plan's denial stands) or 'overturned' (the denial is reversed), with a short rationale.",
    "coding": "Submit invalid_codes (not in ICD-10-CM FY2026) and non_billable_codes (category headers), exactly as written on the claim.",
    "coverage_qa": "Submit the answer (number or 'yes'/'no') and the supporting clause_id (e.g. SLV-4.1).",
    "uw": ("Submit the final underwriting decision (call exactly once, last). decision: accept_standard|accept_rated|postpone|decline. "
           "table_class: Standard|T2|T4|T6|T8|Postpone|Decline. required_evidence: ALL evidence codes required for this case per the "
           "manual (grid + triggers). exclusions: exclusion codes (EXC-*). offered_sum_assured: amount offered after financial limits "
           "(0 if not accepted). refer: true if a referral rule applies. cited_rules: manual rule IDs relied on. rationale: short explanation."),
    "claims": ("Submit the final claim adjudication (call exactly once, last). decision: pay|partial|reject|pend_for_documents. "
               "payable_amount: amount payable (0 for reject/pend). deductions: each deduction with the policy clause_id (e.g. SLV-4.1) and amount. "
               "decision_clause: clause ID supporting a reject or pend decision (null otherwise). missing_documents: required document codes "
               "not submitted. fraud_flags: red flags found. letter: short decision letter to the claimant."),
}


ALL = ("uw", "claims", "appeals", "coding", "coverage_qa")


def _tool(name, desc, props=None, required=None, tracks=("uw", "claims")):
    return {"name": name, "description": desc, "tracks": tracks,
            "parameters": {"type": "object", "properties": props or {}, "required": required or []}}


TOOL_SPECS = [
    _tool("list_documents", "List the documents currently on file for this case (doc_id and title).", tracks=ALL),
    _tool("read_document", "Read the full text of a document by doc_id.", {"doc_id": {"type": "string"}}, ["doc_id"], ALL),
    _tool("icd10_lookup", "Look up an ICD-10-CM FY2026 code (with or without the dot). Returns description and whether it is billable, or not found.",
          {"code": {"type": "string"}}, ["code"], ("coding",)),
    _tool("search_manual", "Keyword (BM25) search over the Meridian Mutual underwriting manual. Returns the top matching sections in full.",
          {"query": {"type": "string"}, "k": {"type": "integer"}}, ["query"], ("uw",)),
    _tool("search_policy", "Keyword (BM25) search over the policy wording of a plan (plan_code from the schedule, e.g. MM-HOSP-SILVER). Returns matching clauses in full.",
          {"query": {"type": "string"}, "plan_code": {"type": "string"}, "k": {"type": "integer"}}, ["query", "plan_code"], ("claims", "coverage_qa")),
    _tool("debit_calculator", "Compute the manual rating for one factor. factor=bmi (height_cm, weight_kg) | blood_pressure (systolic, diastolic) | hba1c (hba1c) | lipids (total_cholesterol, hdl). Returns value, rule id, debits and any knock-out outcome.",
          {"factor": {"type": "string", "enum": ["bmi", "blood_pressure", "hba1c", "lipids"]}, "height_cm": {"type": "number"},
           "weight_kg": {"type": "number"}, "systolic": {"type": "number"}, "diastolic": {"type": "number"}, "hba1c": {"type": "number"},
           "total_cholesterol": {"type": "number"}, "hdl": {"type": "number"}}, ["factor"], ("uw",)),
    _tool("calculator", "Evaluate an arithmetic expression (+ - * / parentheses, min, max, round).", {"expression": {"type": "string"}}, ["expression"],
          ("uw", "claims", "coverage_qa")),
    _tool("prior_application_lookup", "MIB-style lookup of prior applications and in-force cover at other carriers, by applicant_id.",
          {"applicant_id": {"type": "string"}}, ["applicant_id"], ("uw",)),
    _tool("claims_history_lookup", "Look up previous claims on a policy (dates, hospital, billed, paid, status), by policy_number.",
          {"policy_number": {"type": "string"}}, ["policy_number"], ("claims",)),
    _tool("order_evidence", "Order an underwriting evidence requirement by code (BLD, URN, PMR, ECG, TECG, APS, FIN, INSP, HQ, OQ). Returns the result document.",
          {"code": {"type": "string"}}, ["code"], ("uw",)),
    _tool("ask_user", "Ask the case owner (a junior colleague who spoke to the customer) a question. They only know some extra facts and only answer what is asked.",
          {"question": {"type": "string"}}, ["question"]),
    _tool("refer_to_senior", "Refer the case to a senior colleague (log a referral with a reason). You must still submit your recommended decision.",
          {"reason": {"type": "string"}}, ["reason"]),
]


def tool_specs(track: str) -> list[dict]:
    specs = [t for t in TOOL_SPECS if track in t["tracks"]]
    specs.append(_tool("submit_decision", SUBMIT_DESC[track], {"decision": SUBMIT_SCHEMAS[track]}, ["decision"], (track,)))
    return specs


def openai_tools(track: str) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"], "parameters": t["parameters"]}}
            for t in tool_specs(track)]


def anthropic_tools(track: str) -> list[dict]:
    return [{"name": t["name"], "description": t["description"], "input_schema": t["parameters"]} for t in tool_specs(track)]


# ---------------------------------------------------------------------------------------------
def validate(obj: Any, schema: dict, path: str = "$") -> list[str]:
    errs: list[str] = []
    t = schema.get("type")
    types = t if isinstance(t, list) else [t] if t else []
    pymap = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}
    if types:
        ok = False
        for ty in types:
            if ty in ("number", "integer"):
                if isinstance(obj, (int, float)) and not isinstance(obj, bool) and (ty == "number" or float(obj).is_integer()):
                    ok = True
            elif isinstance(obj, pymap[ty]):
                ok = True
        if not ok:
            return [f"{path}: expected {types}, got {type(obj).__name__}"]
    if "enum" in schema and obj not in schema["enum"]:
        errs.append(f"{path}: {obj!r} not in {schema['enum']}")
    if isinstance(obj, dict):
        for r in schema.get("required", []):
            if r not in obj:
                errs.append(f"{path}: missing required field '{r}'")
        for k, sub in schema.get("properties", {}).items():
            if k in obj:
                errs += validate(obj[k], sub, f"{path}.{k}")
    if isinstance(obj, list) and "items" in schema:
        for i, x in enumerate(obj):
            errs += validate(x, schema["items"], f"{path}[{i}]")
    return errs


_OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
        ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Pow: operator.pow}
_FUNCS = {"min": min, "max": max, "round": round, "abs": abs}


def safe_eval(expr: str) -> float:
    def ev(n):
        if isinstance(n, ast.Expression):
            return ev(n.body)
        if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
            return n.value
        if isinstance(n, ast.BinOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.left), ev(n.right))
        if isinstance(n, ast.UnaryOp) and type(n.op) in _OPS:
            return _OPS[type(n.op)](ev(n.operand))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id in _FUNCS:
            return _FUNCS[n.func.id](*[ev(a) for a in n.args])
        raise ValueError("unsupported expression")
    return ev(ast.parse(expr.replace(",", "") if "(" not in expr else expr, mode="eval"))


_MANUAL_INDEX: BM25 | None = None
_POLICY_INDEX: dict[str, BM25] = {}


def manual_index() -> BM25:
    global _MANUAL_INDEX
    if _MANUAL_INDEX is None:
        _MANUAL_INDEX = BM25(manual_sections())
    return _MANUAL_INDEX


def policy_index(code: str) -> BM25:
    if code not in _POLICY_INDEX:
        _POLICY_INDEX[code] = BM25(policy_sections(code))
    return _POLICY_INDEX[code]


class BudgetExceeded(Exception):
    pass


class ToolEnv:
    def __init__(self, case: dict, trace: Trace, budget: dict | None = None, user_kind: str = "rule"):
        self.case = case
        self.track = case["track"]
        self.trace = trace
        self.budget = {**DEFAULT_BUDGET, **(budget or {})}
        self.user = make_user(case, user_kind)
        self.docs = {k: dict(v) for k, v in case["documents"].items()}
        self.visible = [k for k, v in self.docs.items() if v["visible"]]
        self.ordered: list[str] = []
        self.step = 0
        self.done = False
        self.specs = {t["name"]: t for t in tool_specs(self.track)}

    # -------------------------------------------------------------------------------------------
    def call(self, name: str, args: dict | None = None) -> str:
        """Dispatch a tool call; always returns a string (JSON or text). Logs the call."""
        args = args or {}
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except Exception:
                args = {"_raw": args}
        self.step += 1
        if self.step > self.budget["max_steps"]:
            self.trace.status = "budget_exceeded"
            self._log(name, args, False, None, "step budget exceeded")
            raise BudgetExceeded()
        if self.done:
            return self._log(name, args, False, None, "decision already submitted; no further calls allowed")
        spec = self.specs.get(name)
        if spec is None:
            return self._log(name, args, False, None, f"unknown tool '{name}' for track {self.track}")
        errs = validate(args, spec["parameters"])
        if errs and name != "submit_decision":
            return self._log(name, args, False, None, "; ".join(errs))
        try:
            res = getattr(self, f"_t_{name}")(**args)
        except ToolError as e:
            return self._log(name, args, False, None, str(e))
        except TypeError as e:
            return self._log(name, args, False, None, f"bad arguments: {e}")
        return self._log(name, args, True, res, None)

    def _log(self, name, args, ok, result, error):
        out = result if isinstance(result, str) else json.dumps(result)
        self.trace.events.append(ToolEvent(step=self.step, tool=name, args=args, ok=ok, result=out if ok else None, error=error, t=time.time()))
        return out if ok else json.dumps({"error": error})

    # ---- tools --------------------------------------------------------------------------------
    def _t_list_documents(self):
        return [{"doc_id": k, "title": self.docs[k]["title"]} for k in self.visible]

    def _t_read_document(self, doc_id):
        if doc_id not in self.visible:
            raise ToolError(f"no document '{doc_id}' on file. Use list_documents.")
        return self.docs[doc_id]["text"]

    def _t_search_manual(self, query, k=3):
        hits = manual_index().search(query, max(1, min(int(k), 5)))
        return "\n\n".join(f"## [{sid}] {title}\n{body}" for _, (sid, title, body) in hits) or "No matching sections."

    def _t_search_policy(self, query, plan_code, k=3):
        if plan_code not in CP.POLICIES:
            raise ToolError(f"unknown plan_code '{plan_code}'. Valid: {list(CP.POLICIES)}")
        hits = policy_index(plan_code).search(query, max(1, min(int(k), 5)))
        return "\n\n".join(f"## [{cid}] {title}\n{body}" for _, (cid, title, body) in hits) or "No matching clauses."

    def _t_debit_calculator(self, factor, **kw):
        try:
            if factor == "bmi":
                b = UE.bmi(kw["height_cm"], kw["weight_kg"]); rid, deb, out = UE.bmi_rule(b)
                return {"bmi": b, "rule": rid, "debits": deb, "outcome": out}
            if factor == "blood_pressure":
                rid, deb, out = UE.bp_rule(int(kw["systolic"]), int(kw["diastolic"]))
                return {"rule": rid, "debits": deb, "outcome": out}
            if factor == "hba1c":
                rid, deb, out = UE.hba1c_rule(float(kw["hba1c"]))
                return {"rule": rid, "debits": deb, "outcome": out, "note": "diabetes adjustments (duration, insulin) not included"}
            if factor == "lipids":
                ratio = round(kw["total_cholesterol"] / kw["hdl"], 1); rid, deb = UE.lipid_rule(ratio)
                return {"ratio": ratio, "rule": rid, "debits": deb}
        except KeyError as e:
            raise ToolError(f"missing argument {e} for factor {factor}")
        raise ToolError("unknown factor")

    def _t_calculator(self, expression):
        try:
            return {"result": round(safe_eval(expression), 6)}
        except Exception as e:
            raise ToolError(f"cannot evaluate: {e}")

    def _t_prior_application_lookup(self, applicant_id):
        env = self.case["env_data"]
        if applicant_id.strip() != env["applicant_id"]:
            raise ToolError(f"no applicant with id '{applicant_id}'")
        recs = env["mib"]
        return {"applicant_id": applicant_id, "records": recs, "note": "months_ago is measured back from the application date"} if recs else \
            {"applicant_id": applicant_id, "records": [], "note": "no prior applications or in-force cover found"}

    def _t_claims_history_lookup(self, policy_number):
        env = self.case["env_data"]
        if policy_number.strip() != env["policy_number"]:
            raise ToolError(f"no policy '{policy_number}'")
        return {"policy_number": policy_number, "prior_claims": env["prior_claims"]}

    def _t_order_evidence(self, code):
        code = code.strip().upper()
        if code not in UR.EVIDENCE_CODES:
            raise ToolError(f"unknown evidence code '{code}'. Valid: {list(UR.EVIDENCE_CODES)}")
        did = f"EV-{code}"
        if code in self.ordered:
            return {"doc_id": did, "status": "already ordered", "text": self.docs[did]["text"]}
        self.ordered.append(code)
        if did not in self.docs:
            env = self.case["env_data"]
            self.docs[did] = {"title": UR.EVIDENCE_CODES[code], "text": normal_stub(code, env), "visible": True, "evidence_code": code}
        if did not in self.visible:
            self.visible.append(did)
        return {"doc_id": did, "status": "result received", "text": self.docs[did]["text"]}

    def _t_icd10_lookup(self, code):
        from ..suites.coding import icd_table
        c = code.strip().upper().replace(".", "")
        hit = icd_table().get(c)
        if not hit:
            return {"code": code, "found": False}
        return {"code": code, "found": True, "billable": bool(hit[0]), "description": hit[1]}

    def _t_ask_user(self, question):
        return self.user.ask(question)

    def _t_refer_to_senior(self, reason):
        self.trace.referred = True
        return "Referral logged. A senior colleague will review. Still submit your recommended decision with submit_decision."

    def _t_submit_decision(self, decision=None, **extra):
        if decision is None and extra:
            decision = extra  # tolerate flattened arguments
        if isinstance(decision, str):
            try:
                decision = json.loads(decision)
            except Exception:
                raise ToolError("decision must be a JSON object")
        errs = validate(decision, SUBMIT_SCHEMAS[self.track])
        if errs:
            raise ToolError("invalid submission: " + "; ".join(errs[:8]))
        self.trace.submission = decision
        self.done = True
        return "Decision recorded. The case is closed."


class ToolError(Exception):
    pass
