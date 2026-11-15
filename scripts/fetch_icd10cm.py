"""Fetch the FY2026 ICD-10-CM code set (CMS/CDC NCHS, US public domain) and build the `coding_validity` suite.

Writes:
  data/sources/icd10cm_2026.tsv.gz   code<TAB>billable(0/1)<TAB>short description  (public domain, redistributable)
  data/coding/{dev,test}.jsonl, data/gold/coding_dev.jsonl, data/gold_hidden/coding_test.jsonl

Task: a claim lists diagnosis codes; identify codes that do not exist in ICD-10-CM FY2026 (invalid) and codes that exist
but are category headers that are not valid for claim submission (non_billable).
"""
from __future__ import annotations

import gzip
import json
import os
import random
import zipfile

from _common import ROOT, download, sha256, today

URL = "https://www.cms.gov/files/zip/2026-code-descriptions-tabular-order.zip"


def main():
    from insurebench import CANARY
    z = download(URL, "icd10cm_2026.zip")
    lines = zipfile.ZipFile(z).read("icd10cm_order_2026.txt").decode("latin-1").splitlines()
    table = {}
    for ln in lines:
        code, bill, short = ln[6:13].strip(), ln[14:15], ln[16:76].strip()
        table[code] = (int(bill), short)
    src = ROOT / "data" / "sources"
    src.mkdir(parents=True, exist_ok=True)
    with gzip.open(src / "icd10cm_2026.tsv.gz", "wt") as f:
        for c, (b, s) in sorted(table.items()):
            f.write(f"{c}\t{b}\t{s}\n")
    billable = sorted(c for c, (b, _) in table.items() if b == 1)
    headers = sorted(c for c, (b, _) in table.items() if b == 0 and len(c) >= 4)

    def dotted(c):
        return c if len(c) <= 3 else c[:3] + "." + c[3:]

    def fake(rng):
        while True:
            c = rng.choice(billable)
            alt = c[:-1] + rng.choice("0123456789XYZ")
            if alt not in table and len(alt) >= 4:
                return alt

    for split in ("dev", "test"):
        rng = random.Random(20261115 if split == "dev" else f"{os.environ.get('INSUREBENCH_PRIVATE_SEED', 'public-test')}-icd")
        cases, golds = [], []
        for i in range(1, 41):
            n = rng.randint(3, 6)
            codes = rng.sample(billable, n)
            invalid, nonbill = [], []
            for _ in range(rng.choice([0, 1, 1, 2])):
                invalid.append(fake(rng))
            for _ in range(rng.choice([0, 0, 1])):
                nonbill.append(rng.choice(headers))
            allc = codes + invalid + nonbill
            rng.shuffle(allc)
            primary = table[codes[0]][1]
            cid = f"CD{'T' if split == 'test' else ''}-{i:03d}"
            rows = "\n".join(f"| {k + 1} | {dotted(c)} |" for k, c in enumerate(allc))
            doc = (f"<!-- {CANARY} -->\n# Claim diagnosis coding (synthetic claim, real code set)\nClaim ID: {cid}\n"
                   f"Primary reason for encounter (narrative): {primary}\n\n| Line | ICD-10-CM code |\n|---|---|\n{rows}\n")
            cases.append({"canary": CANARY, "case_id": cid, "track": "coding", "family": cid, "variant": "clean", "tags": ["icd10cm"],
                          "split": split, "documents": {"CLAIM_CODES": {"title": "Claim diagnosis codes", "text": doc, "visible": True, "evidence_code": None}},
                          "hidden_facts": [], "env_data": {},
                          "task": ("You are a claims coding auditor. Check every diagnosis code on the claim against the ICD-10-CM FY2026 code set "
                                   "(use icd10_lookup). Submit invalid_codes (codes that do not exist) and non_billable_codes (codes that exist "
                                   "but are category headers not valid for claim submission), using the codes exactly as written on the claim.")})
            golds.append({"canary": CANARY, "case_id": cid, "track": "coding", "split": split,
                          "gold": {"decision": "clean" if not (invalid or nonbill) else "errors",
                                   "invalid_codes": sorted(dotted(c) for c in invalid), "non_billable_codes": sorted(dotted(c) for c in nonbill)}})
        for p, rows in ((ROOT / "data" / "coding" / f"{split}.jsonl", cases),
                        (ROOT / "data" / ("gold" if split == "dev" else "gold_hidden") / f"coding_{split}.jsonl", golds)):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("".join(json.dumps(r, sort_keys=True) + "\n" for r in rows))
    meta = {"source_url": URL, "retrieved": today(), "sha256": sha256(z), "codes": len(table), "billable": len(billable)}
    (src / "icd10cm_meta.json").write_text(json.dumps(meta, indent=1))
    print(meta)


if __name__ == "__main__":
    main()
