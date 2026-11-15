# Running harnesses in Vercel Sandbox (stub)

Not implemented in v0. Intended design:

1. Create a Sandbox (Firecracker microVM) from a Python image via the Vercel Sandbox SDK (`@vercel/sandbox`).
2. Copy the repo (or `pip install` the package from git) into the sandbox.
3. Pass `OPENROUTER_API_KEY` as an env var and run
   `python -m insurebench sweep --suites ... --models ... --max-usd ...`.
4. Read back `results/leaderboard.json` and upload it to Blob (`web/scripts/upload-blob.mjs`).

Why: isolates untrusted third-party harness code (e.g. community-submitted agents) from the CI runner and
the Blob token. Until this exists, use `.github/workflows/sweep.yml`.
