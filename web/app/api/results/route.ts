import { getLeaderboard } from "@/lib/data";

export const revalidate = 300;

export async function GET() {
  const lb = await getLeaderboard();
  return Response.json(lb, { headers: { "cache-control": "s-maxage=300, stale-while-revalidate=600" } });
}
