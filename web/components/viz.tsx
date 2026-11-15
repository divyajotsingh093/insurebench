"use client";
import { useMemo, useState } from "react";
import type { Run } from "@/lib/data";

/* ---------- tokens ---------- */
export const C = {
  open: "#2a78d6", openHi: "#5598e7",
  closed: "#eb6834", closedHi: "#f08a5d",
  baseline: "#898781", baselineHi: "#a8a69f",
  ink: "#0b0b0b", ink2: "#52514e", muted: "#898781", grid: "#e1e0d9", axis: "#c3c2b7", panel: "#f6f5f1",
  seq: ["#f3f8fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
};
export type Kind = "open" | "closed" | "baseline";
export type Agent = { key: string; model: string; harness: string; name: string; vendor: string; kind: Kind; runs: Run[] };

/* ---------- metrics ---------- */
export type MetricKey = "primary_accuracy" | "cost_per_correct_usd" | "tokens_per_case" | "latency_s_mean" | "hallucination_rate" | "injection_resistance";
export const METRICS: Record<MetricKey, { label: string; short: string; better: "high" | "low"; fmt: (v: number) => string; unit01?: boolean }> = {
  primary_accuracy: { label: "Accuracy (cases fully correct)", short: "Accuracy", better: "high", fmt: (v) => (v * 100).toFixed(1) + "%", unit01: true },
  injection_resistance: { label: "Prompt-injection resistance", short: "Injection resist.", better: "high", fmt: (v) => (v * 100).toFixed(0) + "%", unit01: true },
  hallucination_rate: { label: "Hallucination rate (lower is better)", short: "Hallucination", better: "low", fmt: (v) => (v * 100).toFixed(1) + "%", unit01: true },
  cost_per_correct_usd: { label: "Cost per correct decision (USD)", short: "$ / correct", better: "low", fmt: (v) => (v >= 1 ? "$" + v.toFixed(2) : v >= 0.01 ? "$" + v.toFixed(3) : "$" + v.toPrecision(2)) },
  tokens_per_case: { label: "Tokens per case", short: "Tokens", better: "low", fmt: (v) => (v >= 1000 ? (v / 1000).toFixed(v >= 1e5 ? 0 : 1) + "k" : String(Math.round(v))) },
  latency_s_mean: { label: "Mean latency per case (s)", short: "Latency", better: "low", fmt: (v) => v.toFixed(1) + "s" },
};

/** Value of a metric for an agent on a suite ("overall" = case-weighted mean across suites that have it). */
export function value(a: Agent, m: MetricKey, suite: string): number | undefined {
  const rs = a.runs.filter((r) => (suite === "overall" || r.suite === suite) && typeof r[m] === "number");
  if (!rs.length) return undefined;
  const w = rs.reduce((s, r) => s + (r.n_cases || 1), 0);
  return rs.reduce((s, r) => s + r[m] * (r.n_cases || 1), 0) / w;
}
export function nCases(a: Agent, suite: string) {
  return a.runs.filter((r) => suite === "overall" || r.suite === suite).reduce((s, r) => s + (r.n_cases || 0), 0);
}
export function wilson(p: number, n: number): [number, number] {
  if (!n) return [p, p];
  const z = 1.96, d = 1 + (z * z) / n, c = p + (z * z) / (2 * n), m = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [Math.max(0, (c - m) / d), Math.min(1, (c + m) / d)];
}

/* ---------- scales ---------- */
export function scale(domain: [number, number], range: [number, number], log: boolean) {
  const [d0, d1] = log ? [Math.log10(domain[0]), Math.log10(domain[1])] : domain;
  const f = (v: number) => range[0] + (((log ? Math.log10(v) : v) - d0) / (d1 - d0 || 1)) * (range[1] - range[0]);
  const ticks = (): number[] => {
    if (log) {
      const out: number[] = [];
      for (let e = Math.floor(d0); e <= Math.ceil(d1); e++) for (const k of [1, 2, 5]) { const t = k * 10 ** e; if (t >= domain[0] * 0.999 && t <= domain[1] * 1.001) out.push(t); }
      return out.length > 7 ? out.filter((t) => Math.abs(Math.log10(t) % 1) < 1e-9) : out;
    }
    const span = domain[1] - domain[0], raw = span / 5, mag = 10 ** Math.floor(Math.log10(raw || 1));
    const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => span / s <= 6) ?? mag * 10;
    const out: number[] = []; for (let t = Math.ceil(domain[0] / step) * step; t <= domain[1] + 1e-9; t += step) out.push(+t.toFixed(10));
    return out;
  };
  return { f, ticks };
}
export function niceDomain(vals: number[], log: boolean, unit01?: boolean): [number, number] {
  const v = vals.filter((x) => (log ? x > 0 : Number.isFinite(x)));
  if (!v.length) return log ? [0.01, 1] : [0, 1];
  let lo = Math.min(...v), hi = Math.max(...v);
  if (log) return [10 ** Math.floor(Math.log10(lo) - 0.05), 10 ** Math.ceil(Math.log10(hi) + 0.05)];
  if (unit01) return [0, 1];
  return [0, hi * 1.12 || 1];
}

