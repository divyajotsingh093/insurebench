"""Generate SIMULATED leaderboard results for UI preview only.

Model names are anonymised on purpose ("Closed model 07", "Open model 03") so fabricated numbers
can never be read as a real vendor's score. Every run carries demo=True; the web app watermarks
any chart built from them and drops them automatically once a real LLM run exists.
"""
import json, random
from pathlib import Path

rng = random.Random(20261115)
DEV_N = {"uw_synthetic": 25, "claims_synthetic": 25, "appeals_real": 40, "coding_validity": 40, "coverage_qa": 30}
TRACK = {"uw_synthetic": "uw", "claims_synthetic": "claims", "appeals_real": "appeals", "coding_validity": "coding", "coverage_qa": "coverage_qa"}
DIFF = {"uw_synthetic": 0.18, "claims_synthetic": 0.22, "appeals_real": 0.0, "coding_validity": 0.05, "coverage_qa": 0.08}
TOK = {"uw": (90000, 5000), "claims": (80000, 5000), "appeals": (4000, 600), "coding": (8000, 800), "coverage_qa": (12000, 600)}

models = []
for i in range(15):
    models.append(dict(id=f"demo/closed-model-{i+1:02d}", open=False, skill=0.92 - i * 0.025 + rng.uniform(-0.03, 0.03),
                       pin=[15, 10, 5, 3, 2, 1.25, 1, 0.8, 0.6, 0.5, 0.4, 0.3, 0.25, 0.15, 0.1][i]))
for i in range(15):
    models.append(dict(id=f"demo/open-model-{i+1:02d}", open=True, skill=0.84 - i * 0.03 + rng.uniform(-0.03, 0.03),
                       pin=[1.2, 0.9, 0.6, 0.5, 0.4, 0.35, 0.3, 0.25, 0.2, 0.15, 0.12, 0.1, 0.08, 0.06, 0.04][i]))

runs = []
for m in models:
    for s, n in DEV_N.items():
        if s == "appeals_real":
            p = 0.5 + (m["skill"] - 0.4) * 0.3 + rng.uniform(-0.04, 0.04)
        else:
            p = m["skill"] - DIFF[s] + rng.uniform(-0.06, 0.06)
        p = round(min(1, max(0, round(p * n) / n)), 4)
        tin, tout = TOK[TRACK[s]]
        cost = n * (tin * m["pin"] + tout * m["pin"] * 4) / 1e6
        correct = max(1, round(p * n))
        runs.append(dict(track=TRACK[s], suite=s, harness="react_raw", model=m["id"], split="dev", n_cases=n, k=1, demo=True,
                         primary_accuracy=p, cost_usd_total=round(cost, 4), cost_per_correct_usd=round(cost / correct, 5),
                         injection_resistance=round(min(1, max(0, m["skill"] + rng.uniform(-0.15, 0.1))), 3) if s in ("uw_synthetic", "claims_synthetic") else None,
                         hallucination_rate=round(max(0, (1 - m["skill"]) * 0.3 + rng.uniform(-0.03, 0.03)), 3)))
demo_roster = [dict(id=m["id"], name=m["id"], vendor="demo", open_weights=m["open"], hugging_face_id=None, context_length=0,
                    usd_per_1m_input=m["pin"], usd_per_1m_output=m["pin"] * 4, why="Simulated placeholder") for m in models]
out = Path(__file__).resolve().parents[1] / "web" / "data" / "demo.json"
out.write_text(json.dumps({"note": "SIMULATED DATA for UI preview. Not real model results.", "runs": runs, "roster": demo_roster}, indent=1))
print(f"wrote {len(runs)} simulated runs -> {out}")
