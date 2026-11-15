"""Pluggable free-text judges for UW rationales and claims letters.

- "heuristic" (default, offline, deterministic): checks that the text mentions the gold drivers
  (rule/clause IDs or factor names, decision, payable amount). Cheap and transparent, but shallow.
- "llm:<model>": rubric-based LLM judge via OpenRouter (or Anthropic for claude-* ids). Returns a 0-1 score.
- "none": no free-text score (column shows null).
"""
from __future__ import annotations

import json
import os
import re

UW_RUBRIC = """Score the underwriting rationale from 0 to 1.
1.0: states the decision and class, names every material rating factor with its manual rule ID, and nothing contradicts the gold.
0.5: decision is right but drivers are partly missing or rule IDs are vague. 0.0: wrong, missing or fabricated reasoning.
Gold drivers: {drivers}. Gold decision: {decision} / {table}.
Rationale: {text}
Reply with JSON {{"score": <0-1>, "why": "<short>"}}."""

LETTER_RUBRIC = """Score the claim decision letter from 0 to 1 for a lay claimant.
1.0: states the decision and the payable amount, explains each deduction or rejection ground with its clause ID, lists any
missing documents, and is courteous and clear. 0.0: wrong, missing or misleading.
Gold: decision {decision}, payable {payable}, clauses {clauses}, missing docs {missing}.
Letter: {text}
Reply with JSON {{"score": <0-1>, "why": "<short>"}}."""


def _heuristic_uw(text: str, gold: dict) -> float:
    t = (text or "").lower()
    drivers = set(gold["cited_rules"])
    if not drivers:
        return 1.0 if gold["decision"].replace("_", " ") in t or gold["decision"] in t else 0.5
    hit = sum(1 for r in drivers if r.lower() in t)
    dec = 1 if (gold["decision"] in t or gold["table_class"].lower() in t) else 0
    return round(0.8 * hit / len(drivers) + 0.2 * dec, 3)


def _heuristic_letter(text: str, gold: dict) -> float:
    t = (text or "").lower()
    pts, tot = 0, 0
    tot += 1; pts += gold["decision"].replace("_", " ") in t.replace("_", " ")
    tot += 1; pts += any(s in t for s in (f"{gold['payable_amount']:.2f}", f"{gold['payable_amount']:,.2f}", str(int(gold["payable_amount"]))))
    for c in gold["cited_clauses"]:
        tot += 1; pts += c.lower() in t
    for m in gold["missing_documents"]:
        tot += 1; pts += m.lower() in t or m.lower().replace("_", " ") in t
    return round(pts / tot, 3)


def _llm(prompt: str, model: str) -> float | None:
    try:
        if model.startswith("claude") and os.environ.get("ANTHROPIC_API_KEY"):
            import anthropic
            r = anthropic.Anthropic().messages.create(model=model, max_tokens=200, messages=[{"role": "user", "content": prompt}])
            txt = r.content[0].text
        elif os.environ.get("OPENROUTER_API_KEY"):
            from openai import OpenAI

            from ..harnesses.base import OPENROUTER_BASE, OPENROUTER_HEADERS, openrouter_model_id
            c = OpenAI(base_url=OPENROUTER_BASE, api_key=os.environ["OPENROUTER_API_KEY"], default_headers=OPENROUTER_HEADERS)
            txt = c.chat.completions.create(model=openrouter_model_id(model), max_tokens=200,
                                            messages=[{"role": "user", "content": prompt}]).choices[0].message.content
        else:
            return None
        m = re.search(r"\{.*\}", txt, re.S)
        return float(json.loads(m.group(0))["score"]) if m else None
    except Exception:
        return None


class Judge:
    def __init__(self, spec: str = "heuristic"):
        self.spec = spec

    def uw(self, text: str, gold: dict) -> float | None:
        if self.spec == "none":
            return None
        if self.spec.startswith("llm:"):
            s = _llm(UW_RUBRIC.format(drivers=gold["cited_rules"], decision=gold["decision"], table=gold["table_class"], text=text), self.spec[4:])
            return s if s is not None else _heuristic_uw(text, gold)
        return _heuristic_uw(text, gold)

    def letter(self, text: str, gold: dict) -> float | None:
        if self.spec == "none":
            return None
        if self.spec.startswith("llm:"):
            s = _llm(LETTER_RUBRIC.format(decision=gold["decision"], payable=gold["payable_amount"], clauses=gold["cited_clauses"],
                                          missing=gold["missing_documents"], text=text), self.spec[4:])
            return s if s is not None else _heuristic_letter(text, gold)
        return _heuristic_letter(text, gold)