/* ---------- tooltip ---------- */
type Tip = { x: number; y: number; lines: string[] } | null;
export function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = (e: React.MouseEvent, lines: string[]) => {
    const box = (e.currentTarget as Element).closest(".vbox")!.getBoundingClientRect();
    const x = e.clientX - box.left, flip = x > box.width - 220;
    setTip({ x: flip ? x - 224 : x + 14, y: e.clientY - box.top + 14, lines });
  };
  return { tip, show, hide: () => setTip(null) };
}
export function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return <div className="vtip" style={{ left: tip.x, top: tip.y }} role="status">{tip.lines.map((l, i) => <div key={i} className={i === 0 ? "vtip-h" : ""}>{l}</div>)}</div>;
}

/* ---------- small UI ---------- */
export function Seg<T extends string>({ value: v, options, onChange, label }: { value: T; options: { v: T; l: string }[]; onChange: (v: T) => void; label?: string }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {options.map((o) => <button key={o.v} role="radio" aria-checked={o.v === v} onClick={() => onChange(o.v)}>{o.l}</button>)}
    </div>
  );
}
export function Monogram({ a, size = 22 }: { a: Agent; size?: number }) {
  const ch = a.kind === "baseline" ? "B" : (a.vendor || a.name)[0]?.toUpperCase();
  return (
    <g>
      <circle r={size / 2} fill="#fff" stroke={C.grid} />
      <text y={4} fontSize={11} fontWeight={700} fill={C[a.kind]} textAnchor="middle">{ch}</text>
    </g>
  );
}
export function KindLegend({ kinds }: { kinds: Kind[] }) {
  const names: Record<Kind, string> = { open: "Open-weight", closed: "Closed", baseline: "Reference baseline (no LLM)" };
  return <div className="vlegend">{kinds.map((k) => <span key={k}><i style={{ background: C[k] }} />{names[k]}</span>)}</div>;
}
export function Grad() {
  return (
    <defs>
      {(["open", "closed", "baseline"] as Kind[]).map((k) => (
        <linearGradient key={k} id={`g-${k}`} x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stopColor={C[(k + "Hi") as keyof typeof C] as string} />
          <stop offset="1" stopColor={C[k]} />
        </linearGradient>
      ))}
    </defs>
  );
}

/* =====================================================================
   1. BENCHMARK INDEX: Snorkel-style vertical ranking with metric / scale / sort controls
   ===================================================================== */
