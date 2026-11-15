"""Static configuration: paths, budgets, token pricing."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("INSUREBENCH_DATA", ROOT / "data"))
RESULTS_DIR = Path(os.environ.get("INSUREBENCH_RESULTS", ROOT / "results"))
SITE_DIR = ROOT / "site"

# Identical budget for every harness so comparisons are fair.
DEFAULT_BUDGET = {
    "max_steps": 40,          # max tool calls per case
    "max_tokens": 250_000,    # total input+output tokens per case
    "max_output_tokens": 4096,  # per model turn
}

# USD per 1M tokens (input, output). Edit to match current list prices; used for cost-per-correct.
# Unknown models fall back to "default". Baselines cost 0.
PRICING = {
    "default": (3.00, 15.00),
    "claude-opus-4-5": (5.00, 25.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gemini-2.5-pro": (1.25, 10.00),
    "none": (0.0, 0.0),
}


# Assumed tokens per case (input, output) for the `estimate` command. Agentic tracks re-send the growing
# transcript every turn, so input dominates. Calibrate from real runs (summary.json tokens_per_case).
TOKEN_ESTIMATES = {"uw": (90_000, 5_000), "claims": (80_000, 5_000), "appeals": (4_000, 600),
                   "coding": (8_000, 800), "coverage_qa": (12_000, 600)}


def price_for(model: str) -> tuple[float, float]:
    from .models.roster import pricing
    rp = pricing()
    mid = model[len("openrouter/"):] if model.startswith("openrouter/") else model
    if mid in rp:
        return rp[mid]
    if model in PRICING:
        return PRICING[model]
    for k, v in PRICING.items():
        if k != "default" and model.startswith(k):
            return v
    return PRICING["default"]


def cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    pi, po = price_for(model)
    return (tokens_in * pi + tokens_out * po) / 1_000_000


def available_providers() -> dict[str, bool]:
    return {
        "anthropic": bool(os.environ.get("ANTHROPIC_API_KEY")),
        "openai": bool(os.environ.get("OPENAI_API_KEY")),
        "gemini": bool(os.environ.get("GEMINI_API_KEY")),
    }


def provider_for(model: str) -> str:
    m = model.lower()
    if m.startswith("claude"):
        return "anthropic"
    if m.startswith(("gpt", "o1", "o3", "o4")):
        return "openai"
    if m.startswith("gemini"):
        return "gemini"
    return "unknown"
