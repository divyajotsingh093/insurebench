"""Framework harness adapters: LangGraph ReAct, Claude Agent SDK, OpenAI Agents SDK.

All three wrap the SAME ToolEnv tool specs (names, descriptions, JSON schemas) and obey the same step budget
(enforced inside ToolEnv) and token budget (checked after the run). Each adapter imports its framework lazily
and reports `skipped` when the framework or the provider key is missing.
"""
from __future__ import annotations

import asyncio
import json
import os

from ..env.tools import BudgetExceeded, ToolEnv, tool_specs
from .base import (OPENROUTER_BASE, OPENROUTER_HEADERS, PROVIDER_KEYS, Harness, key_available, openrouter_model_id,
                   resolve_provider, system_prompt, user_prompt)


def _finish(tools, budget):
    if tools.trace.tokens_in + tools.trace.tokens_out > budget["max_tokens"]:
        tools.trace.status = "budget_exceeded"


class LangGraphReact(Harness):
    name = "langgraph_react"

    def _llm(self, model, budget):
        prov = resolve_provider(model)
        if prov == "anthropic":
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(model=model, max_tokens=budget["max_output_tokens"])
        from langchain_openai import ChatOpenAI
        if prov == "openrouter":
            return ChatOpenAI(model=openrouter_model_id(model), base_url=OPENROUTER_BASE, api_key=os.environ["OPENROUTER_API_KEY"],
                              default_headers=OPENROUTER_HEADERS, max_tokens=budget["max_output_tokens"])
        return ChatOpenAI(model=model, max_tokens=budget["max_output_tokens"])

    def run(self, case, tools: ToolEnv, model, budget):
        try:
            from langchain_core.tools import StructuredTool
            from langgraph.prebuilt import create_react_agent
        except ImportError as e:
            return self.skip(tools, f"langgraph not installed: {e}")
        if not key_available(model):
            return self.skip(tools, f"{PROVIDER_KEYS[resolve_provider(model)]} not set")

        def mk(spec):
            name = spec["name"]
            return StructuredTool(name=name, description=spec["description"], args_schema=spec["parameters"],
                                  func=lambda **kw: tools.call(name, kw))
        lc_tools = [mk(s) for s in tool_specs(case["track"])]
        try:
            agent = create_react_agent(self._llm(model, budget), lc_tools, prompt=system_prompt(case, budget))
            out = agent.invoke({"messages": [("user", user_prompt(case))]}, {"recursion_limit": 2 * budget["max_steps"] + 5})
            for m in out["messages"]:
                um = getattr(m, "usage_metadata", None)
                if um:
                    tools.trace.tokens_in += um.get("input_tokens", 0)
                    tools.trace.tokens_out += um.get("output_tokens", 0)
        except BudgetExceeded:
            pass
        except Exception as e:
            if not tools.done:
                tools.trace.status, tools.trace.error = "error", f"{type(e).__name__}: {e}"[:500]
        _finish(tools, budget)
        return tools.trace


class ClaudeAgentSDK(Harness):
    name = "claude_agent_sdk"

    def run(self, case, tools: ToolEnv, model, budget):
        try:
            import claude_agent_sdk as sdk
        except ImportError as e:
            return self.skip(tools, f"claude-agent-sdk not installed: {e}")
        prov = resolve_provider(model)
        if prov == "openai":
            return self.skip(tools, "claude_agent_sdk runs Anthropic models only (direct or via an Anthropic-compatible proxy)")
        env = {}
        if prov == "openrouter":
            # OpenRouter exposes an Anthropic-compatible endpoint; only Anthropic models are supported by the SDK.
            if not os.environ.get("OPENROUTER_API_KEY"):
                return self.skip(tools, "OPENROUTER_API_KEY not set")
            env = {"ANTHROPIC_BASE_URL": "https://openrouter.ai/api", "ANTHROPIC_AUTH_TOKEN": os.environ["OPENROUTER_API_KEY"],
                   "ANTHROPIC_API_KEY": ""}
        elif not os.environ.get("ANTHROPIC_API_KEY"):
            return self.skip(tools, "ANTHROPIC_API_KEY not set")

        def mk(spec):
            name = spec["name"]

            async def handler(args):
                try:
                    return {"content": [{"type": "text", "text": tools.call(name, args)}]}
                except BudgetExceeded:
                    return {"content": [{"type": "text", "text": "Budget exceeded. Stop."}], "is_error": True}
            return sdk.tool(name, spec["description"], spec["parameters"])(handler)

        server = sdk.create_sdk_mcp_server(name="ib", tools=[mk(s) for s in tool_specs(case["track"])])
        names = [f"mcp__ib__{s['name']}" for s in tool_specs(case["track"])]
        opts = sdk.ClaudeAgentOptions(mcp_servers={"ib": server}, allowed_tools=names, tools=[], system_prompt=system_prompt(case, budget),
                                      max_turns=budget["max_steps"] + 2, model=openrouter_model_id(model), permission_mode="bypassPermissions",
                                      env=env, setting_sources=[])

        async def go():
            async for msg in sdk.query(prompt=user_prompt(case), options=opts):
                if isinstance(msg, sdk.ResultMessage) and msg.usage:
                    u = msg.usage
                    tools.trace.tokens_in += u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
                    tools.trace.tokens_out += u.get("output_tokens", 0)
        try:
            asyncio.run(go())
        except Exception as e:
            if not tools.done:
                tools.trace.status, tools.trace.error = "error", f"{type(e).__name__}: {e}"[:500]
        _finish(tools, budget)
        return tools.trace


class OpenAIAgentsSDK(Harness):
    name = "openai_agents_sdk"

    def run(self, case, tools: ToolEnv, model, budget):
        try:
            import agents
            from openai import AsyncOpenAI
        except ImportError as e:
            return self.skip(tools, f"openai-agents not installed: {e}")
        prov = resolve_provider(model)
        if not key_available(model):
            return self.skip(tools, f"{PROVIDER_KEYS[prov]} not set")
        agents.set_tracing_disabled(True)
        if prov == "anthropic":
            return self.skip(tools, "use an OpenRouter id (e.g. anthropic/claude-sonnet-4.5) to run Claude models in the OpenAI Agents SDK")
        if prov == "openrouter":
            agents.set_default_openai_client(AsyncOpenAI(base_url=OPENROUTER_BASE, api_key=os.environ["OPENROUTER_API_KEY"],
                                                         default_headers=OPENROUTER_HEADERS), use_for_tracing=False)
            agents.set_default_openai_api("chat_completions")

        def mk(spec):
            name = spec["name"]

            async def invoke(ctx, args_json: str):
                try:
                    return tools.call(name, json.loads(args_json or "{}"))
                except BudgetExceeded:
                    return "Budget exceeded. Stop."
            return agents.FunctionTool(name=name, description=spec["description"], params_json_schema=spec["parameters"],
                                       on_invoke_tool=invoke, strict_json_schema=False)
        agent = agents.Agent(name="insurebench", instructions=system_prompt(case, budget), model=openrouter_model_id(model),
                             tools=[mk(s) for s in tool_specs(case["track"])],
                             model_settings=agents.ModelSettings(max_tokens=budget["max_output_tokens"]))
        try:
            res = agents.Runner.run_sync(agent, user_prompt(case), max_turns=budget["max_steps"] + 2)
            u = res.context_wrapper.usage
            tools.trace.tokens_in += u.input_tokens
            tools.trace.tokens_out += u.output_tokens
        except Exception as e:
            if not tools.done:
                tools.trace.status, tools.trace.error = "error", f"{type(e).__name__}: {e}"[:500]
        _finish(tools, budget)
        return tools.trace
