import type { Metadata } from "next";
import { Instrument_Serif, IBM_Plex_Mono } from "next/font/google";
import { GeistSans } from "geist/font/sans";
import "./globals.css";
import { Nav } from "@/lib/components/site/Nav";
import { Footer } from "@/lib/components/site/Footer";
import { getCorpus } from "@/lib/data/live";
import { WalletProvider } from "@/lib/wallet/WalletProvider";

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

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const { network, live } = await getCorpus();
  const simulated = network?.simulated ?? true;
  const mode = network?.mode ?? "DEMO";

  return (
    <html lang="en" className={`${GeistSans.variable} ${display.variable} ${mono.variable}`}>
      <body className="min-h-screen bg-obsidian font-sans antialiased">
        <div className="border-b border-white/[0.06] bg-ink">
          <div className="shell flex h-[26px] items-center justify-between">
            <p className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
              <span className="mr-2 inline-block h-[4px] w-[4px] translate-y-[-1px] rounded-full bg-copper align-middle" />
              {simulated ? "Demo environment · simulated records" : `${mode} · live contract records`}
            </p>
            <p className="hidden font-mono text-[9px] uppercase tracking-[0.18em] text-muted sm:block">
              {live ? `GenLayer ${network?.network ?? mode}` : "GenLayer · not connected"} · precedent index v0.1
            </p>
          </div>
        </div>

        <WalletProvider>
          <Nav network={network} />
          <main>{children}</main>
          <Footer />
        </WalletProvider>
      </body>
    </html>
  );
}
