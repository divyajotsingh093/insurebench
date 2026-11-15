// Upload results/leaderboard.json to Vercel Blob (key results/leaderboard.json). Used by .github/workflows/sweep.yml.
// Requires BLOB_READ_WRITE_TOKEN. Run from web/:  node scripts/upload-blob.mjs ../results/leaderboard.json
import { put } from "@vercel/blob";
import { readFileSync } from "node:fs";

const file = process.argv[2] || "../results/leaderboard.json";
if (!process.env.BLOB_READ_WRITE_TOKEN) { console.error("BLOB_READ_WRITE_TOKEN not set"); process.exit(1); }
const body = readFileSync(file, "utf8");
if (/gold_hidden/.test(body)) { console.error("refusing to upload: references hidden gold"); process.exit(1); }
const r = await put("results/leaderboard.json", body, { access: "public", contentType: "application/json", allowOverwrite: true, addRandomSuffix: false });
console.log("uploaded", r.url);
