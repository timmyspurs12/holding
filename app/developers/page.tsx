import type { Metadata } from "next";
import { ArrowUpRight } from "lucide-react";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { Label, Rule, MetaTag } from "@/lib/components/ui/primitives";
import { RegisterSource } from "@/lib/components/operator/RegisterSource";

export const metadata: Metadata = {
  title: "Developers",
  description: "Give your Intelligent Contract a memory: emit a holding, retrieve precedent, distinguish on the record.",
};

const STEPS = [
  {
    n: "01",
    k: "Emit",
    v: "Create a holding after finality.",
    d: "The mixin distils the decision into issue, facts, verdict, reason codes and ratio, then writes it to the registry.",
  },
  {
    n: "02",
    k: "Retrieve",
    v: "Ask HOLDING for relevant precedent.",
    d: "A free view call, executed inside GenVM so every validator recomputes the same k-NN.",
  },
  {
    n: "03",
    k: "Distinguish",
    v: "Follow precedent, or explain why this case differs.",
    d: "The instruction lives in the prompt. A departure is recorded as a distinguishment and becomes part of the new holding.",
  },
];

const SCHEMA: [string, string][] = [
  ["holding_id", "unique · on-chain"],
  ["domain", "escrow · prediction-markets · moderation · …"],
  ["contract_class", "which contract produced it"],
  ["issue", "the question actually decided, in one sentence"],
  ["facts_digest", "the material facts, normalised"],
  ["verdict", "the structured outcome"],
  ["reason_codes[]", "from the contract's own taxonomy"],
  ["ratio", "the reason, in one sentence — the binding part"],
  ["evidence_hashes[]", "what it was decided on"],
  ["panel_size", "5 / 11 / more"],
  ["appeal_outcome", "survived unappealed / upheld / overturned"],
  ["finality_ts", "finality timestamp"],
];

const CODE = `from holding import HoldingEmitter          # ~30-line mixin

class RefundArbiter(gl.Contract, HoldingEmitter):
    domain = "digital-commerce"

    @gl.public.write
    def resolve(self, case_digest: str) -> None:
        # 02 · RETRIEVE — free view call, runs inside GenVM
        precedent = self.get_precedent(case_digest, self.domain, k=3)

        verdict = gl.nondet.exec_prompt(f"""
Rule on this case.

CASE
{case_digest}

NEAREST HOLDINGS
{precedent.formatted()}

Rule consistently with the nearest holdings unless you can state,
in one sentence, a material difference. If you rule differently,
that sentence is your distinguishment.
""")

        # 03 · EMIT — after finality, the decision becomes authority
        self.emit_holding(
            issue           = verdict["issue"],
            facts           = verdict["facts"],
            verdict         = verdict["outcome"],
            reason_codes    = verdict["reason_codes"],
            ratio           = verdict["ratio"],
            distinguishment = verdict.get("distinguishment"),
        )`;

