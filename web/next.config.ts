import type { NextConfig } from "next";

// The app only imports files under web/ (web/data/*.json written by `python -m insurebench report`).
// Hidden test gold lives in ../data/gold_hidden (gitignored) and is never imported; scripts/check-bundle.mjs
// fails the build if anything gold-like appears in web/data.
const config: NextConfig = {};

export default config;
