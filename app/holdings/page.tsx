import type { Metadata } from "next";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { getCorpus } from "@/lib/data/live";
import { fmtNum, fmtDate } from "@/lib/data";
import { Label, MetaTag } from "@/lib/components/ui/primitives";
import { SourceTag } from "@/lib/components/ui/SourceTag";
import { HoldingRow } from "@/lib/components/HoldingCard";

export const metadata: Metadata = {
  title: "Holdings index",
  description: "The permanent record of every holding created on HOLDING.",
};

export default async function HoldingsIndexPage() {
  const { holdings, live, network, stats } = await getCorpus();
  const rows = [...holdings].sort((a, b) => +new Date(b.finalityTs) - +new Date(a.finalityTs));

  return (
    <>
      <PageHeader
        eyebrow="Archive"
        title="Holdings index"
        lede="The permanent record. Each row is a finalised decision distilled into an issue, a set of material facts, a verdict and a ratio — citable by every panel that comes after it."
        meta={
          <div className="space-y-4 text-right">
            <div>
              <div className="display text-[34px] leading-none tabular-nums text-paper">
                {fmtNum(stats.holdingsIndexed)}
              </div>
              <div className="mt-2 flex items-center justify-end gap-2">
                <Label>Total holdings</Label>
                <SourceTag live={live} network={network} />
              </div>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {rows.length} shown · newest first
            </p>
          </div>
        }
      />

      <section className="shell py-12">
        <div className="grid grid-cols-12 gap-4 border-b border-white/[0.12] pb-3">
          <span className="label col-span-3 sm:col-span-2">Holding</span>
          <span className="label col-span-9 sm:col-span-4">Issue</span>
          <span className="label col-span-4 hidden sm:block">Domain</span>
          <span className="label col-span-1 hidden md:block">Decision</span>
          <span className="label col-span-2 hidden text-right md:block">Cited</span>
          <span className="label col-span-2 hidden text-right md:block">Finality</span>
        </div>

        <div className="mt-2">
          {rows.map((h) => (
            <HoldingRow key={h.id} holding={h} />
          ))}
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.08] pt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            {live && network ? `${network.mode} · ${rows.length} records · registry ${network.registry_address.slice(0, 10)}…` : "Demo environment · simulated records · not live GenLayer data"}
          </p>
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            Index v0.1 · {fmtDate(stats.lastIndexed)}
          </p>
        </div>
      </section>
    </>
  );
}
