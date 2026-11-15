import bundled from "@/data/leaderboard.json";

export type Run = Record<string, any> & { track: string; suite: string; harness: string; model: string; split: string };
export type Leaderboard = {
  generated_at: string;
  suites: Record<string, { track: string; kind: string; source: string; license: string; description: string; card: string }>;
  roster: { models: { id: string; open_weights: boolean; context_length: number; usd_per_1m_input: number; usd_per_1m_output: number; why: string; vendor: string }[]; retrieved?: string; selection_basis?: string };
  runs: Run[];
  metric_defs: Record<string, string>;
  sample_traces: Record<string, any>;
  source?: string;
};

/** Results come from Vercel Blob when BLOB_READ_WRITE_TOKEN is set (key results/leaderboard.json, written by the
 *  sweep workflow), otherwise from the JSON bundled in the repo. Zero env vars required to build and deploy. */
export async function getLeaderboard(): Promise<Leaderboard> {
  if (process.env.BLOB_READ_WRITE_TOKEN) {
    try {
      const { list } = await import("@vercel/blob");
      const { blobs } = await list({ prefix: "results/leaderboard.json", limit: 1 });
      if (blobs[0]) {
        const r = await fetch(blobs[0].url, { next: { revalidate: 300 } });
        if (r.ok) return { ...(await r.json()), source: "vercel-blob" };
      }
    } catch (e) {
      console.error("blob read failed, using bundled results", e);
    }
  }
  return { ...(bundled as unknown as Leaderboard), source: "bundled" };
}
