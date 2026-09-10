import type { Metadata } from "next";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { PrecedentConsole } from "@/lib/components/PrecedentConsole";
import { Label } from "@/lib/components/ui/primitives";
import { NETWORK_FACTS } from "@/lib/data";

export const metadata: Metadata = {
  title: "Precedent console",
  description: "Run a case against the index and watch the panel answer the record.",
};

const NOTES = [
  {
    k: "Retrieval is consensus-verified",
    v: "The k-NN runs inside GenVM. Every validator recomputes it, so no party chooses which precedents the panel sees.",
  },
  {
    k: "Following is the default",
    v: "The panel rules consistently with the nearest holdings unless it can state a material difference in one sentence.",
  },
  {
    k: "Departure is recorded",
    v: "A distinguishment becomes part of the new holding, so the exception is inherited by every later panel.",
  },
];

export default function PrecedentPage() {
  return (
    <>
      <PageHeader
        eyebrow="Precedent console"
        title="Run a case. Watch the panel answer the record."
        lede="Pick a fact pattern, ask the index for precedent, and let the panel rule. Every step below is the sequence a HOLDING-enabled contract runs — retrieval, suggestion, vote, verdict."
        meta={
          <div className="space-y-3 text-right">
            {NETWORK_FACTS.slice(0, 2).map((f) => (
              <div key={f.label}>
                <div className="display text-[26px] leading-none tabular-nums text-paper">
                  {f.figure}
                </div>
                <div className="mt-2">
                  <Label>{f.label}</Label>
                </div>
              </div>
            ))}
          </div>
        }
      />

      <section className="shell py-14 md:py-16">
        <PrecedentConsole />
      </section>

      <section className="border-t border-white/[0.08]">
        <div className="shell grid gap-10 py-16 md:grid-cols-3">
          {NOTES.map((n) => (
            <div key={n.k}>
              <Label>{n.k}</Label>
              <p className="mt-4 max-w-[38ch] text-[13.5px] leading-[1.7] text-stone">{n.v}</p>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}
