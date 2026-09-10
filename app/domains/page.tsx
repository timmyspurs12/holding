import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { getCorpus } from "@/lib/data/live";
import { fmtNum } from "@/lib/data";
import { Label, Rule } from "@/lib/components/ui/primitives";
import { SourceTag } from "@/lib/components/ui/SourceTag";

export const metadata: Metadata = {
  title: "Domains",
  description: "Consistency, volume and the leading issue in every domain HOLDING indexes.",
};

export default async function DomainsPage() {
  const { domains: DOMAINS, live, network, stats: CORPUS } = await getCorpus();
  const avg = Math.round(DOMAINS.reduce((a, d) => a + d.consistency, 0) / DOMAINS.length);

  return (
    <>
      <PageHeader
        eyebrow="Domains"
        title="How consistently is each domain being adjudicated?"
        lede="Consistency is the share of comparable cases that followed established precedent. A low score is not a failure — it marks the areas where the law is still being argued out, which is exactly where the record is most valuable."
        meta={
          <div className="space-y-4 text-right">
            <div>
              <div className="display text-[34px] leading-none tabular-nums text-paper">
                {avg}%
              </div>
              <div className="mt-2 flex items-center justify-end gap-2">
                <Label>Mean consistency</Label>
                <SourceTag live={live} network={network} />
              </div>
            </div>
            <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {DOMAINS.length} domains · {fmtNum(CORPUS.holdingsIndexed)} holdings
            </p>
          </div>
        }
      />

      <section className="shell py-14">
        <div className="grid gap-px overflow-hidden rounded-[10px] border border-white/[0.08] bg-white/[0.06] md:grid-cols-2">
          {DOMAINS.map((d) => (
            <div
              key={d.slug}
              id={d.slug}
              className="scroll-mt-24 bg-obsidian p-7 transition-colors hover:bg-ink"
            >
              <div className="flex items-start justify-between gap-6">
                <div>
                  <h2 className="text-[17px] leading-[1.3] text-paper">{d.name}</h2>
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                    {fmtNum(d.holdings)} holdings · {d.velocity}
                  </p>
                </div>
                <div className="text-right">
                  <div className="display text-[30px] leading-none tabular-nums text-paper">
                    {d.consistency}
                    <span className="text-[16px] text-muted">%</span>
                  </div>
                  <p className="mt-1 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                    consistency
                  </p>
                </div>
              </div>

              {/* split meter */}
              <div className="mt-6 flex h-[6px] w-full gap-[2px]">
                {Array.from({ length: 32 }).map((_, i) => (
                  <span
                    key={i}
                    className={
                      i < Math.round((d.consistency / 100) * 32)
                        ? "flex-1 bg-verdict/80"
                        : "flex-1 bg-dissent/60"
                    }
                  />
                ))}
              </div>

              <div className="mt-4 flex items-center gap-6">
                <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-stone">
                  <span className="h-[5px] w-[5px] rounded-[1px] bg-verdict" />
                  Followed {d.followed}%
                </span>
                <span className="flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.12em] text-stone">
                  <span className="h-[5px] w-[5px] rotate-45 bg-dissent" />
                  Distinguished {d.distinguished}%
                </span>
              </div>

              <Rule className="my-6" />

              <div className="flex items-end justify-between gap-6">
                <div>
                  <Label>Leading issue</Label>
                  <p className="mt-2 max-w-[34ch] text-[13px] leading-[1.55] text-stone">
                    {d.leadingIssue}
                  </p>
                </div>
                <Link
                  href={`/reporter?domain=${d.slug}`}
                  className="shrink-0 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone transition-colors hover:text-copper"
                >
                  Reporter →
                </Link>
              </div>
            </div>
          ))}
        </div>

        <div className="mt-12 flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.08] pt-6">
          <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            Demo environment · simulated figures
          </p>
          <Link
            href="/reporter"
            className="inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
          >
            Search all domains
            <ArrowRight size={11} strokeWidth={1.5} />
          </Link>
        </div>
      </section>
    </>
  );
}
