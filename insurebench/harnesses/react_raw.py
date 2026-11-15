"""Minimal hand-rolled ReAct loop over raw provider APIs (no framework).

Providers: OpenRouter (default; OpenAI-compatible, one key for every model), Anthropic Messages API,
OpenAI Chat Completions. Selection by model name, see base.resolve_provider.
"""
from __future__ import annotations

import json
import os

from ..env.tools import BudgetExceeded, ToolEnv, anthropic_tools, openai_tools
from .base import (OPENROUTER_BASE, OPENROUTER_HEADERS, PROVIDER_KEYS, Harness, key_available, openrouter_model_id,
                   resolve_provider, system_prompt, user_prompt)

NUDGE = "You have not submitted a decision. Call submit_decision now with your best structured decision."


class ReactRaw(Harness):
    name = "react_raw"

    def run(self, case, tools: ToolEnv, model, budget):
        prov = resolve_provider(model)
        if not key_available(model):
            return self.skip(tools, f"{PROVIDER_KEYS[prov]} not set")
        try:
            if prov == "anthropic":
                self._anthropic(case, tools, model, budget)
            else:
                self._openai_compat(case, tools, model, budget, prov)
        except BudgetExceeded:
            pass
        except Exception as e:  # network / API errors are recorded, not raised
            tools.trace.status = "error"
            tools.trace.error = f"{type(e).__name__}: {e}"[:500]
        return tools.trace

    def _over_tokens(self, tools, budget):
        if tools.trace.tokens_in + tools.trace.tokens_out > budget["max_tokens"]:
            tools.trace.status = "budget_exceeded"
            return True
        return False

    # ---- Anthropic --------------------------------------------------------------------------
    def _anthropic(self, case, tools, model, budget):
        import anthropic
        client = anthropic.Anthropic()
        msgs = [{"role": "user", "content": user_prompt(case)}]
        nudged = False
        while not tools.done and not self._over_tokens(tools, budget):
            r = client.messages.create(model=model, system=system_prompt(case, budget), messages=msgs,
                                       tools=anthropic_tools(case["track"]), max_tokens=budget["max_output_tokens"])
            tools.trace.tokens_in += r.usage.input_tokens
            tools.trace.tokens_out += r.usage.output_tokens
            msgs.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in r.content]})
            uses = [b for b in r.content if b.type == "tool_use"]
            if not uses:
                if nudged:
                    break
                nudged = True
                msgs.append({"role": "user", "content": NUDGE})
                continue
            results = []
            for u in uses:
                out = tools.call(u.name, u.input)
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": out})
            msgs.append({"role": "user", "content": results})
        tools.trace.messages = msgs[-6:]

    # ---- OpenAI-compatible (OpenRouter, OpenAI) ---------------------------------------------
    def _openai_compat(self, case, tools, model, budget, prov):
        from openai import OpenAI
        if prov == "openrouter":
            client = OpenAI(base_url=OPENROUTER_BASE, api_key=os.environ["OPENROUTER_API_KEY"], default_headers=OPENROUTER_HEADERS)
            mid = openrouter_model_id(model)
        else:
            client, mid = OpenAI(), model
        msgs = [{"role": "system", "content": system_prompt(case, budget)}, {"role": "user", "content": user_prompt(case)}]
        nudged = False
        while not tools.done and not self._over_tokens(tools, budget):
            r = client.chat.completions.create(model=mid, messages=msgs, tools=openai_tools(case["track"]),
                                               max_tokens=budget["max_output_tokens"])
            if r.usage:
                tools.trace.tokens_in += r.usage.prompt_tokens or 0
                tools.trace.tokens_out += r.usage.completion_tokens or 0
            m = r.choices[0].message
            entry = {"role": "assistant", "content": m.content or ""}
            if m.tool_calls:
                entry["tool_calls"] = [{"id": tc.id, "type": "function",
                                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in m.tool_calls]
            msgs.append(entry)
            if not m.tool_calls:
                if nudged:
                    break
                nudged = True
                msgs.append({"role": "user", "content": NUDGE})
                continue
            for tc in m.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {"_raw": tc.function.arguments}
                out = tools.call(tc.function.name, args)
                msgs.append({"role": "tool", "tool_call_id": tc.id, "content": out})
        tools.trace.messages = msgs[-6:]
