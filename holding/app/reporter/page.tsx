import type { Metadata } from "next";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { ReporterExplorer } from "@/lib/components/ReporterExplorer";
import { getCorpus } from "@/lib/data/live";
import { fmtNum, fmtDate } from "@/lib/data";
import { Label, MetaTag } from "@/lib/components/ui/primitives";
import { SourceTag } from "@/lib/components/ui/SourceTag";
import Link from "next/link";
import { Suspense } from "react";

export const metadata: Metadata = {
  title: "Reporter",
  description: "Search the decisions shaping future decisions.",
};

export default async function ReporterPage() {
  const { holdings: HOLDINGS, live, network, stats: CORPUS } = await getCorpus();
  const mostDistinguished = [...HOLDINGS].sort((a, b) => b.distinguishedBy - a.distinguishedBy).slice(0, 4);
  const mostCited = [...HOLDINGS].sort((a, b) => b.citations - a.citations).slice(0, 4);

  return (
    <>
      <PageHeader
        eyebrow="Reporter"
        title="Search the decisions shaping future decisions."
        lede="Every holding in the index, with its authority, its appeal history and the line of cases it belongs to. Retrieval is deterministic and runs inside GenVM, so the set you see is the set a panel would see."
        meta={
          <div className="space-y-4 text-right">
            <div>
              <div className="display text-[34px] leading-none tabular-nums text-paper">
                {fmtNum(CORPUS.holdingsIndexed)}
              </div>
              <div className="mt-2 flex items-center justify-end gap-2">
                <Label>Holdings indexed</Label>
                <SourceTag live={live} network={network} />
              </div>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              Last indexed {fmtDate(CORPUS.lastIndexed)}
            </p>
          </div>
        }
      />

      <section className="shell py-14 md:py-16">
        <Suspense fallback={<ExplorerSkeleton />}>
          <ReporterExplorer />
        </Suspense>
      </section>

      <section className="border-t border-white/[0.08]">
        <div className="shell grid gap-12 py-16 md:grid-cols-2 md:gap-16">
          <div>
            <Label>Most cited</Label>
            <div className="mt-6">
              {mostCited.map((h) => (
                <Link
                  key={h.id}
                  href={`/holdings/${h.id}`}
                  className="group flex items-center justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                >
                  <div className="min-w-0">
                    <span className="font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                      #{h.id}
                    </span>
                    <p className="mt-1 line-clamp-2 text-[13.5px] leading-[1.45] text-stone">{h.issue}</p>
                  </div>
                  <span className="shrink-0 font-mono text-[13px] tabular-nums text-copper">
                    {String(h.citations).padStart(2, "0")}
                  </span>
                </Link>
              ))}
            </div>
          </div>

          <div>
            <Label>Most distinguished</Label>
            <div className="mt-6">
              {mostDistinguished.map((h) => (
                <Link
                  key={h.id}
                  href={`/holdings/${h.id}`}
                  className="group flex items-center justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                >
                  <div className="min-w-0">
                    <span className="font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                      #{h.id}
                    </span>
                    <p className="mt-1 line-clamp-2 text-[13.5px] leading-[1.45] text-stone">{h.issue}</p>
                  </div>
                  <span className="shrink-0 font-mono text-[13px] tabular-nums text-dissent">
                    {String(h.distinguishedBy).padStart(2, "0")}
                  </span>
                </Link>
              ))}
            </div>
            <p className="mt-6 text-[13px] leading-[1.65] text-muted">
              A holding that is distinguished often is not failing — it is where the law is
              currently being argued about.
            </p>
          </div>
        </div>
      </section>
    </>
  );
}

function ExplorerSkeleton() {
  return (
    <div>
      <div className="h-[44px] border-b border-white/[0.12]" />
      <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {[0, 1, 2, 3, 4, 5].map((i) => (
          <div key={i} className="h-[210px] animate-pulseSoft rounded-[9px] border border-white/[0.06] bg-ink" />
        ))}
      </div>
    </div>
  );
}
