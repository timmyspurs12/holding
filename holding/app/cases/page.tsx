import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { getCorpus } from "@/lib/data/live";
import { fmtNum } from "@/lib/data";
import { Label, VerdictTag, MetaTag } from "@/lib/components/ui/primitives";
import { SourceTag } from "@/lib/components/ui/SourceTag";

export const metadata: Metadata = {
  title: "Cases",
  description: "Every case that came before a panel, and what the panel did with the precedent it found.",
};

export default async function CasesPage() {
  const { cases, live, network, stats } = await getCorpus();
  const rows = [...cases].sort((a, b) => +new Date(b.submitted) - +new Date(a.submitted));

  return (
    <>
      <PageHeader
        eyebrow="Cases"
        title="What the panel did with the precedent it found."
        lede="A case is the live event; a holding is what survives it. Open any case to see which holdings were retrieved, how each validator voted, and whether the panel followed the record or wrote a distinguishment."
        meta={
          <div className="space-y-4 text-right">
            <div>
              <div className="display text-[34px] leading-none tabular-nums text-paper">
                {fmtNum(stats.casesProcessed)}
              </div>
              <div className="mt-2 flex items-center justify-end gap-2">
                <Label>Cases processed</Label>
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
          <span className="label col-span-2">Case</span>
          <span className="label col-span-4">Issue</span>
          <span className="label col-span-2 hidden sm:block">Domain</span>
          <span className="label col-span-2 hidden md:block">Consensus</span>
          <span className="label col-span-2 hidden text-right md:block">Result</span>
        </div>

        <div className="mt-2">
          {rows.map((c) => (
            <Link
              key={c.id}
              href={`/cases/${c.id}`}
              className="group grid grid-cols-12 items-center gap-4 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
            >
              <span className="col-span-2 font-mono text-[12px] tracking-[0.1em] text-paper group-hover:text-copper">
                #{c.id}
              </span>
              <span className="col-span-4 text-[13.5px] leading-[1.45] text-stone">{c.issue}</span>
              <span className="col-span-2 hidden text-[12px] text-muted sm:block">{c.domain}</span>
              <span className="col-span-2 hidden font-mono text-[11px] tabular-nums text-stone md:block">
                {c.consensus}
              </span>
              <span className="col-span-2 flex justify-end md:block">
                {c.status === "PENDING" ? (
                  <MetaTag tone="copper">Pending</MetaTag>
                ) : c.verdict ? (
                  <VerdictTag verdict={c.verdict} />
                ) : null}
              </span>
            </Link>
          ))}
        </div>

        <p className="mt-10 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Demo environment · simulated records · not live GenLayer data
        </p>
      </section>
    </>
  );
}
