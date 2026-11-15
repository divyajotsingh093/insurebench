// Fails the build if anything that looks like hidden test gold is in the web bundle inputs.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

const dir = new URL("../data/", import.meta.url).pathname;
const allowed = new Set(["leaderboard.json", "dev_case_ids.json", "README.md", "demo.json"]);
let bad = [];
for (const f of readdirSync(dir)) {
  if (!allowed.has(f)) bad.push(`unexpected file web/data/${f}`);
  const txt = readFileSync(join(dir, f), "utf8");
  if (/gold_hidden|"split":\s*"test"[^}]*"gold"/.test(txt)) bad.push(`web/data/${f} references hidden test gold`);
}
if (bad.length) { console.error(bad.join("\n")); process.exit(1); }
console.log("bundle check OK: no hidden gold in web/data");
