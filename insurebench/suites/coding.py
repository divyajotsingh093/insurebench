"""ICD-10-CM code table loader (data/sources/icd10cm_2026.tsv.gz, US public domain)."""
from __future__ import annotations

import gzip
from functools import lru_cache

from ..config import ROOT


@lru_cache(maxsize=1)
def icd_table() -> dict[str, tuple[int, str]]:
    p = ROOT / "data" / "sources" / "icd10cm_2026.tsv.gz"
    out = {}
    if not p.exists():
        return out
    with gzip.open(p, "rt") as f:
        for line in f:
            c, b, d = line.rstrip("\n").split("\t", 2)
            out[c] = (int(b), d)
    return out
