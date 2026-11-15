"use client";
import { useMemo, useState } from "react";
import type { Leaderboard as LB, Run } from "@/lib/data";
import demoData from "@/data/demo.json";
import { type Agent, type Kind, BenchCards, HarnessBench, HeadToHead, Heatmap, IndexChart, Seg, ValueMap, harnessLabel } from "@/components/viz";

const HIDE = new Set(["track", "harness", "model", "suite", "split", "judge", "status_counts", "generated_at", "stopped", "note", "skipped", "skip_reason", "n_cases", "k", "demo"]);
const META: Record<string, { label: string; blurb: string; kind: string; source: string }> = {
  uw_synthetic: { label: "Underwriting", blurb: "Life & health: debits, table class, evidence, exclusions, referral.", kind: "Agentic · synthetic", source: "Rules engine (fictional carrier)" },
  claims_synthetic: { label: "Claims adjudication", blurb: "Admissibility, payable amount, clause citations, fraud flags.", kind: "Agentic · synthetic", source: "Policy engine, CMS PUF deductibles" },
  appeals_real: { label: "Real appeals", blurb: "Predict the outcome of real health-claim denial appeals.", kind: "Real data", source: "California DMHC IMR (CC-BY)" },
  coding_validity: { label: "Medical coding", blurb: "Is this ICD-10-CM code valid and billable for the case?", kind: "Real data", source: "ICD-10-CM FY2026 (public domain)" },
  coverage_qa: { label: "Policy wording QA", blurb: "Answer coverage questions from policy wording.", kind: "QA · synthetic", source: "Synthetic policy wordings" },
};
const suiteLabel = (s: string) => (s === "overall" ? "Overall" : META[s]?.label ?? s);

