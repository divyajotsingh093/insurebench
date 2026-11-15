"""Optional external reference suite: Snorkel AI "Multi-Turn-Insurance-Underwriting" (Hugging Face, Apache-2.0).

US commercial P&C small-business underwriting, multi-turn. It is a different domain from InsureBench (life & health)
and is NOT scored by InsureBench graders in v0. This script downloads the parquet to data/raw/ and writes a 5-row
sample to data/sources/snorkel_underwriting_sample.json for reference/compatibility work.
"""
from __future__ import annotations

import json

from _common import ROOT, download, today

URL = "https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting/resolve/main/data/train-00000-of-00001.parquet"


def main():
    p = download(URL, "snorkel_multi_turn_underwriting.parquet")
    try:
        import pandas as pd
        df = pd.read_parquet(p)
        sample = json.loads(df.head(5).to_json(orient="records"))
        cols = list(df.columns); n = len(df)
    except Exception as e:  # pandas/pyarrow optional
        sample, cols, n = [], [], None
        print("pandas/pyarrow not available, sample skipped:", e)
    out = {"source": URL, "license": "apache-2.0", "retrieved": today(), "rows": n, "columns": cols, "sample": sample}
    (ROOT / "data" / "sources" / "snorkel_underwriting_sample.json").write_text(json.dumps(out, indent=1)[:200_000])
    print({k: out[k] for k in ("rows", "columns")})


if __name__ == "__main__":
    main()