export default function DevelopersPage() {
  return (
    <>
      <PageHeader
        eyebrow="Developers"
        title="Give your Intelligent Contract a memory."
        lede="Three steps, one mixin, no rewrite. Emit a holding when a decision becomes final, ask for precedent before you rule, and let the panel decide whether to follow it."
        meta={
          <div className="space-y-3 text-right">
            <MetaTag tone="copper">Spec complete</MetaTag>
            <p className="font-mono text-[10px] uppercase leading-[1.8] tracking-[0.12em] text-muted">
              SDK in progress
              <br />
              Testnet target · Bradbury
            </p>
          </div>
        }
      />

      {/* ---------- three steps ---------- */}
      <section className="shell py-16 md:py-20">
        <div className="grid gap-10 md:grid-cols-3 md:gap-12">
          {STEPS.map((s) => (
            <div key={s.n} className="border-t border-white/[0.12] pt-6">
              <span className="font-mono text-[10px] tracking-[0.16em] text-copper">{s.n}</span>
              <h2 className="mt-4 font-mono text-[13px] uppercase tracking-[0.12em] text-paper">
                {s.k}
              </h2>
              <p className="mt-3 text-[14px] leading-[1.55] text-paper">{s.v}</p>
              <p className="mt-3 text-[13px] leading-[1.65] text-stone">{s.d}</p>
            </div>
          ))}
        </div>

        <div className="mt-16 overflow-hidden rounded-[10px] border border-white/[0.08] bg-ink">
          <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Python · Intelligent Contract
            </span>
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Illustrative
            </span>
          </div>
          <pre className="overflow-x-auto p-6 font-mono text-[12.5px] leading-[1.85] text-stone">
            {CODE}
          </pre>
        </div>

        <div className="mt-10 grid gap-8 md:grid-cols-12">
          <div className="md:col-span-6">
            <p className="display text-[24px] leading-[1.35] text-paper md:text-[30px]">
              That&apos;s the integration.
            </p>
          </div>
          <div className="md:col-span-6">
            <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
              The retrieval call is the only new surface your contract touches. Everything else —
              authority weighting, citation graph, consistency scoring, the Reporter — comes with
              the registry and costs you nothing.
            </p>
          </div>
        </div>
      </section>

      <RegisterSource />

      {/* ---------- schema ---------- */}
      <section id="schema" className="scroll-mt-20 border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <div className="grid gap-6 md:grid-cols-12">
            <div className="md:col-span-5">
              <div id="sdk" className="scroll-mt-20">
                <Label>The schema</Label>
              </div>
              <h2 className="display mt-4 text-[28px] leading-[1.18] text-paper md:text-[34px]">
                One record. Twelve fields. That is the standard.
              </h2>
            </div>
            <div className="md:col-span-6 md:col-start-7 md:pt-3">
              <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
                The hard part of this project was never the code — it was agreeing what a holding
                contains. Get this right and every contract&apos;s decisions become comparable to
                every other contract&apos;s.
              </p>
            </div>
          </div>

          <div className="mt-12 overflow-hidden rounded-[10px] border border-white/[0.08] bg-ink">
            <div className="flex items-center justify-between border-b border-white/[0.06] px-5 py-3">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                Holding
              </span>
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                v0.1
              </span>
            </div>
            <div className="divide-y divide-white/[0.05]">
              {SCHEMA.map(([k, v]) => (
                <div key={k} className="grid grid-cols-12 gap-4 px-5 py-[10px] md:px-6">
                  <code className="col-span-12 font-mono text-[12.5px] text-paper sm:col-span-5 md:col-span-4">
                    {k}
                  </code>
                  <span className="col-span-12 font-mono text-[11.5px] text-muted sm:col-span-7 md:col-span-8">
                    {v}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {/* ---------- why inside genvm ---------- */}
      <section className="border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <div className="grid gap-10 md:grid-cols-12">
            <div className="md:col-span-5">
              <Label>Why retrieval runs inside GenVM</Label>
              <h2 className="display mt-4 text-[26px] leading-[1.22] text-paper md:text-[32px]">
                An off-chain index means whoever runs the database owns the law.
              </h2>
            </div>
            <div className="md:col-span-6 md:col-start-7">
              <p className="max-w-[48ch] text-[14px] leading-[1.7] text-stone">
                GenLayer ships a native on-chain vector store. Embeddings are produced by a pinned
                model, so they are deterministic; the k-NN is deterministic; and every validator
                recomputes it. A panel cannot be shown a curated set of precedents, because the
                retrieval is part of consensus rather than a service in front of it.
              </p>
              <div className="mt-8 space-y-3">
                {[
                  { href: "https://docs.genlayer.com/", label: "GenLayer documentation" },
                  {
                    href: "https://docs.genlayer.com/developers/intelligent-contracts/advanced-features/vector-store",
                    label: "Vector Store reference",
                  },
                ].map((l) => (
                  <a
                    key={l.href}
                    href={l.href}
                    target="_blank"
                    rel="noreferrer"
                    className="group flex items-center justify-between border-b border-white/[0.08] pb-3 text-[13.5px] text-stone transition-colors hover:text-paper"
                  >
                    {l.label}
                    <ArrowUpRight
                      size={13}
                      strokeWidth={1.5}
                      className="transition-transform duration-200 group-hover:-translate-y-[2px] group-hover:translate-x-[2px]"
                    />
                  </a>
                ))}
              </div>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
