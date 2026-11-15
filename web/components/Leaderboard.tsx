"use client";
import { useMemo, useState } from "react";
import type { Leaderboard as LB, Run } from "@/lib/data";
import { HeroChart, SuiteHeatmap, CostAccuracy } from "@/components/Charts";

const HIDE = new Set(["track", "harness", "model", "suite", "split", "judge", "status_counts", "generated_at", "stopped", "note", "skipped", "skip_reason", "n_cases", "k"]);

function Cell({ v }: { v: unknown }) {
  if (v === null || v === undefined) return <td className="na">-</td>;
  if (typeof v === "number") return <td>{Math.abs(v) < 10 ? v.toFixed(3) : v.toFixed(1)}</td>;
  return <td>{String(v)}</td>;
}

export default function Leaderboard({ lb }: { lb: LB }) {
  const suites = Object.keys(lb.suites);
  const [suite, setSuite] = useState(suites[0]);
  const [filter, setFilter] = useState("all");
  const splits = useMemo(() => Array.from(new Set(lb.runs.map((r) => r.split))), [lb]);
  const [split, setSplit] = useState(splits.includes("dev") ? "dev" : splits[0]);
  const roster = useMemo(() => Object.fromEntries(lb.roster.models.map((m) => [m.id, m])), [lb]);
  const kind = (m: string): "open" | "closed" | "baseline" => (m === "none" ? "baseline" : roster[m.replace("openrouter/", "")]?.open_weights ? "open" : "closed");
  const runs: Run[] = lb.runs.filter((r) => r.suite === suite && r.split === split && !r.skipped && (filter === "all" || kind(r.model) === filter));
  const models = Array.from(new Set(runs.map((r) => r.model)));
  const harnesses = Array.from(new Set(runs.map((r) => r.harness)));
  const keys = Array.from(new Set(runs.flatMap((r) => Object.keys(r)))).filter((k) => !HIDE.has(k) && runs.some((r) => typeof r[k] === "number"));
  const trace = lb.sample_traces[lb.suites[suite].track];
  return (
    <>
      <div className="tabs" role="tablist">
        {suites.map((s) => <button key={s} role="tab" aria-selected={s === suite} onClick={() => setSuite(s)}>{s}</button>)}
      </div>
      <p className="muted">{lb.suites[suite].description} <span className="pill">{lb.suites[suite].kind}</span></p>
      <div className="controls">
        <label>Models <select value={filter} onChange={(e) => setFilter(e.target.value)}>
          <option value="all">all</option><option value="open">open-weight</option><option value="closed">closed</option><option value="baseline">baselines</option></select></label>
        <label>Split <select value={split} onChange={(e) => setSplit(e.target.value)}>{splits.map((s) => <option key={s}>{s}</option>)}</select></label>
      </div>
      <div className="card hero">
        <HeroChart title={`${suite.replace("_", " ")} · primary accuracy (${split} split)`} runs={runs} kind={kind}
          pending={filter === "baseline" ? [] : lb.roster.models.filter((m) => (filter === "all" || kind(m.id) === filter) && !runs.some((r) => r.model.replace("openrouter/", "") === m.id)).map((m) => ({ id: m.id, open: m.open_weights }))} />
      </div>
      <div className="card">
        <h2>Overview: primary accuracy on every suite</h2>
        <p className="muted">Each row is one agent (a model run through a harness). Darker means more cases right. Split: {split}.</p>
        <SuiteHeatmap lb={lb} split={split} keep={(r) => !r.skipped && (filter === "all" || kind(r.model) === filter)} />
      </div>
      <div className="card">
        <h2>Accuracy vs cost: {suite}</h2>
        <CostAccuracy runs={runs} kind={kind} rosterSize={lb.roster.models.length} />
      </div>
      <div className="card">
        <h2>Primary accuracy: model &times; harness</h2>
        {runs.length === 0 ? <p className="muted">No runs for this suite, split and filter yet. Roster models appear once a sweep has run with an OpenRouter key.</p> : (
          <table><thead><tr><th>model</th>{harnesses.map((h) => <th key={h}>{h}</th>)}</tr></thead>
            <tbody>{models.map((m) => <tr key={m}><td>{m}<span className="pill">{kind(m)}</span></td>
              {harnesses.map((h) => <Cell key={h} v={runs.find((r) => r.model === m && r.harness === h)?.primary_accuracy} />)}</tr>)}</tbody></table>)}
      </div>
      {runs.length > 0 && (
        <div className="card">
          <h2>All metrics</h2>
          <table><thead><tr><th>run</th>{keys.map((k) => <th key={k} title={lb.metric_defs[k] || ""}>{k}</th>)}</tr></thead>
            <tbody>{runs.map((r) => <tr key={r.harness + r.model}><td>{r.harness} &times; {r.model}</td>{keys.map((k) => <Cell key={k} v={r[k]} />)}</tr>)}</tbody></table>
        </div>)}
      <div className="card">
        <h2>Sample trace (dev split)</h2>
        {!trace ? <p className="muted">No trace.</p> : (<>
          <p className="muted">{trace.case_id} &middot; {trace.harness} &times; {trace.model} &middot; {trace.events.length} tool calls &middot; {trace.status}</p>
          {trace.events.map((e: any, i: number) => (
            <div key={i} className={`ev ${e.ok ? "" : "bad"}`}><b className="mono">{e.tool}</b> <span className="muted mono">{JSON.stringify(e.args).slice(0, 240)}</span>
              <pre>{String(e.ok ? e.result : e.error).slice(0, 1200)}</pre></div>))}
          <h2>Submission</h2><pre>{JSON.stringify(trace.submission, null, 1)}</pre>
        </>)}
      </div>
      <div className="card">
        <h2>Model roster ({lb.roster.models.length})</h2>
        <p className="muted">{lb.roster.selection_basis} (retrieved {lb.roster.retrieved}).</p>
        <table><thead><tr><th>id</th><th>weights</th><th>context</th><th>$/1M in</th><th>$/1M out</th><th>why</th></tr></thead>
          <tbody>{lb.roster.models.filter((m) => filter === "all" || filter === "baseline" || kind(m.id) === filter).map((m) => (
            <tr key={m.id}><td className="mono">{m.id}</td><td>{m.open_weights ? "open" : "closed"}</td><td>{m.context_length?.toLocaleString()}</td>
              <td>{m.usd_per_1m_input}</td><td>{m.usd_per_1m_output}</td><td className="wrap">{m.why}</td></tr>))}</tbody></table>
      </div>
    </>
  );
}
