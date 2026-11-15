"use client";
import { useState } from "react";
import type { Leaderboard as LB, Run } from "@/lib/data";

/* Chart roles (validated: blue/orange pass all-pairs CVD + contrast on #fff). Baselines use neutral ink, not a series hue. */
const C = {
  open: "#2a78d6",
  closed: "#eb6834",
  baseline: "#898781",
  ink: "#0b0b0b",
  ink2: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  seq: ["#f3f8fe", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"],
};
type Kind = "open" | "closed" | "baseline";

function seqColor(v: number) {
  const i = Math.max(0, Math.min(C.seq.length - 1, Math.round(v * (C.seq.length - 1))));
  return { fill: C.seq[i], text: i >= 4 ? "#ffffff" : C.ink };
}
const label = (r: Run) => (r.model === "none" ? r.harness.replace("baseline_", "") + " baseline" : `${r.model.split("/").pop()} · ${r.harness}`);
const pct = (v: number) => `${Math.round(v * 100)}%`;

type Tip = { x: number; y: number; lines: string[] } | null;
function Tooltip({ tip }: { tip: Tip }) {
  if (!tip) return null;
  return (
    <div className="vtip" style={{ left: tip.x + 12, top: tip.y + 12 }} role="status">
      {tip.lines.map((l, i) => <div key={i} className={i === 0 ? "vtip-h" : ""}>{l}</div>)}
    </div>
  );
}
function useTip() {
  const [tip, setTip] = useState<Tip>(null);
  const show = (e: React.MouseEvent, lines: string[]) => {
    const box = (e.currentTarget as Element).closest(".vbox")!.getBoundingClientRect();
    setTip({ x: e.clientX - box.left, y: e.clientY - box.top, lines });
  };
  return { tip, show, hide: () => setTip(null) };
}

function Legend({ kinds }: { kinds: Kind[] }) {
  const names: Record<Kind, string> = { open: "Open-weight model", closed: "Closed model", baseline: "Reference baseline (no LLM)" };
  return (
    <div className="vlegend">
      {kinds.map((k) => <span key={k}><i style={{ background: C[k] }} />{names[k]}</span>)}
    </div>
  );
}

/* 1. Ranked horizontal bars: primary accuracy on the selected suite */
export function RankingBars({ runs, kind, metricDef }: { runs: Run[]; kind: (m: string) => Kind; metricDef?: string }) {
  const { tip, show, hide } = useTip();
  const rows = [...runs].filter((r) => typeof r.primary_accuracy === "number").sort((a, b) => b.primary_accuracy - a.primary_accuracy);
  if (!rows.length) return null;
  const W = 600, labelW = 170, rowH = 30, barH = 18, padR = 48, top = 24;
  const H = top + rows.length * rowH + 28;
  const x = (v: number) => labelW + v * (W - labelW - padR);
  const kinds = Array.from(new Set(rows.map((r) => kind(r.model)))) as Kind[];
  return (
    <div className="vbox">
      <Legend kinds={kinds} />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Primary accuracy ranking">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => (
          <g key={t}>
            <line x1={x(t)} x2={x(t)} y1={top - 6} y2={H - 24} stroke={t === 0 ? C.axis : C.grid} strokeWidth={1} />
            <text x={x(t)} y={H - 8} fontSize={11} fill={C.muted} textAnchor="middle">{pct(t)}</text>
          </g>
        ))}
        {rows.map((r, i) => {
          const y = top + i * rowH, v = r.primary_accuracy, k = kind(r.model), w = Math.max(x(v) - x(0), 2);
          return (
            <g key={r.harness + r.model} onMouseMove={(e) => show(e, [label(r), `Primary accuracy ${pct(v)}`, `Cases ${r.n_cases} · k=${r.k}`, r.cost_per_correct_usd ? `$${r.cost_per_correct_usd.toFixed(4)} per correct` : "No API cost"])} onMouseLeave={hide}>
              <rect x={0} y={y} width={W} height={rowH} fill="transparent" />
              <text x={labelW - 10} y={y + rowH / 2 + 4} fontSize={12} fill={C.ink2} textAnchor="end">{label(r)}</text>
              <path d={`M${x(0)},${y + (rowH - barH) / 2} h${w - 4} a4,4 0 0 1 4,4 v${barH - 8} a4,4 0 0 1 -4,4 h-${w - 4} z`} fill={C[k]} />
              <text x={x(0) + w + 6} y={y + rowH / 2 + 4} fontSize={12} fill={C.ink} style={{ fontVariantNumeric: "tabular-nums" }}>{pct(v)}</text>
            </g>
          );
        })}
      </svg>
      {metricDef && <p className="vnote">{metricDef}</p>}
      <Tooltip tip={tip} />
    </div>
  );
}

