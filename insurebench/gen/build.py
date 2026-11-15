"""Build the InsureBench v0 dataset: 50 UW + 50 claims cases, dev/test split, manual and wordings.

Layout written to data/:
  manual/uw_manual.md, policies/<code>.md
  uw/dev.jsonl, uw/test.jsonl, claims/dev.jsonl, claims/test.jsonl       (public cases, no gold)
  gold/uw_dev.jsonl, gold/claims_dev.jsonl                                 (public dev gold)
  gold_hidden/uw_test.jsonl, gold_hidden/claims_test.jsonl                 (HIDDEN test gold - do not publish)
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path

from .. import CANARY
from ..claims.policies import POLICIES
from ..claims.wording import render_wording
from ..uw.manual import render_manual
from . import claims_gen, uw_gen
from .common import swap_name

SEED = 20261115

UW_PLAN = (["base"] * 30 + ["nondisclosure_dm"] * 2 + ["nondisclosure_smoker"] * 1 + ["borderline"] * 3 +
           ["refer_authority"] * 1 + ["mib_decline"] * 1)
CLAIMS_PLAN = (["base"] * 28 + ["ped_wait", "fraud_outside_period","edge_initial_wait", "edge_specific_wait", "edge_accident", "room_prop", "si_exhaust",
                                "missing_docs", "fraud_inflated", "fraud_duplicate"])
# 38 families each + 4 fairness + 4 noisy + 4 injection = 50 per track
VARIANTS = ["fairness_swap"] * 4 + ["noisy"] * 4 + ["injection"] * 4


def _make_track(track: str, rng: random.Random, test: bool = False):
    gen = uw_gen if track == "uw" else claims_gen
    plan = UW_PLAN if track == "uw" else CLAIMS_PLAN
    prefix = ("UW" if track == "uw" else "CL") + ("T" if test else "")
    cases, golds, base_facts = [], [], {}
    for i, kind in enumerate(plan, start=1):
        cid = f"{prefix}-{i:03d}"
        facts = gen.sample_facts(rng, i, kind)
        c, g = gen.build_case(cid, facts, "clean", rng, tags=[kind] if kind != "base" else ["base"])
        cases.append(c); golds.append(g); base_facts[cid] = facts
    base_ids = [c["case_id"] for c in cases if c["tags"] == ["base"]]
    # prefer interesting bases for injection (gold != injection target)
    target = "accept_standard" if track == "uw" else "pay"
    gold_by = {g["case_id"]: g["gold"] for g in golds}
    inj_pool = [b for b in base_ids if gold_by[b]["decision"] != target]
    chosen_inj = rng.sample(inj_pool, 4)
    rest = [b for b in base_ids if b not in chosen_inj]
    chosen_fair = rng.sample(rest, 4)
    rest = [b for b in rest if b not in chosen_fair]
    chosen_noisy = rng.sample(rest, 4)
    n = len(plan)
    for variant, bases in (("fairness_swap", chosen_fair), ("noisy", chosen_noisy), ("injection", chosen_inj)):
        for b in bases:
            n += 1
            cid = f"{prefix}-{n:03d}"
            facts = json.loads(json.dumps(base_facts[b]))
            if variant == "fairness_swap":
                key_name = "name" if track == "uw" else "member_name"
                facts[key_name], facts["sex"] = swap_name(facts[key_name], facts["sex"])
            c, g = gen.build_case(cid, facts, variant, rng, family=b, tags=[variant])
            cases.append(c); golds.append(g)
    return cases, golds


def _split(cases, golds, rng):
    fams = sorted({c["family"] for c in cases})
    var_fams = sorted({c["family"] for c in cases if c["variant"] != "clean"})
    plain = [f for f in fams if f not in var_fams]
    rng.shuffle(var_fams); rng.shuffle(plain)
    dev_f = set(var_fams[: len(var_fams) // 2] + plain[: len(plain) // 2])
    out = {"dev": ([], []), "test": ([], [])}
    for c, g in zip(cases, golds):
        s = "dev" if c["family"] in dev_f else "test"
        c["split"] = s; g["split"] = s
        out[s][0].append(c); out[s][1].append(g)
    return out


def _write_jsonl(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def build(out_dir: Path, seed: int = SEED) -> dict:
    out_dir = Path(out_dir)
    summary = {}
    (out_dir / "manual").mkdir(parents=True, exist_ok=True)
    (out_dir / "manual" / "uw_manual.md").write_text(render_manual())
    (out_dir / "policies").mkdir(parents=True, exist_ok=True)
    for code in POLICIES:
        (out_dir / "policies" / f"{code}.md").write_text(render_wording(code))
    private = os.environ.get("INSUREBENCH_PRIVATE_SEED")
    summary["test_seed"] = "private (INSUREBENCH_PRIVATE_SEED)" if private else "public default (NOT hidden: regenerable by anyone)"
    for track in ("uw", "claims"):
        # dev comes from the public seed; test comes from a separate stream that is private when
        # INSUREBENCH_PRIVATE_SEED is set (the official leaderboard), so test gold cannot be regenerated.
        rng = random.Random(f"{seed}-{track}")
        cases, golds = _make_track(track, rng)
        dev = _split(cases, golds, rng)["dev"]
        trng = random.Random(f"{private or str(seed) + '-public-test'}-{track}")
        tcases, tgolds = _make_track(track, trng, test=True)
        test = _split(tcases, tgolds, trng)["test"]
        for s, (cs, gs) in {"dev": dev, "test": test}.items():
            _write_jsonl(out_dir / track / f"{s}.jsonl", cs)
            gdir = "gold" if s == "dev" else "gold_hidden"
            _write_jsonl(out_dir / gdir / f"{track}_{s}.jsonl", gs)
            summary[f"{track}_{s}"] = len(cs)
    from ..suites import coverage_qa
    summary.update(coverage_qa.build(out_dir))
    (out_dir / "gold_hidden" / "README.md").write_text(
        f"<!-- {CANARY} -->\nHIDDEN TEST GOLD. Do not publish, do not commit to a public mirror, do not bundle in the web app.\n"
        "Kept in the repo for v0 reproducibility only; the public release removes this directory (see DEPLOY.md).\n")
    (out_dir / "CANARY.txt").write_text(CANARY + "\n")
    return summary


def load_cases(data_dir: Path, track: str, split: str) -> list[dict]:
    p = Path(data_dir) / track / f"{split}.jsonl"
    return [json.loads(line) for line in open(p)]


def load_gold(data_dir: Path, track: str, split: str) -> dict[str, dict]:
    d = "gold" if split == "dev" else "gold_hidden"
    p = Path(data_dir) / d / f"{track}_{split}.jsonl"
    if not p.exists():
        return {}
    return {g["case_id"]: g for g in (json.loads(line) for line in open(p))}
