"""Simulated user (tau-bench style): a junior underwriter / claims handler who owns the case and holds
some facts back, revealing them only when asked a relevant question.

RuleBasedUser is deterministic (offline default). LLMUser wraps an LLM but is constrained to the same
hidden facts; it falls back to RuleBasedUser when no provider is available.
"""
from __future__ import annotations

import os

NO_INFO = "I don't have any further information on that. Please work from the documents and tools."


class RuleBasedUser:
    def __init__(self, hidden_facts: list[dict], role: str):
        self.hidden = hidden_facts
        self.role = role
        self.revealed: set[str] = set()

    def ask(self, question: str) -> str:
        q = (question or "").lower()
        hits = [h for h in self.hidden if any(k.lower() in q for k in h["keywords"])]
        if not hits:
            return NO_INFO
        for h in hits:
            self.revealed.add(h["key"])
        return " ".join(h["answer"] for h in hits)


class LLMUser(RuleBasedUser):
    """Paraphrases only facts that the rule-based matcher would reveal (keeps grading deterministic
    with respect to what information is available)."""

    def __init__(self, hidden_facts, role, model: str = "claude-haiku-4-5"):
        super().__init__(hidden_facts, role)
        self.model = model

    def ask(self, question: str) -> str:
        base = super().ask(question)
        if base == NO_INFO or not os.environ.get("ANTHROPIC_API_KEY"):
            return base
        try:
            import anthropic
            msg = anthropic.Anthropic().messages.create(
                model=self.model, max_tokens=200,
                system=f"You are a busy junior {self.role}. Answer the colleague's question in one or two sentences using ONLY these facts: {base}",
                messages=[{"role": "user", "content": question}])
            return msg.content[0].text
        except Exception:
            return base


def make_user(case: dict, kind: str = "rule"):
    role = "underwriter" if case["track"] == "uw" else "claims handler"
    if kind == "llm":
        return LLMUser(case["hidden_facts"], role)
    return RuleBasedUser(case["hidden_facts"], role)
