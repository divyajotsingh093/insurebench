"""Tiny dependency-free BM25 over manual / policy sections."""
from __future__ import annotations

import math
import re
from collections import Counter

_TOK = re.compile(r"[a-z0-9]+(?:[-.][a-z0-9]+)*")


def tokenize(s: str) -> list[str]:
    return _TOK.findall(s.lower())


class BM25:
    def __init__(self, docs: list[tuple[str, str, str]], k1: float = 1.4, b: float = 0.75):
        """docs: list of (id, title, body)."""
        self.docs = docs
        self.toks = [tokenize(f"{i} {t} {t} {body}") for i, t, body in docs]
        self.k1, self.b = k1, b
        self.avgdl = sum(len(t) for t in self.toks) / max(1, len(self.toks))
        df = Counter()
        for t in self.toks:
            df.update(set(t))
        n = len(docs)
        self.idf = {w: math.log(1 + (n - c + 0.5) / (c + 0.5)) for w, c in df.items()}
        self.tf = [Counter(t) for t in self.toks]

    def search(self, query: str, k: int = 3) -> list[tuple[float, tuple[str, str, str]]]:
        q = tokenize(query)
        scores = []
        for i, tf in enumerate(self.tf):
            dl = len(self.toks[i])
            s = 0.0
            for w in q:
                if w in tf:
                    f = tf[w]
                    s += self.idf.get(w, 0) * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            scores.append((s, self.docs[i]))
        scores.sort(key=lambda x: -x[0])
        return [x for x in scores[:k] if x[0] > 0]