/* 2. Overview heatmap: every agent × every suite */
export function SuiteHeatmap({ lb, split, keep }: { lb: LB; split: string; keep: (r: Run) => boolean }) {
  const { tip, show, hide } = useTip();
  const suites = Object.keys(lb.suites);
  const runs = lb.runs.filter((r) => r.split === split && !r.skipped && typeof r.primary_accuracy === "number" && keep(r));
  const agents = Array.from(new Map(runs.map((r) => [r.harness + "|" + r.model, r])).values());
  if (!agents.length) return null;
  const score = (a: Run, s: string) => runs.find((r) => r.suite === s && r.harness === a.harness && r.model === a.model)?.primary_accuracy as number | undefined;
  const mean = (a: Run) => { const v = suites.map((s) => score(a, s)).filter((x): x is number => x !== undefined); return v.reduce((p, c) => p + c, 0) / (v.length || 1); };
  agents.sort((a, b) => mean(b) - mean(a));
  const labelW = 160, cw = 88, ch = 32, top = 40, gap = 2;
  const W = labelW + suites.length * cw, H = top + agents.length * ch + 4;
  return (
    <div className="vbox">
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" style={{ maxWidth: W * 1.25 }} role="img" aria-label="Primary accuracy by agent and suite">
        {suites.map((s, j) => <text key={s} x={labelW + j * cw + cw / 2} y={top - 12} fontSize={11} fill={C.ink2} textAnchor="middle">{s.replace("_", " ")}</text>)}
        {agents.map((a, i) => (
          <g key={a.harness + a.model}>
            <text x={labelW - 10} y={top + i * ch + ch / 2 + 4} fontSize={12} fill={C.ink2} textAnchor="end">{label(a)}</text>
            {suites.map((s, j) => {
              const v = score(a, s);
              const cx = labelW + j * cw, cy = top + i * ch;
              if (v === undefined) return <rect key={s} x={cx + gap / 2} y={cy + gap / 2} width={cw - gap} height={ch - gap} rx={4} fill="#f5f5f4" />;
              const c = seqColor(v);
              return (
                <g key={s} onMouseMove={(e) => show(e, [label(a), `${s}: ${pct(v)}`])} onMouseLeave={hide}>
                  <rect x={cx + gap / 2} y={cy + gap / 2} width={cw - gap} height={ch - gap} rx={4} fill={c.fill} />
                  <text x={cx + cw / 2} y={cy + ch / 2 + 4} fontSize={12} fill={c.text} textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>{pct(v)}</text>
                </g>
              );
            })}
          </g>
        ))}
      </svg>
      <div className="vramp"><span>0%</span>{C.seq.map((s) => <i key={s} style={{ background: s }} />)}<span>100%</span></div>
      <Tooltip tip={tip} />
    </div>
  );
}

