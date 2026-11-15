import "./globals.css";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = {
  title: "InsureBench leaderboard",
  description: "Open benchmark for AI agents on life & health underwriting, claims adjudication, appeals and coding. Models x harnesses.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <nav>
            <Link href="/" className="brand">InsureBench</Link>
            <Link href="/">Leaderboard</Link>
            <Link href="/suites">Suites</Link>
            <Link href="/methodology">Methodology</Link>
            <a href="https://github.com/divyajotsingh093/insurebench">GitHub</a>
          </nav>
          {children}
          <footer>Synthetic suites use a fictional carrier (Meridian Mutual). Real-data suites cite their sources and licenses on the Suites page. Code Apache-2.0, data CC-BY-4.0 unless a source license says otherwise.</footer>
        </div>
      </body>
    </html>
  );
}
