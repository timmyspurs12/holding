import type { Metadata } from "next";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { IntegrationFlow } from "@/lib/components/IntegrationFlow";
import { Label, Rule, MetaTag } from "@/lib/components/ui/primitives";

export const metadata: Metadata = {
  title: "Integrations",
  description: "Where HOLDING sits inside an Intelligent Contract, and what changes for each kind of application.",
};

const TARGETS = [
  {
    name: "Escrow & milestone payments",
    uses: "MilestoneEscrow",
    change:
      "Acceptance disputes stop being re-litigated from first principles. A late-but-conforming deliverable is decided the same way it was decided last month.",
    status: "Reference",
    tone: "copper" as const,
  },
  {
    name: "Prediction market resolution",
    uses: "ResolutionOracle",
    change:
      "Window, source-agreement and scope questions resolve consistently, so traders can price a market against how it has actually been resolved before.",
    status: "Reference",
    tone: "copper" as const,
  },
  {
    name: "Content moderation appeals",
    uses: "AppealsBoard",
    change:
      "Findings stand, but disproportionate sanctions get corrected the same way every time — and the correction is citable.",
    status: "Planned",
    tone: "neutral" as const,
  },
  {
    name: "Insurance claim adjudication",
    uses: "ClaimAdjudicator",
    change:
      "Materiality becomes a question with a recorded answer instead of a fresh judgement on every claim.",
    status: "Planned",
    tone: "neutral" as const,
  },
  {
    name: "Agent SLA enforcement",
    uses: "ServiceLevelCourt",
    change:
      "An agent can predict the consequence of a breach before it happens, which is the precondition for transacting at machine speed.",
    status: "Planned",
    tone: "neutral" as const,
  },
  {
    name: "DAO proposal validation",
    uses: "ProposalValidator",
    change:
      "Notice and quorum defects are decided on a stable rule rather than the mood of the voters present that week.",
    status: "Planned",
    tone: "neutral" as const,
  },
];

export default function IntegrationsPage() {
  return (
    <>
      <PageHeader
        eyebrow="Integrations"
        title="Where HOLDING sits."
        lede="Not beside the adjudication loop — inside it. A contract asks for precedent before it rules, the panel answers the record, and the outcome becomes precedent for the next one."
      />

      <section className="shell py-16">
        <IntegrationFlow />
      </section>

      <section className="border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <div className="grid gap-6 md:grid-cols-12">
            <div className="md:col-span-5">
              <Label>Adopters</Label>
              <h2 className="display mt-4 text-[28px] leading-[1.18] text-paper md:text-[34px]">
                Every contract that has to decide the same kind of question twice.
              </h2>
            </div>
            <div className="md:col-span-6 md:col-start-7 md:pt-3">
              <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
                HOLDING is valuable in proportion to how often a contract sees a recurring question.
                Escrow, resolution, moderation and claims all do. One-off creative judgements do not,
                and do not need it.
              </p>
            </div>
          </div>

          <div className="mt-14">
            {TARGETS.map((t) => (
              <div
                key={t.name}
                className="grid gap-6 border-t border-white/[0.08] py-7 md:grid-cols-12 md:gap-10"
              >
                <div className="md:col-span-3">
                  <h3 className="text-[15.5px] leading-[1.4] text-paper">{t.name}</h3>
                  <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                    {t.uses}
                  </p>
                </div>
                <p className="max-w-[62ch] text-[13.5px] leading-[1.7] text-stone md:col-span-7">
                  {t.change}
                </p>
                <div className="md:col-span-2 md:text-right">
                  <MetaTag tone={t.tone}>{t.status}</MetaTag>
                </div>
              </div>
            ))}
          </div>

          <p className="mt-10 font-mono text-[10px] uppercase leading-[1.8] tracking-[0.12em] text-muted">
            Reference = wired up against demo data · Planned = designed, not yet implemented
          </p>
        </div>
      </section>

      <section className="border-t border-white/[0.08]">
        <div className="shell grid gap-10 py-16 md:grid-cols-12">
          <div className="md:col-span-5">
            <Label>Adopt the schema</Label>
            <h3 className="display mt-4 text-[24px] leading-[1.25] text-paper md:text-[30px]">
              Six weeks of work becomes one afternoon if the contract already emits a holding.
            </h3>
          </div>
          <div className="md:col-span-6 md:col-start-7 md:pt-2">
            <p className="max-w-[48ch] text-[14px] leading-[1.7] text-stone">
              The emitter is a mixin, not a rewrite. Import it, emit on finality, and call the
              Chamber before you rule. Everything else — authority weighting, citation graph,
              consistency scoring — comes with the registry.
            </p>
            <Link
              href="/developers"
              className="mt-6 inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-copper"
            >
              Read the integration
              <ArrowRight size={11} strokeWidth={1.5} />
            </Link>
          </div>
        </div>
      </section>
    </>
  );
}