/* 3. Cost vs accuracy (log x). Only runs that actually spent money. */
export function CostAccuracy({ runs, kind, rosterSize }: { runs: Run[]; kind: (m: string) => Kind; rosterSize: number }) {
  const { tip, show, hide } = useTip();
  const pts = runs.filter((r) => r.cost_per_correct_usd > 0 && typeof r.primary_accuracy === "number");
  const W = 600, H = 300, L = 48, R = 16, T = 16, B = 40;
  if (!pts.length) {
    return (
      <div className="vempty">
        <svg viewBox={`0 0 600 160`} width="100%" aria-hidden>
          <line x1={L} x2={L} y1={10} y2={130} stroke={C.axis} /><line x1={L} x2={584} y1={130} y2={130} stroke={C.axis} />
          <text x={L - 8} y={16} fontSize={11} fill={C.muted} textAnchor="end">100%</text>
          <text x={584} y={150} fontSize={11} fill={C.muted} textAnchor="end">cost per correct decision (log $) →</text>
        </svg>
        <p>Waiting for the first model sweep. This chart plots accuracy against <b>cost per correct decision</b> for each of the {rosterSize} roster models once they've been run through OpenRouter. The reference baselines don't call an LLM, so they have no cost to plot.</p>
      </div>
    );
  }
  const costs = pts.map((p) => p.cost_per_correct_usd);
  const lo = Math.log10(Math.min(...costs)) - 0.2, hi = Math.log10(Math.max(...costs)) + 0.2;
  const x = (c: number) => L + ((Math.log10(c) - lo) / (hi - lo || 1)) * (W - L - R);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const ticks: number[] = []; for (let e = Math.floor(lo); e <= Math.ceil(hi); e++) ticks.push(10 ** e);
  const kinds = Array.from(new Set(pts.map((p) => kind(p.model)))) as Kind[];
  // Pareto frontier: cheapest-for-accuracy
  const frontier = [...pts].sort((a, b) => a.cost_per_correct_usd - b.cost_per_correct_usd).reduce<Run[]>((f, p) => (!f.length || p.primary_accuracy > f[f.length - 1].primary_accuracy ? [...f, p] : f), []);
  return (
    <div className="vbox">
      <Legend kinds={kinds} />
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" role="img" aria-label="Accuracy versus cost per correct decision">
        {[0, 0.25, 0.5, 0.75, 1].map((t) => <g key={t}><line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={t === 0 ? C.axis : C.grid} /><text x={L - 8} y={y(t) + 4} fontSize={11} fill={C.muted} textAnchor="end">{pct(t)}</text></g>)}
        {ticks.filter((t) => Math.log10(t) >= lo && Math.log10(t) <= hi).map((t) => <text key={t} x={x(t)} y={H - 18} fontSize={11} fill={C.muted} textAnchor="middle">${t < 0.01 ? t.toExponential(0) : t}</text>)}
        <text x={W - R} y={H - 2} fontSize={11} fill={C.muted} textAnchor="end">cost per correct decision (log scale) →</text>
        <polyline points={frontier.map((p) => `${x(p.cost_per_correct_usd)},${y(p.primary_accuracy)}`).join(" ")} fill="none" stroke={C.axis} strokeWidth={2} strokeDasharray="4 4" />
        {pts.map((p) => (
          <g key={p.harness + p.model} onMouseMove={(e) => show(e, [label(p), `Accuracy ${pct(p.primary_accuracy)}`, `$${p.cost_per_correct_usd.toFixed(4)} per correct`])} onMouseLeave={hide}>
            <circle cx={x(p.cost_per_correct_usd)} cy={y(p.primary_accuracy)} r={12} fill="transparent" />
            <circle cx={x(p.cost_per_correct_usd)} cy={y(p.primary_accuracy)} r={5} fill={C[kind(p.model)]} stroke="#fff" strokeWidth={2} />
          </g>
        ))}
        {frontier.map((p) => <text key={"l" + p.model + p.harness} x={x(p.cost_per_correct_usd) + 8} y={y(p.primary_accuracy) - 8} fontSize={11} fill={C.ink2}>{p.model.split("/").pop()}</text>)}
      </svg>
      <p className="vnote">Dashed line: the cost/accuracy frontier. Points on it are the cheapest way to reach that accuracy.</p>
      <Tooltip tip={tip} />
    </div>
  );
}

/* Hero: the classic benchmark-leaderboard chart. Vertical bars sorted by score, value on top,
   95% Wilson interval whiskers, open vs closed colour, roster models not yet run shown as pending slots. */
