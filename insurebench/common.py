"""Shared data structures."""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolEvent:
    step: int
    tool: str
    args: dict
    ok: bool
    result: Any
    error: str | None = None
    t: float = field(default_factory=time.time)


@dataclass
class Trace:
    case_id: str
    track: str
    harness: str
    model: str
    run_idx: int = 0
    events: list[ToolEvent] = field(default_factory=list)
    messages: list[dict] = field(default_factory=list)   # optional model transcript (truncated)
    submission: dict | None = None
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0
    status: str = "ok"           # ok | no_submission | budget_exceeded | error | skipped
    error: str | None = None
    referred: bool = False

    def to_dict(self) -> dict:
        d = asdict(self)
        # keep traces compact: truncate long tool results
        for e in d["events"]:
            r = e["result"]
            if isinstance(r, str) and len(r) > 1500:
                e["result"] = r[:1500] + "...[truncated]"
        return d
