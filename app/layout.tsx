import type { Metadata } from "next";
import { Instrument_Serif, IBM_Plex_Mono } from "next/font/google";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import { Nav } from "@/lib/components/site/Nav";
import { Footer } from "@/lib/components/site/Footer";

const display = Instrument_Serif({
  subsets: ["latin"],
  weight: "400",
  variable: "--font-display",
  display: "swap",
});

const mono = IBM_Plex_Mono({
  subsets: ["latin"],
  weight: ["400", "500"],
  variable: "--font-mono",
  display: "swap",
});

export const metadata: Metadata = {
  title: {
    default: "HOLDING — the precedent layer for GenLayer",
    template: "%s · HOLDING",
  },
  description:
    "HOLDING turns finalized GenLayer decisions into searchable, citable authority for the decisions that come next.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${GeistSans.variable} ${display.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-obsidian font-sans antialiased">
        <div className="border-b border-white/[0.06] bg-ink">
          <div className="shell flex h-[26px] items-center justify-between">
            <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
              <span className="mr-2 inline-block h-[4px] w-[4px] translate-y-[-1px] rounded-full bg-copper align-middle" />
              Demo environment · simulated records
            </p>
            <p className="hidden font-mono text-[9px] uppercase tracking-[0.18em] text-muted sm:block">
              GenLayer testnet · precedent index v0.1
            </p>
          </div>
        </div>

        <Nav />
        <main>{children}</main>
        <Footer />
      </body>
    </html>
  );
}
