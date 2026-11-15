"""Harness registry. To add a harness: subclass harnesses.base.Harness, implement run(), register below."""
from __future__ import annotations

from .baselines import BaselineNaive, BaselineRules
from .frameworks import ClaudeAgentSDK, LangGraphReact, OpenAIAgentsSDK
from .react_raw import ReactRaw
from .remote import NeutrinosHarness

HARNESSES = {h.name: h for h in (BaselineRules, BaselineNaive, ReactRaw, LangGraphReact, ClaudeAgentSDK, OpenAIAgentsSDK, NeutrinosHarness)}


def get_harness(name: str):
    if name not in HARNESSES:
        raise KeyError(f"unknown harness '{name}'. Available: {sorted(HARNESSES)}")
    return HARNESSES[name]()