export function IndexChart({ agents, suite, suiteLabel, focus, setFocus }: { agents: Agent[]; suite: string; suiteLabel: string; focus: string | null; setFocus: (k: string | null) => void }) {
  const { tip, show, hide } = useTip();
  const [metric, setMetric] = useState<MetricKey>("primary_accuracy");
  const [log, setLog] = useState(false);
  const [sort, setSort] = useState<"score" | "name">("score");
  const M = METRICS[metric];
  const rows = useMemo(() => {
    const r = agents.map((a) => ({ a, v: value(a, metric, suite) })).filter((x): x is { a: Agent; v: number } => x.v !== undefined && (!log || x.v > 0));
    r.sort((p, q) => (sort === "name" ? p.a.name.localeCompare(q.a.name) : M.better === "high" ? q.v - p.v : p.v - q.v));
    return r;
  }, [agents, metric, suite, log, sort, M.better]);
  const hiddenZeros = log ? agents.filter((a) => value(a, metric, suite) === 0).length : 0;
  const metricsAvail = (Object.keys(METRICS) as MetricKey[]).filter((k) => agents.some((a) => (value(a, k, suite) ?? 0) > 0 || (k === "primary_accuracy" && value(a, k, suite) !== undefined)));

  const slot = rows.length ? Math.max(44, Math.min(78, 1000 / rows.length)) : 60;
  const L = 52, R = 16, T = 34, B = 108, H = 430;
  const W = L + R + rows.length * slot;
  const dom = niceDomain(rows.map((r) => r.v), log, M.unit01);
  const y = scale(dom, [H - B, T], log);
  const bw = Math.min(34, slot * 0.6);
  return (
    <div className="vbox panel">
      <div className="ix-head">
        <div>
          <div className="ix-title">{suiteLabel}</div>
          <div className="ix-sub">{M.label}{M.better === "low" ? " · shorter bar is better" : ""}</div>
        </div>
        <div className="ix-ctrls">
          <select value={metric} onChange={(e) => setMetric(e.target.value as MetricKey)} aria-label="Metric">
            {metricsAvail.map((k) => <option key={k} value={k}>{METRICS[k].short}</option>)}
          </select>
          <Seg label="Scale" value={log ? "log" : "lin"} onChange={(v) => setLog(v === "log")} options={[{ v: "lin", l: "Linear" }, { v: "log", l: "Log" }]} />
          <Seg label="Sort" value={sort} onChange={setSort} options={[{ v: "score", l: "Rank" }, { v: "name", l: "A–Z" }]} />
        </div>
      </div>
      {!rows.length ? <p className="muted pad">No values for this metric yet.</p> : (
        <div className="hscroll">
          <svg viewBox={`0 0 ${W} ${H}`} style={{ width: Math.max(W, 600), maxWidth: "none", minWidth: "100%" }} role="img" aria-label={`${suiteLabel} ranking by ${M.short}`}>
            <Grad />
            {y.ticks().map((t) => (
              <g key={t}>
                <line x1={L} x2={W - R} y1={y.f(t)} y2={y.f(t)} stroke={C.grid} strokeDasharray={t === dom[0] ? "" : "2 4"} />
                <text x={L - 10} y={y.f(t) + 4} fontSize={11} fill={C.muted} textAnchor="end" className="tnum">{M.fmt(t)}</text>
              </g>
            ))}
            {rows.map(({ a, v }, i) => {
              const cx = L + i * slot + slot / 2, top = y.f(v), base = y.f(dom[0]), h = Math.max(base - top, 2);
              const n = nCases(a, suite), ci = metric === "primary_accuracy" && n ? wilson(v, n) : null;
              const dim = focus && focus !== a.key;
              return (
                <g key={a.key} className="bar" opacity={dim ? 0.28 : 1} style={{ cursor: "pointer" }}
                  onClick={() => setFocus(focus === a.key ? null : a.key)}
                  onMouseMove={(e) => show(e, [a.name, `${a.harness} harness · ${a.kind}`, `${M.short}: ${M.fmt(v)}`, ...(ci ? [`95% CI ${M.fmt(ci[0])} – ${M.fmt(ci[1])}`, `n = ${n} cases`] : []), "Click to highlight everywhere"])} onMouseLeave={hide}>
                  <rect x={cx - slot / 2} y={T} width={slot} height={H - T - 20} fill="transparent" />
                  <rect x={cx - bw / 2} width={bw} rx={5} fill={`url(#g-${a.kind})`} style={{ y: top, height: h, transition: "y .45s cubic-bezier(.2,.8,.2,1), height .45s cubic-bezier(.2,.8,.2,1)" } as React.CSSProperties} />
                  {ci && <g stroke={C.ink} strokeOpacity={0.45} strokeWidth={1.25}><line x1={cx} x2={cx} y1={y.f(ci[1])} y2={y.f(ci[0])} /><line x1={cx - 4} x2={cx + 4} y1={y.f(ci[1])} y2={y.f(ci[1])} /><line x1={cx - 4} x2={cx + 4} y1={y.f(ci[0])} y2={y.f(ci[0])} /></g>}
                  <text x={cx} y={Math.min(top, ci ? y.f(ci[1]) : top) - 7} fontSize={11} fill={C.ink2} textAnchor="middle" className="tnum">{M.fmt(v)}</text>
                  <g transform={`translate(${cx},${base + 20})`}><Monogram a={a} /></g>
                  <text transform={`translate(${cx + 3},${base + 40}) rotate(-38)`} fontSize={11} fill={focus === a.key ? C.ink : C.ink2} fontWeight={focus === a.key ? 650 : 400} textAnchor="end">{a.name}</text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
      <div className="ix-foot">
        <KindLegend kinds={Array.from(new Set(rows.map((r) => r.a.kind)))} />
        <span className="muted small">{metric === "primary_accuracy" ? "Whiskers: 95% Wilson interval. " : ""}{hiddenZeros ? `${hiddenZeros} zero-valued agents hidden on log scale. ` : ""}Click a bar to highlight it in every chart.</span>
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* =====================================================================
   2. VALUE MAP: any metric vs any metric, per-axis log, Pareto frontier
   ===================================================================== */
type XKey = "cost_per_correct_usd" | "tokens_per_case" | "latency_s_mean" | "usd_in" | "usd_out";
const XDEF: Record<XKey, { label: string; fmt: (v: number) => string }> = {
  cost_per_correct_usd: { label: "Cost per correct decision", fmt: METRICS.cost_per_correct_usd.fmt },
  usd_in: { label: "List price, $ per 1M input tokens", fmt: (v) => "$" + (v < 1 ? v.toFixed(2) : v.toFixed(1)) },
  usd_out: { label: "List price, $ per 1M output tokens", fmt: (v) => "$" + (v < 1 ? v.toFixed(2) : v.toFixed(1)) },
  tokens_per_case: { label: "Tokens per case", fmt: METRICS.tokens_per_case.fmt },
  latency_s_mean: { label: "Mean latency per case", fmt: METRICS.latency_s_mean.fmt },
};
export function ValueMap({ agents, suite, prices, focus, setFocus }: { agents: Agent[]; suite: string; prices: Record<string, { in: number; out: number }>; focus: string | null; setFocus: (k: string | null) => void }) {
  const { tip, show, hide } = useTip();
  const [xk, setXk] = useState<XKey>("cost_per_correct_usd");
  const [yk, setYk] = useState<MetricKey>("primary_accuracy");
  const [xlog, setXlog] = useState(true);
  const [ylog, setYlog] = useState(false);
  const xv = (a: Agent) => (xk === "usd_in" ? prices[a.model]?.in : xk === "usd_out" ? prices[a.model]?.out : value(a, xk, suite));
  const pts = agents.map((a) => ({ a, x: xv(a), y: value(a, yk, suite) }))
    .filter((p): p is { a: Agent; x: number; y: number } => p.x !== undefined && p.y !== undefined && p.x > 0 && (!ylog || p.y > 0));
  const W = 860, H = 420, L = 64, R = 24, T = 20, B = 52;
  if (!pts.length) return (
    <div className="vbox panel"><div className="ix-title">Value map</div>
      <div className="vempty">Needs model runs with API cost. It plots accuracy against what it costs once the first OpenRouter sweep lands; baselines don't call an LLM, so they have nothing to plot.</div></div>
  );
  const xd = niceDomain(pts.map((p) => p.x), xlog), yd = niceDomain(pts.map((p) => p.y), ylog, METRICS[yk].unit01);
  const x = scale(xd, [L, W - R], xlog), y = scale(yd, [H - B, T], ylog);
  const hb = METRICS[yk].better === "high";
  const frontier = [...pts].sort((p, q) => p.x - q.x).reduce<typeof pts>((f, p) => (!f.length || (hb ? p.y > f[f.length - 1].y : p.y < f[f.length - 1].y) ? [...f, p] : f), []);
  const onF = new Set(frontier.map((p) => p.a.key));
  // greedy label placement: skip frontier labels that would collide with one already placed
  const placed: { x: number; y: number }[] = [];
  const labelled = new Set<string>();
  [...frontier].reverse().forEach((p) => {
    const px = x.f(p.x), py = y.f(p.y);
    if (placed.every((q) => Math.abs(q.x - px) > 95 || Math.abs(q.y - py) > 16)) { placed.push({ x: px, y: py }); labelled.add(p.a.key); }
  });
  return (
    <div className="vbox panel">
      <div className="ix-head">
        <div><div className="ix-title">Value map</div><div className="ix-sub">Which models give the most for the money. Up-and-left is better{METRICS[yk].better === "low" ? " (down-and-left for this metric)" : ""}.</div></div>
        <div className="ix-ctrls">
          <label className="ctl">Y <select value={yk} onChange={(e) => setYk(e.target.value as MetricKey)}>{(["primary_accuracy", "injection_resistance", "hallucination_rate"] as MetricKey[]).map((k) => <option key={k} value={k}>{METRICS[k].short}</option>)}</select></label>
          <Seg label="Y scale" value={ylog ? "log" : "lin"} onChange={(v) => setYlog(v === "log")} options={[{ v: "lin", l: "Lin" }, { v: "log", l: "Log" }]} />
          <label className="ctl">X <select value={xk} onChange={(e) => setXk(e.target.value as XKey)}>{(Object.keys(XDEF) as XKey[]).map((k) => <option key={k} value={k}>{XDEF[k].label.replace("List price, ", "")}</option>)}</select></label>
          <Seg label="X scale" value={xlog ? "log" : "lin"} onChange={(v) => setXlog(v === "log")} options={[{ v: "lin", l: "Lin" }, { v: "log", l: "Log" }]} />
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Value map scatter">
        {y.ticks().map((t) => <g key={"y" + t}><line x1={L} x2={W - R} y1={y.f(t)} y2={y.f(t)} stroke={C.grid} strokeDasharray="2 4" /><text x={L - 10} y={y.f(t) + 4} fontSize={11} fill={C.muted} textAnchor="end" className="tnum">{METRICS[yk].fmt(t)}</text></g>)}
        {x.ticks().map((t) => <g key={"x" + t}><line x1={x.f(t)} x2={x.f(t)} y1={T} y2={H - B} stroke={C.grid} strokeDasharray="2 4" /><text x={x.f(t)} y={H - B + 18} fontSize={11} fill={C.muted} textAnchor="middle" className="tnum">{XDEF[xk].fmt(t)}</text></g>)}
        <line x1={L} x2={W - R} y1={H - B} y2={H - B} stroke={C.axis} />
        <text x={(L + W - R) / 2} y={H - 10} fontSize={12} fill={C.ink2} textAnchor="middle">{XDEF[xk].label}{xlog ? " (log)" : ""}</text>
        <text transform={`translate(16,${(T + H - B) / 2}) rotate(-90)`} fontSize={12} fill={C.ink2} textAnchor="middle">{METRICS[yk].short}{ylog ? " (log)" : ""}</text>
        <path d={frontier.map((p, i) => `${i ? "L" : "M"}${x.f(p.x)},${y.f(p.y)}`).join("")} fill="none" stroke={C.ink} strokeOpacity={0.35} strokeWidth={1.5} strokeDasharray="5 4" />
        {pts.map((p) => {
          const dim = focus && focus !== p.a.key, me = focus === p.a.key;
          return (
            <g key={p.a.key} opacity={dim ? 0.22 : 1} style={{ cursor: "pointer", transition: "opacity .2s" }} onClick={() => setFocus(me ? null : p.a.key)}
              onMouseMove={(e) => show(e, [p.a.name, `${METRICS[yk].short}: ${METRICS[yk].fmt(p.y)}`, `${XDEF[xk].label}: ${XDEF[xk].fmt(p.x)}`, onF.has(p.a.key) ? "On the value frontier" : ""].filter(Boolean))} onMouseLeave={hide}>
              <circle cx={x.f(p.x)} cy={y.f(p.y)} r={14} fill="transparent" />
              <circle cx={x.f(p.x)} cy={y.f(p.y)} r={me ? 8 : onF.has(p.a.key) ? 6.5 : 5} fill={C[p.a.kind]} stroke="#fff" strokeWidth={2} style={{ transition: "cx .45s, cy .45s, r .2s" } as React.CSSProperties} />
              {(labelled.has(p.a.key) || me) && <text x={x.f(p.x) + 10} y={y.f(p.y) - 9} fontSize={11} fill={C.ink} fontWeight={me ? 650 : 500}>{p.a.name}</text>}
            </g>
          );
        })}
      </svg>
      <div className="ix-foot"><KindLegend kinds={Array.from(new Set(pts.map((p) => p.a.kind)))} /><span className="muted small">Dashed line: value frontier, the best score reachable at each price.</span></div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* =====================================================================
   3. HEAD-TO-HEAD: compare two agents across every suite (dumbbell)
   ===================================================================== */
export function HeadToHead({ agents, suites, suiteLabel }: { agents: Agent[]; suites: string[]; suiteLabel: (s: string) => string }) {
  const { tip, show, hide } = useTip();
  const ranked = [...agents].sort((p, q) => (value(q, "primary_accuracy", "overall") ?? 0) - (value(p, "primary_accuracy", "overall") ?? 0));
  const [ka, setKa] = useState(ranked[0]?.key ?? "");
  const [kb, setKb] = useState(ranked[1]?.key ?? "");
  const A = agents.find((a) => a.key === ka), B = agents.find((a) => a.key === kb);
  const W = 860, rowH = 44, L = 190, R = 70, T = 36;
  const H = T + suites.length * rowH + 30;
  const x = scale([0, 1], [L, W - R], false);
  const ca = "#2a78d6", cb = "#eb6834";
  return (
    <div className="vbox panel">
      <div className="ix-head">
        <div><div className="ix-title">Head-to-head</div><div className="ix-sub">Pick two agents to compare accuracy on every suite.</div></div>
        <div className="ix-ctrls">
          <label className="ctl"><i className="dot" style={{ background: ca }} /><select value={ka} onChange={(e) => setKa(e.target.value)}>{ranked.map((a) => <option key={a.key} value={a.key}>{a.name}</option>)}</select></label>
          <span className="muted">vs</span>
          <label className="ctl"><i className="dot" style={{ background: cb }} /><select value={kb} onChange={(e) => setKb(e.target.value)}>{ranked.map((a) => <option key={a.key} value={a.key}>{a.name}</option>)}</select></label>
        </div>
      </div>
      {A && B && (
        <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Head-to-head comparison">
          {[0, 0.25, 0.5, 0.75, 1].map((t) => <g key={t}><line x1={x.f(t)} x2={x.f(t)} y1={T - 10} y2={H - 26} stroke={C.grid} strokeDasharray="2 4" /><text x={x.f(t)} y={H - 8} fontSize={11} fill={C.muted} textAnchor="middle">{t * 100}%</text></g>)}
          {suites.map((s, i) => {
            const va = value(A, "primary_accuracy", s), vb = value(B, "primary_accuracy", s), cy = T + i * rowH + rowH / 2;
            const d = va !== undefined && vb !== undefined ? va - vb : undefined;
            return (
              <g key={s} onMouseMove={(e) => show(e, [suiteLabel(s), `${A.name}: ${va !== undefined ? METRICS.primary_accuracy.fmt(va) : "–"}`, `${B.name}: ${vb !== undefined ? METRICS.primary_accuracy.fmt(vb) : "–"}`, d !== undefined ? `Gap ${(d * 100).toFixed(1)} pts` : ""].filter(Boolean))} onMouseLeave={hide}>
                <rect x={0} y={cy - rowH / 2} width={W} height={rowH} fill={i % 2 ? "transparent" : "rgba(0,0,0,.018)"} />
                <text x={L - 14} y={cy + 4} fontSize={12.5} fill={C.ink2} textAnchor="end">{suiteLabel(s)}</text>
                {va !== undefined && vb !== undefined && <line x1={x.f(va)} x2={x.f(vb)} y1={cy} y2={cy} stroke={C.axis} strokeWidth={3} strokeLinecap="round" />}
                {va !== undefined && <circle cx={x.f(va)} cy={cy} r={7} fill={ca} stroke="#fff" strokeWidth={2} style={{ transition: "cx .45s" } as React.CSSProperties} />}
                {vb !== undefined && <circle cx={x.f(vb)} cy={cy} r={7} fill={cb} stroke="#fff" strokeWidth={2} style={{ transition: "cx .45s" } as React.CSSProperties} />}
                {d !== undefined && <text x={W - R + 12} y={cy + 4} fontSize={12} fontWeight={600} fill={Math.abs(d) < 0.005 ? C.muted : d > 0 ? ca : cb} className="tnum">{d > 0 ? "+" : ""}{(d * 100).toFixed(1)}</text>}
              </g>
            );
          })}
        </svg>
      )}
      <div className="ix-foot"><span className="muted small">Right column: gap in percentage points (positive favours the blue agent).</span></div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* =====================================================================
   4. BENCHMARK CARDS: one card per eval suite with its top 3 (Snorkel hub style)
   ===================================================================== */
export function BenchCards({ agents, suites, meta, active, onPick }: { agents: Agent[]; suites: string[]; meta: Record<string, { label: string; blurb: string; kind: string; source: string }>; active: string; onPick: (s: string) => void }) {
  return (
    <div className="bench-grid">
      {suites.map((s) => {
        const top = agents.map((a) => ({ a, v: value(a, "primary_accuracy", s) })).filter((x): x is { a: Agent; v: number } => x.v !== undefined).sort((p, q) => q.v - p.v).slice(0, 3);
        return (
          <button key={s} className={`bench ${active === s ? "on" : ""}`} onClick={() => onPick(s)}>
            <div className="bench-k">{meta[s]?.kind}</div>
            <div className="bench-t">{meta[s]?.label ?? s}</div>
            <div className="bench-d">{meta[s]?.blurb}</div>
            <ol>{top.map(({ a, v }, i) => <li key={a.key}><span className="rk">{i + 1}</span><i style={{ background: C[a.kind] }} />{a.name}<b className="tnum">{(v * 100).toFixed(1)}%</b></li>)}</ol>
            <div className="bench-s">{meta[s]?.source}</div>
          </button>
        );
      })}
    </div>
  );
}

/* =====================================================================
   5. SUITE HEATMAP: every agent × every suite
   ===================================================================== */
export function Heatmap({ agents, suites, suiteLabel, focus, setFocus }: { agents: Agent[]; suites: string[]; suiteLabel: (s: string) => string; focus: string | null; setFocus: (k: string | null) => void }) {
  const { tip, show, hide } = useTip();
  const rows = [...agents].sort((p, q) => (value(q, "primary_accuracy", "overall") ?? 0) - (value(p, "primary_accuracy", "overall") ?? 0));
  const labelW = 170, cw = 104, ch = 26, top = 34, gap = 2;
  const W = labelW + (suites.length + 1) * cw, H = top + rows.length * ch + 4;
  const cols = ["overall", ...suites];
  return (
    <div className="vbox panel">
      <div className="ix-head"><div><div className="ix-title">Every agent, every suite</div><div className="ix-sub">Accuracy, darker is better. Sorted by overall.</div></div></div>
      <div className="hscroll">
        <svg viewBox={`0 0 ${W} ${H}`} style={{ width: "100%", minWidth: 640, maxWidth: W * 1.1 }} role="img" aria-label="Accuracy heatmap">
          {cols.map((s, j) => <text key={s} x={labelW + j * cw + cw / 2} y={top - 12} fontSize={11} fontWeight={s === "overall" ? 650 : 400} fill={C.ink2} textAnchor="middle">{s === "overall" ? "Overall" : suiteLabel(s)}</text>)}
          {rows.map((a, i) => (
            <g key={a.key} opacity={focus && focus !== a.key ? 0.3 : 1} style={{ cursor: "pointer" }} onClick={() => setFocus(focus === a.key ? null : a.key)}>
              <text x={labelW - 10} y={top + i * ch + ch / 2 + 4} fontSize={11.5} fill={C.ink2} textAnchor="end" fontWeight={focus === a.key ? 650 : 400}>{a.name}</text>
              {cols.map((s, j) => {
                const v = value(a, "primary_accuracy", s), cx = labelW + j * cw, cy = top + i * ch;
                if (v === undefined) return <rect key={s} x={cx + gap / 2} y={cy + gap / 2} width={cw - gap} height={ch - gap} rx={4} fill="#f2f1ed" />;
                const k = Math.max(0, Math.min(7, Math.round(v * 7)));
                return (
                  <g key={s} onMouseMove={(e) => show(e, [a.name, `${s === "overall" ? "Overall" : suiteLabel(s)}: ${(v * 100).toFixed(1)}%`])} onMouseLeave={hide}>
                    <rect x={cx + gap / 2} y={cy + gap / 2} width={cw - gap} height={ch - gap} rx={4} fill={C.seq[k]} />
                    <text x={cx + cw / 2} y={cy + ch / 2 + 4} fontSize={11} fill={k >= 4 ? "#fff" : C.ink} textAnchor="middle" className="tnum">{(v * 100).toFixed(0)}</text>
                  </g>
                );
              })}
            </g>
          ))}
        </svg>
      </div>
      <div className="vramp"><span>0%</span>{C.seq.map((s) => <i key={s} style={{ background: s }} />)}<span>100%</span></div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* =====================================================================
   6. HARNESS WORKBENCH: same models, different agent harnesses
   ===================================================================== */
const HARNESS_LABEL: Record<string, string> = {
  react_raw: "Plain ReAct", langgraph_react: "LangGraph", openai_agents_sdk: "OpenAI Agents SDK", claude_agent_sdk: "Claude Agent SDK", neutrinos: "Neutrinos",
};
export const harnessLabel = (h: string) => HARNESS_LABEL[h] ?? h;
const DIV = { neg: ["#e34948", "#ef8a89", "#f7c4c3"], mid: "#f0efec", pos: ["#cde2fb", "#6da7ec", "#2a78d6"] };
function divColor(d: number) {
  const a = Math.abs(d), i = a < 0.015 ? -1 : a < 0.04 ? 2 : a < 0.08 ? 1 : 0;
  if (i < 0) return { fill: DIV.mid, text: C.ink };
  return d > 0 ? { fill: DIV.pos[2 - i], text: i === 0 ? "#fff" : C.ink } : { fill: DIV.neg[i], text: i === 0 ? "#fff" : C.ink };
}
export function HarnessBench({ agents, suite, suiteLabel }: { agents: Agent[]; suite: string; suiteLabel: string }) {
  const { tip, show, hide } = useTip();
  const llm = agents.filter((a) => a.kind !== "baseline");
  const harnesses = Array.from(new Set(llm.map((a) => a.harness))).sort((p, q) => (p === "react_raw" ? -1 : q === "react_raw" ? 1 : p.localeCompare(q)));
  const byModel = new Map<string, Map<string, Agent>>();
  llm.forEach((a) => { if (!byModel.has(a.model)) byModel.set(a.model, new Map()); byModel.get(a.model)!.set(a.harness, a); });
  const models = Array.from(byModel.keys()).filter((m) => byModel.get(m)!.size > 1);
  if (harnesses.length < 2 || !models.length) {
    return <div className="vbox panel"><div className="ix-title">Harness workbench</div><div className="vempty">Needs at least one model run through two or more harnesses (Plain ReAct, LangGraph, OpenAI Agents SDK, Claude Agent SDK, Neutrinos).</div></div>;
  }
  // (a) harness ranking: mean lift vs Plain ReAct over models that ran on both (paired, so it's a fair comparison)
  const lift = harnesses.map((h) => {
    const ds = models.map((m) => { const b = byModel.get(m)!.get("react_raw"), x = byModel.get(m)!.get(h); const vb = b && value(b, "primary_accuracy", suite), vx = x && value(x, "primary_accuracy", suite); return vb !== undefined && vx !== undefined ? vx - vb : undefined; }).filter((d): d is number => d !== undefined);
    const accs = models.map((m) => byModel.get(m)!.get(h)).filter(Boolean).map((a) => value(a!, "primary_accuracy", suite)).filter((v): v is number => v !== undefined);
    return { h, mean: ds.length ? ds.reduce((s, d) => s + d, 0) / ds.length : 0, n: ds.length, acc: accs.length ? accs.reduce((s, v) => s + v, 0) / accs.length : 0, wins: ds.filter((d) => d > 0.005).length };
  }).sort((p, q) => q.mean - p.mean);
  const W1 = 860, rowH = 40, L1 = 170, R1 = 120, T1 = 18, H1 = T1 + lift.length * rowH + 26;
  const ext = Math.max(0.05, ...lift.map((l) => Math.abs(l.mean))) * 1.25;
  const x1 = scale([-ext, ext], [L1, W1 - R1], false);
  // (b) per-model lift grid
  const labelW = 170, cw = 120, ch = 28, top = 34;
  const W2 = labelW + harnesses.length * cw, H2 = top + models.length * ch + 4;
  return (
    <div className="vbox panel">
      <div className="ix-head">
        <div><div className="ix-title">Harness workbench · {suiteLabel}</div><div className="ix-sub">Same models, different agent harnesses. How much does the scaffolding add or take away compared with Plain ReAct?</div></div>
      </div>
      <svg viewBox={`0 0 ${W1} ${H1}`} width="100%" role="img" aria-label="Average lift by harness">
        {x1.ticks().map((t) => <g key={t}><line x1={x1.f(t)} x2={x1.f(t)} y1={T1 - 6} y2={H1 - 22} stroke={t === 0 ? C.axis : C.grid} strokeDasharray={t === 0 ? "" : "2 4"} /><text x={x1.f(t)} y={H1 - 6} fontSize={11} fill={C.muted} textAnchor="middle" className="tnum">{t > 0 ? "+" : ""}{(t * 100).toFixed(0)} pts</text></g>)}
        {lift.map((l, i) => {
          const cy = T1 + i * rowH + rowH / 2, x0 = x1.f(0), xv = x1.f(l.mean), base = l.h === "react_raw";
          const col = base ? C.baseline : l.mean >= 0 ? C.open : "#e34948";
          return (
            <g key={l.h} onMouseMove={(e) => show(e, [harnessLabel(l.h), base ? "Reference harness" : `Mean lift ${(l.mean * 100 >= 0 ? "+" : "") + (l.mean * 100).toFixed(1)} pts vs Plain ReAct`, `Mean accuracy ${(l.acc * 100).toFixed(1)}%`, base ? "" : `Beats Plain ReAct on ${l.wins} of ${l.n} models`].filter(Boolean))} onMouseLeave={hide}>
              <rect x={0} y={cy - rowH / 2} width={W1} height={rowH} fill="transparent" />
              <text x={L1 - 14} y={cy + 4} fontSize={13} fill={C.ink} fontWeight={l.h === "neutrinos" ? 650 : 400} textAnchor="end">{harnessLabel(l.h)}</text>
              {base ? <circle cx={x0} cy={cy} r={5} fill={C.baseline} /> :
                <rect x={Math.min(x0, xv)} y={cy - 9} width={Math.max(Math.abs(xv - x0), 2)} height={18} rx={4} fill={col} style={{ transition: "all .45s" }} />}
              <text x={W1 - R1 + 14} y={cy + 4} fontSize={12} fill={C.ink2} className="tnum">{base ? "baseline" : `${l.mean >= 0 ? "+" : ""}${(l.mean * 100).toFixed(1)} · ${l.wins}/${l.n} wins`}</text>
            </g>
          );
        })}
      </svg>
      <div className="hscroll" style={{ marginTop: 10 }}>
        <svg viewBox={`0 0 ${W2} ${H2}`} style={{ width: "100%", minWidth: 600, maxWidth: W2 * 1.1 }} role="img" aria-label="Per-model harness lift">
          {harnesses.map((h, j) => <text key={h} x={labelW + j * cw + cw / 2} y={top - 12} fontSize={11.5} fill={C.ink2} fontWeight={h === "neutrinos" ? 650 : 400} textAnchor="middle">{harnessLabel(h)}</text>)}
          {models.map((m, i) => {
            const base = byModel.get(m)!.get("react_raw"), vb = base && value(base, "primary_accuracy", suite);
            return (
              <g key={m}>
                <text x={labelW - 10} y={top + i * ch + ch / 2 + 4} fontSize={11.5} fill={C.ink2} textAnchor="end">{m.split("/").pop()}</text>
                {harnesses.map((h, j) => {
                  const a = byModel.get(m)!.get(h), v = a && value(a, "primary_accuracy", suite), cx = labelW + j * cw, cy = top + i * ch;
                  if (v === undefined) return <rect key={h} x={cx + 1} y={cy + 1} width={cw - 2} height={ch - 2} rx={4} fill="#f6f5f1" stroke="#ecebe6" strokeDasharray="3 3" />;
                  const d = h === "react_raw" || vb === undefined ? 0 : v - vb, c = h === "react_raw" ? { fill: "#fff", text: C.ink } : divColor(d);
                  return (
                    <g key={h} onMouseMove={(e) => show(e, [`${m.split("/").pop()} · ${harnessLabel(h)}`, `Accuracy ${(v * 100).toFixed(1)}%`, h === "react_raw" ? "Reference" : `${d >= 0 ? "+" : ""}${(d * 100).toFixed(1)} pts vs Plain ReAct`])} onMouseLeave={hide}>
                      <rect x={cx + 1} y={cy + 1} width={cw - 2} height={ch - 2} rx={4} fill={c.fill} stroke={h === "react_raw" ? C.grid : "none"} />
                      <text x={cx + cw / 2} y={cy + ch / 2 + 4} fontSize={11} fill={c.text} textAnchor="middle" className="tnum">{h === "react_raw" ? `${(v * 100).toFixed(0)}%` : `${d >= 0 ? "+" : ""}${(d * 100).toFixed(0)}`}</text>
                    </g>
                  );
                })}
              </g>
            );
          })}
        </svg>
      </div>
      <div className="ix-foot">
        <div className="vramp"><span>worse</span>{[...DIV.neg, DIV.mid, ...DIV.pos].map((c) => <i key={c} style={{ background: c }} />)}<span>better than Plain ReAct</span></div>
        <span className="muted small">Grid: Plain ReAct column shows accuracy; other columns show the change in points. Dashed cells: not run (the Claude Agent SDK only runs Anthropic models).</span>
      </div>
      <Tooltip tip={tip} />
    </div>
  );
}
