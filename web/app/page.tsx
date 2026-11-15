import Leaderboard from "@/components/Leaderboard";
import { getLeaderboard } from "@/lib/data";

export const revalidate = 300;

export default async function Page() {
  const lb = await getLeaderboard();
  return (
    <main>
      <h1>Leaderboard</h1>
      <p className="sub">Models &times; harnesses on each suite. Every metric is its own column; there is no blended score. Results source: {lb.source}, generated {lb.generated_at}.</p>
      <Leaderboard lb={lb} />
    </main>
  );
}
