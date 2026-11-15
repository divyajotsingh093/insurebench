# InsureBench

An open benchmark for AI agents on **life & health insurance** work: underwriting, claims adjudication, appeals and
claim coding. It compares **models** and **harnesses** (agent frameworks) on the same tools, budgets and cases, and reports
every metric as its own column. There is no single blended score.

> v0. All underwriting/claims rules, manuals, policy wordings, people and cases are **synthetic and original**. The
> fictional carrier is "Meridian Mutual". Real public data is used only where the license allows it (see Suites).

## Why another benchmark?

[SnorkelUnderwrite](https://snorkel.ai/blog/evaluating-ai-agents-for-insurance-underwriting/) evaluates agents on
**US commercial P&C** small-business underwriting with **one harness**. InsureBench differs in four ways:

| | SnorkelUnderwrite | InsureBench |
|---|---|---|
| Line of business | Commercial P&C (US) | Individual life underwriting, health/hospitalisation claims, health appeals, claim coding |
| Comparison axis | Models | Models **and** harnesses (raw ReAct, LangGraph, Claude Agent SDK, OpenAI Agents SDK) |
| Gold | Expert-labelled | Computed by a rules engine in code (synthetic suites) or taken from public records (real suites) |
| Cross-cutting | Accuracy | pass^k, cost per correct, hallucinated IDs, tool-use quality, escalation, fairness, robustness, prompt injection |

Snorkel's dataset is Apache-2.0; `scripts/fetch_snorkel.py` downloads it as an optional external reference. InsureBench does not score it in v0.

## Suites

| Suite | Track | Source | License | Gold |
|---|---|---|---|---|
| `uw_synthetic` | uw | Synthetic Meridian underwriting manual + rules engine | CC-BY-4.0 | engine |
| `claims_synthetic` | claims | Synthetic policy wordings + claims engine; deductibles calibrated on CMS Marketplace PUF | CC-BY-4.0 / public domain | engine |
| `appeals_real` | appeals | California DMHC Independent Medical Review determinations (data.ca.gov) | CC-BY | real IMR outcome |
| `coding_validity` | coding | ICD-10-CM FY2026 code set (CMS/CDC NCHS) | public domain | official code table |
| `coverage_qa` | coverage_qa | Synthetic Meridian policy wordings | CC-BY-4.0 | engine |

Each suite has a data card in [`data/cards/`](data/cards). The UW and claims suites also include counterfactual fairness
twins (name/sex swapped), robustness twins (OCR noise + shuffled documents) and prompt-injection twins.

### Sources considered but not integrated in v0

| Source | Status | Reason |
|---|---|---|
| NY DFS external appeals database | rejected for v0 | The search page is reachable, but there is no bulk download or API; scraping a search UI is fragile and its terms of use are unclear. |
| CMS Benefits & Cost Sharing PUF | deferred | Reachable (13 MB). v0 uses the Plan Attributes PUF for deductibles; coinsurance/benefit-level mapping is future work. |
| CMS DE-SynPUF / Synthea | deferred | DE-SynPUF page reachable; Synthea GitHub returned 403 from this sandbox. Planned for realistic histories in UW disclosures. |
| CDC/NCHS life tables | deferred | FTP reachable, but no table was parsed for v0. Planned to ground debits in excess-mortality terms. |
| IRDAI Arogya Sanjeevani standard wording | rejected for v0 | No stable machine-retrievable document URL was verified, and IRDAI's reuse terms are not explicit. `coverage_qa` uses synthetic wordings. |
| Kaggle Prudential life assessment | not redistributed | Kaggle terms forbid redistribution. A user-run download script is future work. |
| HCPCS / CPT | deferred / rejected | HCPCS is public domain (future). CPT is AMA-copyrighted, so it is not used. |

## Quick start (offline, no keys)

```bash
pip install -e ".[agents,dev]" --break-system-packages
python -m insurebench build-data          # synthetic suites (uw, claims, coverage_qa)
python scripts/fetch_imr.py               # appeals_real (already committed; re-run to refresh)
python scripts/fetch_icd10cm.py           # coding_validity (already committed)
python -m insurebench run --suite all --harness baseline_rules --split dev
python -m insurebench run --suite all --harness baseline_naive --split dev
python -m insurebench report              # results/leaderboard.json, site/index.html, web/data/
pytest
```

## Real models (OpenRouter is the default provider)

One key covers every model: `export OPENROUTER_API_KEY=...`. Model ids are OpenRouter ids such as
`anthropic/claude-sonnet-5.5` or `deepseek/deepseek-v4.1-flash-1017`. Direct `ANTHROPIC_API_KEY` / `OPENAI_API_KEY` also
work with bare ids (`claude-*`, `gpt-*`). With no key, LLM harnesses record `skipped`. They never fail silently.

```bash
python -m insurebench roster show                       # the 30-model roster (15 open-weight, 15 closed)
python -m insurebench roster refresh                    # re-derive from the live OpenRouter catalogue (tool-capable only)
python -m insurebench estimate --suites all --models roster --harnesses react_raw --k 1
python -m insurebench run --suite uw --harness react_raw --model anthropic/claude-sonnet-5.5 --split dev --k 3 --max-usd 5
python -m insurebench sweep --suites all --models roster:5 --harnesses react_raw,langgraph_react --k 1 --max-usd 20
```

Cost per correct decision uses per-token prices recorded in `insurebench/models/roster.yaml` from the OpenRouter API.

## Harnesses

All harnesses implement `run(case, tools, model, budget) -> Trace` (`insurebench/harnesses/base.py`) and touch the case only
through the shared `ToolEnv`. That gives identical tools, budgets and logs for every harness.

| Harness | Status |
|---|---|
| `baseline_rules` | Deterministic agent that parses what it reads through the tools and applies the reference engine (oracle-ish sanity check; a prior-based baseline on `appeals_real`). |
| `baseline_naive` | Shallow, trusting heuristic (sanity check for low scores). |
| `react_raw` | Hand-rolled ReAct loop over raw OpenRouter / Anthropic / OpenAI APIs. |
| `langgraph_react` | LangGraph `create_react_agent` with the same tool schemas. |
| `claude_agent_sdk` | Claude Agent SDK with tools served as an in-process MCP server. Anthropic models only. |
| `openai_agents_sdk` | OpenAI Agents SDK `FunctionTool`s, routed through OpenRouter. |

The four LLM harnesses are implemented. None has been exercised against a live model yet, because no key was available while building v0.

**Add a harness:** subclass `Harness`, implement `run()` using `tools.call(name, args)` (or wrap `tool_specs(track)` for your
framework), and register it in `insurebench/harnesses/__init__.py`.

## Tools (Python and MCP)

`list_documents, read_document, search_manual, search_policy, debit_calculator, calculator, prior_application_lookup,
claims_history_lookup, order_evidence, icd10_lookup, ask_user, refer_to_senior, submit_decision`. Every call is logged to a
trace. To serve a case over MCP (stdio): `python -m insurebench mcp --track uw --case UW-001`.

## Submitting results

1. Run your harness/model on the **dev** split (`python -m insurebench run ... --split dev`).
2. POST the traces: `curl -X POST "https://<deployment>/api/submit?name=my-agent&model=...&harness=..." --data-binary @results/runs/<run>/traces.jsonl`.
   The API validates the schema and dev-only case ids, then stores the traces in Vercel Blob.
3. Maintainers score the hidden test split (generated with a private seed) and publish aggregate results.

## Repository layout

```
insurebench/  uw/ claims/ gen/ env/ harnesses/ grade/ suites/ models/ report/  cli.py runner.py
data/         uw/ claims/ coverage_qa/ appeals/ coding/ gold/ (dev)  cards/ sources/ manual/ policies/
              gold_hidden/ (gitignored; never published or bundled)
scripts/      fetch_imr.py fetch_icd10cm.py fetch_cms_puf.py fetch_snorkel.py run_in_sandbox.md
web/          Next.js leaderboard + /api/results + /api/submit (Vercel)
site/         static single-file leaderboard (fallback)
results/      run summaries, dev per-case results, leaderboard.json
```

See [METHODOLOGY.md](METHODOLOGY.md) and [DEPLOY.md](DEPLOY.md). Code: Apache-2.0. Data: see [LICENSE-DATA.md](LICENSE-DATA.md).

## Remote-agent harnesses (Neutrinos)

Agent platforms that run outside this process can be scored through the remote-agent protocol in
`insurebench/harnesses/remote.py`: one HTTPS request per step, the platform replies with the next tool call,
InsureBench executes it and sends back the result. The platform must act through the same tools as every other
harness, so results are directly comparable.

The `neutrinos` harness uses it. Set `NEUTRINOS_AGENT_URL` and `NEUTRINOS_API_KEY`, then:

```
python -m insurebench sweep --suites all --models roster:5 --harnesses react_raw,neutrinos --k 1 --max-usd 10
```

Running a model through several harnesses fills the Harness workbench on the leaderboard (lift vs plain ReAct).
