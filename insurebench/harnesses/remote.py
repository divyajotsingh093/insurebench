"""Remote-agent harnesses: score an agent platform you don't run in-process (e.g. Neutrinos).

Protocol (JSON over HTTPS, one request per step). The platform keeps its own orchestration, memory and
prompting; InsureBench only supplies the case, the tool schemas, and the result of each tool call. The
platform must act through these tools so every harness is scored on identical terms.

  POST {BASE_URL}/insurebench/step
  Authorization: Bearer {API_KEY}
  {
    "session_id": "...",            # stable per case run
    "model": "anthropic/claude-...",# model the platform should use (OpenRouter-style id), if it supports choosing
    "case": {"case_id", "track", "task"},
    "system": "...",                # InsureBench system prompt (platforms may wrap it)
    "tools": [...],                 # OpenAI function-calling schemas
    "observation": null | {"tool": name, "args": {...}, "result": "..."},
    "budget": {"max_steps", "max_tokens"}
  }
  -> {"tool": "read_document", "args": {...}, "usage": {"input_tokens": 0, "output_tokens": 0}}
     or {"done": true, "usage": {...}}   # after it has called submit_decision

Configure with env vars:  NEUTRINOS_AGENT_URL, NEUTRINOS_API_KEY.
"""
from __future__ import annotations

import json
import os
import urllib.request
import uuid

from ..env.tools import BudgetExceeded, ToolEnv, openai_tools
from .base import Harness, system_prompt


class RemoteAgentHarness(Harness):
    name = "remote"
    url_env = ""
    key_env = ""
    timeout_s = 120

    def _post(self, url, key, payload):
        req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
        with urllib.request.urlopen(req, timeout=self.timeout_s) as r:
            return json.loads(r.read().decode())

    def run(self, case, tools: ToolEnv, model, budget):
        base, key = os.environ.get(self.url_env), os.environ.get(self.key_env)
        if not base or not key:
            return self.skip(tools, f"{self.url_env} / {self.key_env} not set")
        url = base.rstrip("/") + "/insurebench/step"
        sid, obs = str(uuid.uuid4()), None
        spec = openai_tools(case["track"])
        try:
            while not tools.done:
                resp = self._post(url, key, {"session_id": sid, "model": model, "system": system_prompt(case, budget),
                                             "case": {k: case[k] for k in ("case_id", "track", "task")}, "tools": spec,
                                             "observation": obs, "budget": {k: budget[k] for k in ("max_steps", "max_tokens")}})
                u = resp.get("usage") or {}
                tools.trace.tokens_in += int(u.get("input_tokens", 0))
                tools.trace.tokens_out += int(u.get("output_tokens", 0))
                if resp.get("done"):
                    break
                name, args = resp.get("tool"), resp.get("args") or {}
                obs = {"tool": name, "args": args, "result": tools.call(name, args)}
                if tools.trace.tokens_in + tools.trace.tokens_out > budget["max_tokens"]:
                    tools.trace.status = "budget_exceeded"
                    break
        except BudgetExceeded:
            pass
        except Exception as e:  # network / protocol errors are recorded, not raised
            tools.trace.status = "error"
            tools.trace.error = f"{type(e).__name__}: {e}"
        return tools.trace


class NeutrinosHarness(RemoteAgentHarness):
    name = "neutrinos"
    url_env = "NEUTRINOS_AGENT_URL"
    key_env = "NEUTRINOS_API_KEY"
