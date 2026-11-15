"""Shared helpers for fetch scripts. Raw downloads go to data/raw/ (gitignored)."""
from __future__ import annotations

import hashlib
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
sys.path.insert(0, str(ROOT))


def download(url: str, name: str, force: bool = False) -> Path:
    RAW.mkdir(parents=True, exist_ok=True)
    out = RAW / name
    if out.exists() and not force:
        return out
    req = urllib.request.Request(url, headers={"User-Agent": "insurebench-fetch/0.1"})
    with urllib.request.urlopen(req, timeout=300) as r, open(out, "wb") as f:
        f.write(r.read())
    return out


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def today() -> str:
    return time.strftime("%Y-%m-%d")
