"""Fetch the CMS Health Insurance Marketplace Plan Attributes PUF (PY2025; US federal public domain) and derive
real-world plan-term calibration used to parameterise the synthetic claims policy variants.

Writes data/sources/cms_plan_params.json: median in-network individual deductible and MOOP by metal level.
claims/policies.py reads that committed file to set the BASIC / SILVER / GOLD deductibles (Bronze / Silver / Gold medians).
"""
from __future__ import annotations

import csv
import io
import json
import statistics
import zipfile

from _common import ROOT, download, sha256, today

URL = "https://download.cms.gov/marketplace-puf/2025/plan-attributes-puf.zip"


def money(s: str):
    s = (s or "").replace("$", "").replace(",", "").strip()
    try:
        return float(s.split()[0])
    except (ValueError, IndexError):
        return None


def main():
    z = download(URL, "plan_attributes_puf_2025.zip")
    zf = zipfile.ZipFile(z)
    r = csv.DictReader(io.TextIOWrapper(zf.open(zf.namelist()[0]), encoding="latin-1"))
    ded, moop = {}, {}
    for row in r:
        lvl = row.get("MetalLevel")
        if lvl not in ("Bronze", "Expanded Bronze", "Silver", "Gold", "Platinum") or row.get("DentalOnlyPlan") == "Yes":
            continue
        lvl = "Bronze" if "Bronze" in lvl else lvl
        d = money(row.get("TEHBDedInnTier1Individual")) or money(row.get("MEHBDedInnTier1Individual"))
        m = money(row.get("TEHBInnTier1IndividualMOOP")) or money(row.get("MEHBInnTier1IndividualMOOP"))
        if d is not None:
            ded.setdefault(lvl, []).append(d)
        if m is not None:
            moop.setdefault(lvl, []).append(m)
    out = {"source_url": URL, "retrieved": today(), "sha256": sha256(z), "plan_year": 2025,
           "median_individual_deductible": {k: statistics.median(v) for k, v in ded.items()},
           "median_individual_moop": {k: statistics.median(v) for k, v in moop.items()},
           "n_plans": {k: len(v) for k, v in ded.items()}}
    (ROOT / "data" / "sources" / "cms_plan_params.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
