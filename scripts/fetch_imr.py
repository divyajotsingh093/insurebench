"""Fetch California DMHC Independent Medical Review (IMR) determinations and build the `appeals_real` suite.

Source: data.ca.gov / CHHS Open Data, "Independent Medical Review (IMR) Determinations, Trend"
License: Creative Commons Attribution (CC-BY) per the dataset page. Redistribution of the processed subset is allowed
with attribution (see data/cards/appeals_real.md).

Task: given the case facts (diagnosis/treatment categories, review type, age band, and the clinical part of the
reviewer's summary with the conclusion redacted) predict whether the IMR UPHELD or OVERTURNED the health plan's denial.

Usage: python scripts/fetch_imr.py [--n-per-split 40]
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random
import re

from _common import ROOT, download, sha256, today

URL = ("https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/"
       "3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv")
DECISIVE = re.compile(r"(necessary|appropriate|indicated|warranted|therefore|likely to be|beneficial|standard of care|"
                      r"recommend|supports? the|does not support|evidence[- ]based|efficacy|effective|safe|insufficient|"
                      r"guideline|literature|studies|consistent with)", re.I)


def redact(findings: str) -> str | None:
    t = findings.replace("Findings:", "").split("Final Result:")[0].strip()
    t = re.sub(r"The (physician )?reviewers? found that ", "", t)
    sents = re.split(r"(?<=[.!?])\s+", t)
    keep = []
    for i, s in enumerate(sents):
        if i > 0 and DECISIVE.search(s):
            break
        if i == 0:
            s = re.sub(r"(?i)^an? (enrollee|patient|member)", "The patient", s)
        keep.append(s)
    if len(keep) < 2 or len(" ".join(keep)) < 120:
        return None
    return " ".join(keep)


def main():
    from insurebench import CANARY
    ap = argparse.ArgumentParser()
    ap.add_argument("--n-per-split", type=int, default=40)
    a = ap.parse_args()
    raw = download(URL, "imr_determinations.csv")
    rows = list(csv.DictReader(open(raw, encoding="utf-8-sig")))
    pool = []
    for r in rows:
        if r["ReportYear"] < "2022":
            continue
        summ = redact(r["Findings"])
        if summ:
            pool.append((r, summ))
    rng = random.Random(20261115)
    rng.shuffle(pool)
    pub, priv = os.environ.get("INSUREBENCH_PRIVATE_SEED"), None
    out = {"dev": [], "test": []}
    used = set()
    for split in ("dev", "test"):
        srng = random.Random(f"{pub or 'public-test'}-imr") if split == "test" else rng
        cand = [p for p in pool if p[0]["ReferenceID"] not in used]
        srng.shuffle(cand)
        for label in ("Upheld Decision of Health Plan", "Overturned Decision of Health Plan"):
            picked = [p for p in cand if p[0]["Determination"] == label][: args_n(a) // 2]
            for p in picked:
                used.add(p[0]["ReferenceID"])
            out[split] += picked
        srng.shuffle(out[split])
    del priv
    for split, items in out.items():
        cases, golds = [], []
        for i, (r, summ) in enumerate(items, 1):
            cid = f"AP{'T' if split == 'test' else ''}-{i:03d}"
            doc = (f"<!-- {CANARY} -->\n# Independent Medical Review case file\n"
                   f"Review type: {r['Type']}\nIMR track: {r['IMRType']}\nDiagnosis category: {r['DiagnosisCategory']} / {r['DiagnosisSubCategory']}\n"
                   f"Treatment category: {r['TreatmentCategory']} / {r['TreatmentSubCategory']}\nPatient age range: {r['AgeRange']}\n"
                   f"Patient gender: {r['PatientGender']}\nReport year: {r['ReportYear']}\n\n## Clinical summary (reviewer conclusion redacted)\n{summ}\n")
            cases.append({"canary": CANARY, "case_id": cid, "track": "appeals", "family": cid, "variant": "clean", "tags": [r["Type"]],
                          "split": split, "documents": {"CASE": {"title": "IMR case file", "text": doc, "visible": True, "evidence_code": None}},
                          "hidden_facts": [], "env_data": {"type": r["Type"], "treatment": r["TreatmentCategory"], "gender": r["PatientGender"]},
                          "task": ("You are a health-insurance appeals analyst. An enrollee appealed a health plan's denial to an Independent "
                                   "Medical Review. Read the case file and predict whether the reviewer UPHELD the plan's denial or OVERTURNED it. "
                                   "Submit determination 'upheld' or 'overturned' with a short rationale.")})
            golds.append({"canary": CANARY, "case_id": cid, "track": "appeals", "split": split,
                          "gold": {"decision": "upheld" if r["Determination"].startswith("Upheld") else "overturned", "source_id": r["ReferenceID"]}})
        _write(ROOT / "data" / "appeals" / f"{split}.jsonl", cases)
        _write(ROOT / "data" / ("gold" if split == "dev" else "gold_hidden") / f"appeals_{split}.jsonl", golds)
    # priors from rows NOT used in the suite (for the prior-based baseline)
    prior = {}
    for r in rows:
        if r["ReferenceID"] in used:
            continue
        k = f"{r['Type']}|{r['TreatmentCategory']}"
        c = prior.setdefault(k, [0, 0])
        c[0 if r["Determination"].startswith("Upheld") else 1] += 1
    (ROOT / "data" / "sources").mkdir(parents=True, exist_ok=True)
    (ROOT / "data" / "sources" / "imr_priors.json").write_text(json.dumps(prior, indent=0, sort_keys=True))
    meta = {"source_url": URL, "retrieved": today(), "sha256": sha256(raw), "rows_total": len(rows), "pool_after_redaction": len(pool),
            "dev": len(out["dev"]), "test": len(out["test"])}
    (ROOT / "data" / "sources" / "imr_meta.json").write_text(json.dumps(meta, indent=1))
    print(meta)


def args_n(a):
    return a.n_per_split


def _write(p, rows):
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
