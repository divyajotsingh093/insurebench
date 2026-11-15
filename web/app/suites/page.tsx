import { getLeaderboard } from "@/lib/data";

export default async function Suites() {
  const lb = await getLeaderboard();
  return (
    <main>
      <h1>Suites and sources</h1>
      <div className="card">
        <table>
          <thead><tr><th>suite</th><th>track</th><th>kind</th><th>source</th><th>license</th><th>description</th></tr></thead>
          <tbody>
            {Object.entries(lb.suites).map(([k, s]) => (
              <tr key={k}><td className="mono">{k}</td><td>{s.track}</td><td>{s.kind}</td><td className="wrap">{s.source}</td><td className="wrap">{s.license}</td><td className="wrap">{s.description}</td></tr>
            ))}
          </tbody>
        </table>
        <p className="muted">Each suite has a data card in <code>data/cards/</code> (source, license, URL, retrieval date, preprocessing, known biases).</p>
      </div>
    </main>
  );
}