function Cell({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <td className="na">-</td>;
  if (typeof v === "number") return <td>{Math.abs(v) < 10 ? v.toFixed(3) : v.toFixed(1)}</td>;
  return <td>{String(v)}</td>;
}

export default function Leaderboard({ lb: real }: { lb: LB }) {
  const hasReal = real.runs.some((r) => r.model !== "none" && !r.skipped);
  const [demo, setDemo] = useState(!hasReal);
  const lb: LB = demo && !hasReal
    ? { ...real, runs: [...real.runs, ...(demoData.runs as unknown as Run[])], roster: { ...real.roster, models: demoData.roster as any } }
    : real;
  const suites = Object.keys(lb.suites);
  const [suite, setSuite] = useState<string>("overall");
  const [filter, setFilter] = useState<"all" | Kind>("all");
  const splits = useMemo(() => Array.from(new Set(lb.runs.map((r) => r.split))), [lb]);
  const [split, setSplit] = useState(splits.includes("dev") ? "dev" : splits[0]);
  const [focus, setFocus] = useState<string | null>(null);
  const roster = useMemo(() => Object.fromEntries(lb.roster.models.map((m) => [m.id, m])), [lb]);
  const kind = (m: string): Kind => (m === "none" ? "baseline" : roster[m.replace("openrouter/", "")]?.open_weights ? "open" : "closed");

  const allAgents: Agent[] = useMemo(() => {
    const map = new Map<string, Agent>();
    for (const r of lb.runs) {
      if (r.split !== split || r.skipped) continue;
      const key = r.harness + "|" + r.model;
      if (!map.has(key)) {
        const short = r.model === "none" ? r.harness.replace("baseline_", "") + " baseline" : r.model.split("/").pop()!;
        map.set(key, { key, model: r.model, harness: r.harness, kind: kind(r.model), vendor: r.model === "none" ? "" : (roster[r.model]?.vendor !== "demo" && roster[r.model]?.vendor) || short.split("-")[0], name: short, runs: [] });
      }
      map.get(key)!.runs.push(r);
    }
    return Array.from(map.values()).filter((a) => filter === "all" || a.kind === filter);
  }, [lb, split, filter]); // eslint-disable-line react-hooks/exhaustive-deps

  // Main model charts use one harness per model so models aren't double-counted; the harness workbench uses all.
  const harnesses = Array.from(new Set(allAgents.filter((a) => a.kind !== "baseline").map((a) => a.harness)));
  const [mainHarness, setMainHarness] = useState("react_raw");
  const mh = harnesses.includes(mainHarness) ? mainHarness : harnesses[0];
  const agents = allAgents.filter((a) => a.kind === "baseline" || a.harness === mh).map((a) => (a.kind === "baseline" || a.harness === "react_raw" ? a : { ...a, name: `${a.name} · ${harnessLabel(a.harness)}` }));
  const prices = Object.fromEntries(lb.roster.models.map((m) => [m.id, { in: m.usd_per_1m_input, out: m.usd_per_1m_output }]));

  const tableRuns: Run[] = lb.runs.filter((r) => (suite === "overall" || r.suite === suite) && r.split === split && !r.skipped && (filter === "all" || kind(r.model) === filter));
  const keys = Array.from(new Set(tableRuns.flatMap((r) => Object.keys(r)))).filter((k) => !HIDE.has(k) && tableRuns.some((r) => typeof r[k] === "number"));
  const trace = lb.sample_traces[lb.suites[suite === "overall" ? suites[0] : suite]?.track];

  return (
    <div className={demo && !hasReal ? "is-demo" : ""}>
      {!hasReal && (
        <div className={`demo-banner ${demo ? "on" : ""}`}>
          <b>{demo ? "Simulated preview." : "No model results yet."}</b>{" "}
          {demo ? "Every model and harness score on this page is made up to show the layout. Model names are anonymised and the numbers are not real. Real results replace them automatically after the first OpenRouter sweep." : "Only the two reference baselines have run."}
          <label><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> Show simulated preview</label>
        </div>)}

      <h2 className="sec">Eval workbenches</h2>
      <BenchCards agents={agents} suites={suites} meta={META} active={suite} onPick={(s) => setSuite(s === suite ? "overall" : s)} />

      <div className="toolbar">
        <Seg label="Suite" value={suite} onChange={setSuite} options={[{ v: "overall", l: "Overall" }, ...suites.map((s) => ({ v: s, l: suiteLabel(s) }))]} />
        <div className="toolbar-r">
          <Seg label="Models" value={filter} onChange={setFilter} options={[{ v: "all", l: "All" }, { v: "closed", l: "Closed" }, { v: "open", l: "Open" }, { v: "baseline", l: "Baselines" }]} />
          {harnesses.length > 1 && <label className="ctl">Harness <select value={mh} onChange={(e) => setMainHarness(e.target.value)}>{harnesses.map((h) => <option key={h} value={h}>{harnessLabel(h)}</option>)}</select></label>}
          <label className="ctl">Split <select value={split} onChange={(e) => setSplit(e.target.value)}>{splits.map((s) => <option key={s}>{s}</option>)}</select></label>
          {focus && <button className="chip" onClick={() => setFocus(null)}>Clear highlight ✕</button>}
        </div>
      </div>

      <div className="card bare"><IndexChart agents={agents} suite={suite} suiteLabel={`InsureBench · ${suiteLabel(suite)}`} focus={focus} setFocus={setFocus} /></div>
      <div className="card bare"><ValueMap agents={agents} suite={suite} prices={prices} focus={focus} setFocus={setFocus} /></div>
      <h2 className="sec">Harness workbench</h2>
      <div className="card bare"><HarnessBench agents={allAgents} suite={suite} suiteLabel={suiteLabel(suite)} /></div>
      <div className="grid2">
        <div className="card bare"><HeadToHead agents={agents} suites={suites} suiteLabel={suiteLabel} /></div>
      </div>
      <div className="card bare"><Heatmap agents={agents} suites={suites} suiteLabel={suiteLabel} focus={focus} setFocus={setFocus} /></div>

      <details className="card">
        <summary><h2 style={{ display: "inline" }}>All metrics ({suiteLabel(suite)}, {tableRuns.length} runs)</h2></summary>
        <table><thead><tr><th>run</th>{keys.map((k) => <th key={k} title={lb.metric_defs[k] || ""}>{k}</th>)}</tr></thead>
          <tbody>{tableRuns.map((r) => <tr key={r.suite + r.harness + r.model}><td>{r.suite} · {harnessLabel(r.harness)} &times; {r.model}</td>{keys.map((k) => <Cell key={k} v={r[k]} />)}</tr>)}</tbody></table>
      </details>
      <details className="card">
        <summary><h2 style={{ display: "inline" }}>Sample trace</h2></summary>
        {!trace ? <p className="muted">No trace.</p> : (<>
          <p className="muted">{trace.case_id} &middot; {trace.harness} &times; {trace.model} &middot; {trace.events.length} tool calls &middot; {trace.status}</p>
          {trace.events.map((e: any, i: number) => (
            <div key={i} className={`ev ${e.ok ? "" : "bad"}`}><b className="mono">{e.tool}</b> <span className="muted mono">{JSON.stringify(e.args).slice(0, 240)}</span>
              <pre>{String(e.ok ? e.result : e.error).slice(0, 1200)}</pre></div>))}
          <h2>Submission</h2><pre>{JSON.stringify(trace.submission, null, 1)}</pre>
        </>)}
      </details>
      <details className="card">
        <summary><h2 style={{ display: "inline" }}>Model roster ({real.roster.models.length})</h2></summary>
        <p className="muted">{real.roster.selection_basis} (retrieved {real.roster.retrieved}).</p>
        <table><thead><tr><th>id</th><th>weights</th><th>context</th><th>$/1M in</th><th>$/1M out</th><th>why</th></tr></thead>
          <tbody>{real.roster.models.map((m) => (
            <tr key={m.id}><td className="mono">{m.id}</td><td>{m.open_weights ? "open" : "closed"}</td><td>{m.context_length?.toLocaleString()}</td>
              <td>{m.usd_per_1m_input}</td><td>{m.usd_per_1m_output}</td><td className="wrap">{m.why}</td></tr>))}</tbody></table>
      </details>
    </div>
  );
}
