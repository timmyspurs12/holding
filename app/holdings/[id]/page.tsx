import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight } from "lucide-react";
import { getCorpus } from "@/lib/data/live";
import { HOLDINGS, fmtDate, fmtTime } from "@/lib/data";
import { Label, Rule, VerdictTag, AuthorityTag, AppealTag, Meter, DataRow, MetaTag, cx } from "@/lib/components/ui/primitives";
import { EvidenceList } from "@/lib/components/EvidenceList";
import { CitationGraph } from "@/lib/components/CitationGraph";
import { StaggerList, FadeIn } from "@/lib/components/StaggerList";

export function generateStaticParams() {
  return HOLDINGS.map((h) => ({ id: h.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const { holdings } = await getCorpus();
  const h = holdings.find((x) => x.id === id);
  return {
    title: h ? `Holding #${h.id}` : "Holding not found",
    description: h?.issue,
  };
}

export default async function HoldingDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { holdings, live, network } = await getCorpus();
  const lookup = (holdingId: string) => holdings.find((h) => h.id === holdingId);

  const holding = lookup(id);
  if (!holding) notFound();

  const idx = holdings.findIndex((h) => h.id === holding.id);
  const prev = holdings[idx - 1];
  const next = holdings[idx + 1];

  const considered = holding.derivedFrom.map(lookup).filter(Boolean);
  const citedBy = holding.citedBy.map(lookup).filter(Boolean);
  const distinguishes = holding.distinguishes.map(lookup).filter(Boolean);
  const distinguishedBy = holdings.filter((h) => h.distinguishes.includes(holding.id));

  const bd = holding.authorityBreakdown;

  return (
    <>
      {/* ---------- header ---------- */}
      <header className="border-b border-white/[0.08]">
        <div className="shell py-10 md:py-14">
          <Link
            href="/holdings"
            className="inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone transition-colors hover:text-copper"
          >
            <ArrowLeft size={11} strokeWidth={1.5} />
            Holdings index
          </Link>

          <div className="mt-8 grid gap-8 md:grid-cols-12">
            <div className="md:col-span-8">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-copper">
                  Holding #{holding.id}
                </span>
                <MetaTag tone="green">Final</MetaTag>
                <AuthorityTag authority={holding.authority} />
              </div>

              <h1 className="display mt-6 max-w-[24ch] text-[34px] leading-[1.1] text-paper md:text-[52px]">
                {holding.issueLong}
              </h1>

              <div className="mt-8 flex flex-wrap items-center gap-x-8 gap-y-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  {holding.domain}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  {holding.contractClass}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  Panel of {holding.panelSize}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  Finality {fmtDate(holding.finalityTs)} · {fmtTime(holding.finalityTs)} UTC
                </span>
              </div>
            </div>

            <div className="md:col-span-4 md:justify-self-end">
              <div className="w-full md:w-[240px]">
                <Label>Verdict</Label>
                <div className="mt-3">
                  <VerdictTag verdict={holding.verdict} size="lg" />
                </div>
                <div className="mt-6">
                  <DataRow k="Appeal">
                    <AppealTag status={holding.appeal} />
                  </DataRow>
                  <DataRow k="Citations">{String(holding.citations).padStart(2, "0")}</DataRow>
                  <DataRow k="Distinguished">
                    {String(holding.distinguishedBy).padStart(2, "0")}
                  </DataRow>
                  <DataRow k="On-chain">
                    <span className="font-mono text-[12px] text-paper">{holding.onChainRef}</span>
                  </DataRow>
                </div>
              </div>
            </div>
          </div>
        </div>
      </header>

      {/* mobile sticky verdict state */}
      <div className="sticky top-[58px] z-30 border-b border-white/[0.08] bg-obsidian/95 backdrop-blur-[10px] md:hidden">
        <div className="shell flex h-[46px] items-center justify-between">
          <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-paper">
            Holding #{holding.id}
          </span>
          <VerdictTag verdict={holding.verdict} />
        </div>
      </div>

      {/* ---------- body ---------- */}
      <div className="shell grid gap-16 py-16 md:grid-cols-12 md:gap-12 md:py-20">
        <div className="md:col-span-8">
          {/* FACTS */}
          <section>
            <Label>Facts</Label>
            <div className="mt-6">
              <StaggerList
                items={holding.facts.map((f) => (
                  <div key={f} className="flex gap-4">
                    <span className="mt-[9px] h-px w-4 shrink-0 bg-white/20" />
                    <p className="text-[14px] leading-[1.65] text-stone">{f}</p>
                  </div>
                ))}
              />
            </div>
          </section>

          <Rule className="my-14" />

          {/* RATIO */}
          <section>
            <Label>Ratio</Label>
            <p className="display mt-6 max-w-[58ch] text-[22px] leading-[1.45] text-paper md:text-[28px]">
              {holding.ratio}
            </p>
            <p className="mt-6 text-[13px] leading-[1.7] text-muted">
              The ratio is the binding part of the holding. A later panel may reach a different
              outcome, but it has to answer this sentence first.
            </p>
          </section>

          <Rule className="my-14" />

          {/* EVIDENCE */}
          <section>
            <Label>Evidence</Label>
            <div className="mt-2">
              <EvidenceList items={holding.evidence} />
            </div>
          </section>

          <Rule className="my-14" />

          {/* PRECEDENT CONSIDERED */}
          <section>
            <Label>Precedent considered</Label>
            {considered.length ? (
              <div className="mt-6">
                {considered.map((h) => (
                  <Link
                    key={h!.id}
                    href={`/holdings/${h!.id}`}
                    className="group flex items-center justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                  >
                    <div className="min-w-0">
                      <span className="inline-block py-[3px] font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                        #{h!.id}
                      </span>
                      <p className="mt-1 text-[13.5px] text-stone">{h!.issue}</p>
                    </div>
                    <VerdictTag verdict={h!.verdict} />
                  </Link>
                ))}
              </div>
            ) : (
              <p className="mt-6 text-[13.5px] leading-[1.7] text-stone">
                No prior holding was available to this panel — the index was empty for this issue
                when it was decided. Holdings like this one are how the record starts.
              </p>
            )}
          </section>

          {/* DISTINGUISHES */}
          {distinguishes.length ? (
            <>
              <Rule className="my-14" />
              <section>
                <Label>Distinguishes</Label>
                <div className="mt-6">
                  {distinguishes.map((h) => (
                    <Link
                      key={h!.id}
                      href={`/holdings/${h!.id}`}
                      className="group flex items-center justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                    >
                      <div className="min-w-0">
                        <span className="inline-block py-[3px] font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                          #{h!.id}
                        </span>
                        <p className="mt-1 text-[13.5px] text-stone">{h!.issue}</p>
                      </div>
                      <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-dissent">
                        Distinguished
                      </span>
                    </Link>
                  ))}
                </div>
              </section>
            </>
          ) : null}

          <Rule className="my-14" />

          {/* CITATION MAP */}
          <section>
            <Label>Citation map</Label>
            <div className="mt-6">
              <CitationGraph rootId={holding.id} />
            </div>
          </section>

          <Rule className="my-14" />

          {/* CITED BY */}
          <section>
            <Label>Cited by</Label>
            {citedBy.length ? (
              <div className="mt-6">
                {citedBy.map((h) => (
                  <Link
                    key={h!.id}
                    href={`/holdings/${h!.id}`}
                    className="group flex items-center justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                  >
                    <div className="min-w-0">
                      <span className="inline-block py-[3px] font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                        #{h!.id}
                      </span>
                      <p className="mt-1 text-[13.5px] text-stone">{h!.issue}</p>
                    </div>
                    <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-info">
                      Followed
                    </span>
                  </Link>
                ))}
              </div>
            ) : (
              <p className="mt-6 text-[13.5px] leading-[1.7] text-stone">
                No later holding has cited this one yet.
              </p>
            )}
          </section>

          {/* DISTINGUISHED BY */}
          {distinguishedBy.length ? (
            <>
              <Rule className="my-14" />
              <section>
                <Label>Distinguished by</Label>
                <div className="mt-6">
                  {distinguishedBy.map((h) => (
                    <Link
                      key={h.id}
                      href={`/holdings/${h.id}`}
                      className="group flex items-start justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                    >
                      <div className="min-w-0">
                        <span className="inline-block py-[3px] font-mono text-[11px] tracking-[0.1em] text-paper group-hover:text-copper">
                          #{h.id}
                        </span>
                        <p className="mt-1 max-w-[56ch] text-[13px] leading-[1.6] text-stone">
                          {h.ratio}
                        </p>
                      </div>
                      <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-dissent">
                        Departed
                      </span>
                    </Link>
                  ))}
                </div>
              </section>
            </>
          ) : null}
        </div>

        {/* ---------- sidebar ---------- */}
        <aside className="md:col-span-4">
          <div className="md:sticky md:top-[80px]">
            <div className="panel rounded-[10px] p-6">
              <Label>Authority</Label>
              <div className="mt-6 space-y-6">
                <Meter label="Finality" value={bd.finality} />
                <Meter label="Appeal" value={bd.appeal} />
                <Meter label="Citations" value={bd.citations} />
                <Meter label="Consistency" value={bd.consistency} />
              </div>
              <p className="mt-7 text-[12.5px] leading-[1.65] text-muted">
                Authority is weighted, not declared. It rises with appeal survival, panel size and
                citation, and falls where later panels depart from the holding on the record.
              </p>
              <p className="mt-4 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                Demo metrics
              </p>
            </div>

            <div className="mt-6">
              <Label>Reason codes</Label>
              <div className="mt-4 flex flex-wrap gap-2">
                {holding.reasonCodes.map((c) => (
                  <MetaTag key={c}>{c}</MetaTag>
                ))}
              </div>
            </div>

            <div className="mt-8">
              <Label>Origin case</Label>
              <Link
                href={`/cases/${holding.originCase}`}
                className="group mt-4 flex items-center justify-between border-b border-white/[0.08] pb-3 text-[13.5px] text-paper transition-colors hover:text-copper"
              >
                Case #{holding.originCase}
                <ArrowRight size={12} strokeWidth={1.5} />
              </Link>
            </div>
          </div>
        </aside>
      </div>

      {/* ---------- prev / next ---------- */}
      <div className="border-t border-white/[0.08]">
        <div className="shell grid gap-px sm:grid-cols-2">
          {prev ? (
            <Link href={`/holdings/${prev.id}`} className="group py-8 pr-6">
              <Label>Newer</Label>
              <p className="mt-3 font-mono text-[13px] text-paper group-hover:text-copper">
                #{prev.id}
              </p>
              <p className="mt-2 max-w-[38ch] text-[13px] text-stone">{prev.issue}</p>
            </Link>
          ) : (
            <div />
          )}
          {next ? (
            <Link href={`/holdings/${next.id}`} className="group py-8 sm:pl-6 sm:text-right">
              <Label>Older</Label>
              <p className="mt-3 font-mono text-[13px] text-paper group-hover:text-copper">
                #{next.id}
              </p>
              <p className="ml-auto mt-2 max-w-[38ch] text-[13px] text-stone">{next.issue}</p>
            </Link>
          ) : null}
        </div>
      </div>
    </>
  );
}