function wilson(p: number, n: number) {
  if (!n) return [p, p];
  const z = 1.96, d = 1 + (z * z) / n, c = p + (z * z) / (2 * n), m = z * Math.sqrt((p * (1 - p)) / n + (z * z) / (4 * n * n));
  return [Math.max(0, (c - m) / d), Math.min(1, (c + m) / d)];
}
export function HeroChart({ runs, kind, pending, title }: { runs: Run[]; kind: (m: string) => Kind; pending: { id: string; open: boolean }[]; title: string }) {
  const { tip, show, hide } = useTip();
  const rows = [...runs].filter((r) => typeof r.primary_accuracy === "number").sort((a, b) => b.primary_accuracy - a.primary_accuracy);
  const slots = rows.length + pending.length;
  if (!slots) return null;
  const L = 44, R = 12, T = 28, B = 150;
  const slotW = Math.max(34, Math.min(72, 900 / slots));
  const W = L + R + slots * slotW, H = 460;
  const bw = Math.min(40, slotW * 0.62);
  const y = (v: number) => T + (1 - v) * (H - T - B);
  const cx = (i: number) => L + i * slotW + slotW / 2;
  const name = (r: Run) => (r.model === "none" ? r.harness.replace("baseline_", "") + " baseline" : r.model.split("/").pop()!);
  const kinds = Array.from(new Set(rows.map((r) => kind(r.model)).concat(pending.map((p) => (p.open ? "open" : "closed") as Kind)))) as Kind[];
  return (
    <div className="vbox">
      <div className="hero-head">
        <div className="hero-title">{title}</div>
        <Legend kinds={kinds} />
      </div>
      <div className="hero-scroll">
        <svg viewBox={`0 0 ${W} ${H}`} style={{ minWidth: Math.min(W, 1100), width: "100%" }} role="img" aria-label={title}>
          {[0, 0.2, 0.4, 0.6, 0.8, 1].map((t) => (
            <g key={t}>
              <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} stroke={t === 0 ? C.axis : C.grid} />
              <text x={L - 8} y={y(t) + 4} fontSize={11} fill={C.muted} textAnchor="end" style={{ fontVariantNumeric: "tabular-nums" }}>{t * 100}</text>
            </g>
          ))}
          <text x={8} y={T - 12} fontSize={11} fill={C.muted}>% correct</text>
          {rows.map((r, i) => {
            const v = r.primary_accuracy, [lo, hi] = wilson(v, r.n_cases || 0), x = cx(i), top = y(v), base = y(0), h = Math.max(base - top, 1);
            return (
              <g key={r.harness + r.model} onMouseMove={(e) => show(e, [name(r), `${r.harness} harness`, `Primary accuracy ${(v * 100).toFixed(1)}%`, `95% CI ${(lo * 100).toFixed(0)}–${(hi * 100).toFixed(0)}% · n=${r.n_cases}`, r.cost_per_correct_usd ? `$${r.cost_per_correct_usd.toFixed(4)} per correct` : "No API cost"])} onMouseLeave={hide}>
                <rect x={x - slotW / 2} y={T} width={slotW} height={H - T - B} fill="transparent" />
                <path d={`M${x - bw / 2},${base} V${top + 4} a4,4 0 0 1 4,-4 H${x + bw / 2 - 4} a4,4 0 0 1 4,4 V${base} Z`} fill={C[kind(r.model)]} />
                <line x1={x} x2={x} y1={y(hi)} y2={y(lo)} stroke={C.ink} strokeWidth={1.5} opacity={0.55} />
                <line x1={x - 5} x2={x + 5} y1={y(hi)} y2={y(hi)} stroke={C.ink} strokeWidth={1.5} opacity={0.55} />
                <line x1={x - 5} x2={x + 5} y1={y(lo)} y2={y(lo)} stroke={C.ink} strokeWidth={1.5} opacity={0.55} />
                <text x={x} y={Math.min(top, y(hi)) - 6} fontSize={12} fontWeight={600} fill={C.ink} textAnchor="middle" style={{ fontVariantNumeric: "tabular-nums" }}>{(v * 100).toFixed(1)}</text>
                <text transform={`translate(${x + 4},${base + 12}) rotate(-50)`} fontSize={11.5} fill={C.ink2} textAnchor="end">{name(r)}</text>
              </g>
            );
          })}
          {pending.map((p, j) => {
            const i = rows.length + j, x = cx(i), base = y(0);
            return (
              <g key={p.id} onMouseMove={(e) => show(e, [p.id, "Queued: not run yet", "Appears after the first OpenRouter sweep"])} onMouseLeave={hide}>
                <rect x={x - slotW / 2} y={T} width={slotW} height={H - T - B} fill="transparent" />
                <rect x={x - bw / 2} y={base - 14} width={bw} height={14} rx={3} fill="none" stroke={p.open ? C.open : C.closed} strokeDasharray="3 3" opacity={0.7} />
                <text transform={`translate(${x + 4},${base + 12}) rotate(-50)`} fontSize={11.5} fill={C.muted} textAnchor="end">{p.id.split("/").pop()}</text>
              </g>
            );
          })}
        </svg>
      </div>
      <p className="vnote">Bars: share of cases fully correct. Whiskers: 95% Wilson confidence interval. Dashed stubs: roster models queued for the first sweep, not yet scored.</p>
      <Tooltip tip={tip} />
    </div>
  );
}
