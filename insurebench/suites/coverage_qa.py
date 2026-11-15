"""coverage_qa: policy-wording interpretation questions over the synthetic Meridian wordings. Gold answers are
computed from the same policy data the claims engine uses."""
from __future__ import annotations

import json
import os
import random
from decimal import Decimal
from pathlib import Path

from .. import CANARY
from ..claims import policies as P
from ..claims.engine import money


def _questions(rng: random.Random, n: int) -> list[dict]:
    out = []
    codes = list(P.POLICIES)
    conds = sorted(P.SPECIFIC_WAIT_CONDITIONS)
    templates = ["room", "deductible", "copay", "spec_wait", "spec_cover", "ped_wait", "sublimit", "prop", "nonpay", "accident", "si"]
    while len(out) < n:
        code = rng.choice(codes); pol = P.POLICIES[code]; t = rng.choice(templates)
        c = lambda x: P.clause_id(code, x)  # noqa: E731
        if t == "room":
            q, a, cl = "What is the maximum eligible room rent per day?", pol["room_limit_per_day"], c("4.1")
        elif t == "deductible":
            q, a, cl = "What deductible applies per claim (0 if none)?", pol["deductible"], c("5.1")
        elif t == "copay":
            q, a, cl = "What co-payment percentage does the insured bear (0 if none)?", pol["copay_pct"], c("5.2")
        elif t == "spec_wait":
            cond = rng.choice(conds)
            q, a, cl = f"How many days in force are required before treatment for {cond.replace('_', ' ')} is payable?", pol["specific_wait_days"], c("2.2")
        elif t == "spec_cover":
            cond = rng.choice(conds); day = pol["specific_wait_days"] + rng.choice([-30, -1, 0, 15])
            q = f"A non-accidental admission for {cond.replace('_', ' ')} happens {day} days after first inception (continuous cover). Is it payable under the waiting period rules? Answer yes or no."
            a, cl = ("yes" if day >= pol["specific_wait_days"] else "no"), c("2.2")
        elif t == "ped_wait":
            q, a, cl = "How many days in force are required before a pre-existing disease is covered?", pol["ped_wait_days"], c("2.3")
        elif t == "sublimit":
            if not pol["sublimits"]:
                continue
            cond, v = rng.choice(sorted(pol["sublimits"].items()))
            q, a, cl = f"What is the per-hospitalisation sublimit for {cond.replace('_', ' ')}?", v, c("4.4")
        elif t == "prop":
            lim = pol["room_limit_per_day"]; rate = int(lim * rng.choice([1.25, 1.5, 2.0])); assoc = rng.randrange(20_000, 80_000, 1000)
            q = (f"The insured stayed in a room billed at {rate:,} per day. Associated medical expenses (surgeon, anaesthetist, OT, "
                 f"nursing, doctor visits, investigations) total {assoc:,}. What is the proportionate deduction amount on those expenses?")
            a = float(money(Decimal(assoc) * (Decimal(1) - Decimal(lim) / Decimal(rate)))); cl = c("4.2")
        elif t == "nonpay":
            cat = rng.choice(sorted(P.NON_PAYABLE))
            q, a, cl = f"Is the item category '{P.NON_PAYABLE[cat]}' payable? Answer yes or no.", "no", c("3.1")
        elif t == "accident":
            day = rng.randint(1, 25)
            q, a, cl = f"An insured is hospitalised after a road accident {day} days after first inception. Does the initial waiting period prevent payment? Answer yes or no.", "no", c("2.1")
        else:
            q, a, cl = "What is the sum insured per policy year?", pol["sum_insured"], c("5.3")
        out.append({"plan": code, "question": q, "answer": a, "clause": cl, "template": t})
    return out


def build(data_dir: Path, n: int = 30) -> dict:
    res = {}
    for split in ("dev", "test"):
        rng = random.Random(20261115 if split == "dev" else f"{os.environ.get('INSUREBENCH_PRIVATE_SEED', 'public-test')}-cqa")
        cases, golds = [], []
        for i, qq in enumerate(_questions(rng, n), 1):
            cid = f"CQ{'T' if split == 'test' else ''}-{i:03d}"
            doc = f"<!-- {CANARY} -->\n# Coverage question\nPlan code: {qq['plan']}\nQuestion: {qq['question']}\n"
            cases.append({"canary": CANARY, "case_id": cid, "track": "coverage_qa", "family": cid, "variant": "clean", "tags": [qq["template"]],
                          "split": split, "documents": {"QUESTION": {"title": "Coverage question", "text": doc, "visible": True, "evidence_code": None}},
                          "hidden_facts": [], "env_data": {"plan": qq["plan"]},
                          "task": ("Answer the coverage question using the plan's policy wording (search_policy). Submit the answer (a number, "
                                   "or 'yes'/'no') and the clause_id that supports it.")})
            golds.append({"canary": CANARY, "case_id": cid, "track": "coverage_qa", "split": split,
                          "gold": {"decision": str(qq["answer"]), "answer": qq["answer"], "clause_id": qq["clause"], "template": qq["template"]}})
        for p, rows in ((data_dir / "coverage_qa" / f"{split}.jsonl", cases),
                        (data_dir / ("gold" if split == "dev" else "gold_hidden") / f"coverage_qa_{split}.jsonl", golds)):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
        res[f"coverage_qa_{split}"] = len(cases)
    return res
