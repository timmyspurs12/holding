import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { ArrowLeft, ArrowRight, Scale } from "lucide-react";
import { getCorpus } from "@/lib/data/live";
import { CASES, getCase, fmtDate, fmtTime } from "@/lib/data";
import { Label, Rule, VerdictTag, MetaTag, DataRow, cx } from "@/lib/components/ui/primitives";
import { PanelReview } from "@/lib/components/PanelReview";
import { CaseCompare } from "@/lib/components/CaseCompare";
import { StaggerList } from "@/lib/components/StaggerList";

export function generateStaticParams() {
  return CASES.map((c) => ({ id: c.id }));
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const c = getCase(id);
  return { title: c ? `Case #${c.id}` : "Case not found", description: c?.issue };
}

export default async function CaseDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const { cases, holdings, live, network } = await getCorpus();
  const lookup = (holdingId: string) => holdings.find((h) => h.id === holdingId);

  const record = cases.find((c) => c.id === id);
  if (!record) notFound();

  const nearest = record.retrieved[0] ? lookup(record.retrieved[0].holdingId) : undefined;
  const resulting = record.resultingHolding ? lookup(record.resultingHolding) : undefined;

  return (
    <>
      <header className="border-b border-white/[0.08]">
        <div className="shell py-10 md:py-14">
          <Link
            href="/cases"
            className="inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone transition-colors hover:text-copper"
          >
            <ArrowLeft size={11} strokeWidth={1.5} />
            All cases
          </Link>

          <div className="mt-8 grid gap-8 md:grid-cols-12">
            <div className="md:col-span-8">
              <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.16em] text-copper">
                  Case #{record.id}
                </span>
                <MetaTag tone={record.status === "PENDING" ? "copper" : "green"}>
                  {record.status}
                </MetaTag>
              </div>
              <h1 className="display mt-6 max-w-[26ch] text-[32px] leading-[1.12] text-paper md:text-[46px]">
                {record.issue}
              </h1>
              <div className="mt-8 flex flex-wrap items-center gap-x-8 gap-y-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  {record.domain}
                </span>
                <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                  Submitted {fmtDate(record.submitted)} · {fmtTime(record.submitted)} UTC
                </span>
              </div>
            </div>

            <div className="md:col-span-4 md:justify-self-end">
              <div className="w-full md:w-[240px]">
                <Label>Verdict</Label>
                <div className="mt-3">
                  {record.verdict ? (
                    <VerdictTag verdict={record.verdict} size="lg" />
                  ) : (
                    <span className="font-mono text-[13px] uppercase tracking-[0.12em] text-stone">
                      Awaiting consensus
                    </span>
                  )}
                </div>
                <div className="mt-6">
                  <DataRow k="Consensus">{record.consensus}</DataRow>
                  <DataRow k="Retrieved">
                    {record.retrieved.length
                      ? `${record.retrieved.length} holdings`
                      : "No precedent available"}
                  </DataRow>
                  <DataRow k="On-chain">
                    <span className="font-mono text-[12px] text-paper">{record.onChainRef}</span>
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
            Case #{record.id}
          </span>
          {record.verdict ? (
            <VerdictTag verdict={record.verdict} />
          ) : (
            <MetaTag tone="copper">Pending</MetaTag>
          )}
        </div>
      </div>

      <div className="shell grid gap-16 py-16 md:grid-cols-12 md:gap-12 md:py-20">
        <div className="md:col-span-8">
          {/* FACTS */}
          <section>
            <Label>Material facts</Label>
            <div className="mt-6">
              <StaggerList
                items={record.facts.map((f) => (
                  <div key={f} className="flex gap-4">
                    <span className="mt-[9px] h-px w-4 shrink-0 bg-white/20" />
                    <p className="text-[14px] leading-[1.65] text-stone">{f}</p>
                  </div>
                ))}
              />
            </div>
          </section>

          <Rule className="my-14" />

          {/* RETRIEVAL */}
          <section>
            <div className="flex items-center justify-between">
              <Label>Precedent retrieved</Label>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                k = 3 · consensus-verified
              </span>
            </div>

            {record.retrieved.length ? (
              <div className="mt-6">
                {record.retrieved.map((r, i) => {
                  const h = holdings.find((x) => x.id === r.holdingId)!;
                  return (
                    <div key={r.holdingId} className="border-b border-white/[0.06] py-5">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-3">
                          <Link
                            href={`/holdings/${h.id}`}
                            className="inline-block py-[4px] font-mono text-[12px] tracking-[0.1em] text-paper hover:text-copper"
                          >
                            #{h.id}
                          </Link>
                          <VerdictTag verdict={h.verdict} />
                          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                            {h.appeal}
                          </span>
                        </div>
                        <span
                          className={cx(
                            "font-mono text-[10px] uppercase tracking-[0.12em]",
                            r.outcome === "FOLLOWED"
                              ? "text-verdict"
                              : r.outcome === "DISTINGUISHED"
                                ? "text-dissent"
                                : "text-info",
                          )}
                        >
                          {r.outcome}
                        </span>
                      </div>
                      <div className="mt-3 flex items-center gap-4">
                        <div className="h-[3px] flex-1 bg-white/[0.06]">
                          <div
                            className="h-[3px] bg-copper/80"
                            style={{ width: `${r.similarity}%` }}
                          />
                        </div>
                        <span className="w-[64px] text-right font-mono text-[11px] tabular-nums text-stone">
                          {r.similarity}%
                        </span>
                      </div>
                      <p className="mt-3 text-[13px] leading-[1.6] text-muted">{r.note}</p>
                      <p className="mt-2 text-[13px] leading-[1.6] text-stone">{h.issue}</p>
                    </div>
                  );
                })}
              </div>
            ) : (
              <div className="mt-6 border border-white/[0.08] bg-ink p-6">
                <p className="text-[13.5px] leading-[1.7] text-stone">
                  No precedent was retrieved. The index held nothing comparable when this case was
                  decided, so the panel ruled on the terms as written — exactly as GenLayer behaves
                  today. HOLDING degrades to that behaviour safely; it never makes a contract worse.
                </p>
              </div>
            )}
          </section>

          {/* COMPARISON */}
          {nearest ? (
            <>
              <Rule className="my-14" />
              <section>
                <div className="flex items-center gap-3">
                  <Scale size={13} strokeWidth={1.5} className="text-copper" />
                  <Label>Precedent vs current case</Label>
                </div>
                <CaseCompare
                  className="mt-8"
                  left={{
                    id: nearest.id,
                    label: `Holding #${nearest.id}`,
                    facts: nearest.facts,
                    verdict: nearest.verdict,
                    meta: `Decided ${fmtDate(nearest.finalityTs)}`,
                  }}
                  right={{
                    id: record.id,
                    label: `Case #${record.id}`,
                    facts: record.facts,
                    verdict: record.verdict ?? undefined,
                    meta: `Submitted ${fmtDate(record.submitted)}`,
                  }}
                  materialDifference={record.materialDifference}
                />
              </section>
            </>
          ) : null}

          {/* DISTINGUISHMENT */}
          {record.distinguishment ? (
            <>
              <Rule className="my-14" />
              <section>
                <Label>Distinguishment</Label>
                <p className="display mt-5 max-w-[56ch] text-[21px] leading-[1.45] text-paper md:text-[25px]">
                  “{record.distinguishment}”
                </p>
                <p className="mt-6 max-w-[54ch] text-[13px] leading-[1.7] text-muted">
                  Recorded as part of the new holding. The next panel to face this fact pattern
                  inherits both the original rule and the exception.
                </p>
              </section>
            </>
          ) : null}

          <Rule className="my-14" />

          {/* PANEL */}
          <section>
            <PanelReview members={record.panel} />
          </section>
        </div>

        {/* ---------- sidebar ---------- */}
        <aside className="md:col-span-4">
          <div className="md:sticky md:top-[80px]">
            <div className="panel rounded-[10px] p-6">
              <Label>Sequence</Label>
              <ol className="mt-5 space-y-0">
                {[
                  { k: "Submitted", v: fmtDate(record.submitted) },
                  {
                    k: "Precedent retrieved",
                    v: record.retrieved.length ? `${record.retrieved.length} holdings` : "None available",
                  },
                  { k: "Panel", v: `${record.panel.length} validators` },
                  { k: "Consensus", v: record.consensus },
                  {
                    k: record.distinguishment ? "Distinguished" : "Followed",
                    v: record.verdict ?? "Pending",
                  },
                ].map((s, i, arr) => (
                  <li key={s.k} className="relative pl-6">
                    {i < arr.length - 1 ? (
                      <span className="absolute left-[2px] top-[16px] h-[22px] w-px bg-white/10" />
                    ) : null}
                    <span
                      className={cx(
                        "absolute left-0 top-[6px] h-[5px] w-[5px] rounded-full",
                        i === arr.length - 1 ? "bg-copper" : "bg-white/25",
                      )}
                    />
                    <div className={i < arr.length - 1 ? "pb-5" : ""}>
                      <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                        {s.k}
                      </p>
                      <p className="mt-1 font-mono text-[12px] text-paper">{s.v}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            {resulting ? (
              <Link
                href={`/holdings/${resulting.id}`}
                className="group mt-6 block rounded-[10px] border border-white/[0.08] bg-ink p-6 transition-all duration-200 hover:-translate-y-[1px] hover:border-copper/35"
              >
                <Label>Resulting holding</Label>
                <p className="mt-3 font-mono text-[14px] tracking-[0.08em] text-paper group-hover:text-copper">
                  #{resulting.id}
                </p>
                <p className="mt-2 text-[13px] leading-[1.6] text-stone">{resulting.issue}</p>
                <p className="mt-4 line-clamp-3 text-[12.5px] leading-[1.65] text-muted">
                  {resulting.ratio}
                </p>
                <span className="mt-5 inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-stone group-hover:text-copper">
                  Open holding
                  <ArrowRight size={11} strokeWidth={1.5} />
                </span>
              </Link>
            ) : (
              <div className="mt-6 rounded-[10px] border border-white/[0.08] bg-ink p-6">
                <Label>Resulting holding</Label>
                <p className="mt-3 text-[13px] leading-[1.65] text-stone">
                  Created once consensus is final. The appeal window is open for roughly thirty
                  minutes before the holding is indexed.
                </p>
              </div>
            )}

            <p className="mt-6 font-mono text-[10px] uppercase leading-[1.8] tracking-[0.12em] text-muted">
              Demo environment · simulated record
            </p>
          </div>
        </aside>
      </div>
    </>
  );
}
