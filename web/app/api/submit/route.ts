import devIds from "@/data/dev_case_ids.json";

export const runtime = "nodejs";
const MAX_BYTES = 5 * 1024 * 1024;
const TRACKS = ["uw", "claims", "appeals", "coding", "coverage_qa"] as const;
const REQUIRED: Record<string, string[]> = {
  uw: ["decision", "table_class", "rate_class", "required_evidence", "exclusions", "offered_sum_assured", "refer", "cited_rules", "rationale"],
  claims: ["decision", "payable_amount", "deductions", "missing_documents", "fraud_flags", "letter"],
  appeals: ["determination", "rationale"],
  coding: ["invalid_codes", "non_billable_codes"],
  coverage_qa: ["answer", "clause_id"],
};

/**
 * POST /api/submit  (body: JSONL; one trace per line, the format written to results/runs/<run>/traces.jsonl)
 * Query: ?name=<submission name>&harness=<harness>&model=<model>
 * Only DEV-split case ids are accepted; the test split is scored by maintainers with private gold.
 */
export async function POST(req: Request) {
  const url = new URL(req.url);
  const name = (url.searchParams.get("name") || "").replace(/[^A-Za-z0-9._-]/g, "_").slice(0, 80);
  if (!name) return Response.json({ error: "query parameter 'name' is required" }, { status: 400 });
  const body = await req.text();
  if (body.length > MAX_BYTES) return Response.json({ error: "payload too large (5 MB max)" }, { status: 413 });
  const ids = devIds as Record<string, string[]>;
  const errors: string[] = [];
  const lines = body.split("\n").filter((l) => l.trim());
  if (!lines.length) errors.push("empty body");
  lines.forEach((line, i) => {
    let row: any;
    try { row = JSON.parse(line); } catch { errors.push(`line ${i + 1}: invalid JSON`); return; }
    if (!TRACKS.includes(row.track)) { errors.push(`line ${i + 1}: unknown track '${row.track}'`); return; }
    if (!(ids[row.track] || []).includes(row.case_id)) errors.push(`line ${i + 1}: '${row.case_id}' is not a dev-split ${row.track} case`);
    const sub = row.submission;
    if (sub !== null && typeof sub !== "object") errors.push(`line ${i + 1}: submission must be an object or null`);
    if (sub) for (const k of REQUIRED[row.track]) if (!(k in sub)) errors.push(`line ${i + 1}: submission missing '${k}'`);
    if (!Array.isArray(row.events)) errors.push(`line ${i + 1}: events (tool-call trace) must be an array`);
  });
  if (errors.length) return Response.json({ ok: false, errors: errors.slice(0, 50) }, { status: 422 });
  if (!process.env.BLOB_READ_WRITE_TOKEN) {
    return Response.json({ ok: true, stored: false, rows: lines.length, note: "valid; storage disabled (BLOB_READ_WRITE_TOKEN not set)" }, { status: 202 });
  }
  const { put } = await import("@vercel/blob");
  const key = `submissions/${new Date().toISOString().replace(/[:.]/g, "-")}-${name}.jsonl`;
  const blob = await put(key, body, { access: "private", contentType: "application/x-ndjson", addRandomSuffix: true });
  return Response.json({ ok: true, stored: true, rows: lines.length, key: blob.pathname });
}
