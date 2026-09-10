import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { Label, Rule, SectionHeading, Stat, ActionLink, MetaTag, cx } from "@/lib/components/ui/primitives";
import { PrecedentStrip } from "@/lib/components/PrecedentStrip";
import { PrecedentMemory } from "@/lib/components/PrecedentMemory";
import { LiveDemo } from "@/lib/components/demo/LiveDemo";
import { DistinguishmentDemo } from "@/lib/components/demo/DistinguishmentDemo";
import { IntegrationFlow } from "@/lib/components/IntegrationFlow";
import { ConsistencyMeter } from "@/lib/components/ConsistencyMeter";
import { NETWORK_FACTS, DOMAINS, fmtNum } from "@/lib/data";
import { getCorpus } from "@/lib/data/live";

const PARTS = [
  {
    n: "01",
    title: "Index",
    sub: "ingestion",
    body: "Every finalised decision is distilled into a canonical holding: the issue, the material facts, the verdict, the reason codes and the ratio — the one sentence that binds. Embedded and written into an on-chain vector store.",
    foot: "Authority is weighted by appeal survival, panel size and citation count.",
  },
  {
    n: "02",
    title: "Chamber",
    sub: "retrieval",
    body: "One free view call any contract can make before it rules. It runs inside GenVM, so every validator recomputes the retrieval independently.",
    foot: "The index cannot be poisoned by whoever is asking the question.",
  },
  {
    n: "03",
    title: "Distinguishing test",
    sub: "the legal mechanism",
    body: "A panel rules consistently with the nearest holdings unless it can state, in one sentence, a material difference. That sentence is recorded as the distinguishment and becomes part of the new holding.",
    foot: "Consistency becomes the default without becoming a cage.",
  },
  {
    n: "04",
    title: "Reporter",
    sub: "the surface",
    body: "Search holdings by domain, issue or free text; follow citation chains; read how a domain is actually being adjudicated; see which holdings are being distinguished most.",
    foot: "A live map of where the law is moving.",
  },
];

const STEPS = [
  { n: "01", k: "Emit", v: "Create a holding after finality." },
  { n: "02", k: "Retrieve", v: "Ask HOLDING for relevant precedent." },
  { n: "03", k: "Distinguish", v: "Follow precedent, or explain why this case differs." },
];

export default async function HomePage() {
  const { stats: CORPUS, live } = await getCorpus();
  return (
    <>
      {/* ================= HERO ================= */}
      <section className="relative overflow-hidden border-b border-white/[0.08]">
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 opacity-[0.55]"
          style={{
            background:
              "radial-gradient(720px 420px at 78% -6%, rgba(215,164,90,0.10), transparent 62%)",
          }}
        />
        <div className="shell relative py-20 md:py-28">
          <div className="grid gap-10 md:grid-cols-12">
            <div className="md:col-span-9">
              <span className="label">GenLayer / Precedent infrastructure</span>
              <h1 className="display mt-7 text-[58px] leading-[0.94] text-paper sm:text-[72px] md:text-[88px]">
                Every decision
                <br />
                becomes precedent.
              </h1>
              <p className="mt-9 max-w-[56ch] text-[17px] leading-[1.6] text-stone md:text-[19px]">
                HOLDING turns finalized GenLayer decisions into searchable, citable authority for
                the decisions that come next.
              </p>
              <div className="mt-10 flex flex-wrap items-center gap-3">
                <ActionLink href="/reporter">Explore the precedent</ActionLink>
                <ActionLink href="#how" variant="ghost">
                  See how it works
                </ActionLink>
              </div>
            </div>
          </div>

          <PrecedentStrip className="mt-20" />

          <div className="mt-14 grid gap-8 border-t border-white/[0.08] pt-10 sm:grid-cols-3">
            <Stat figure={fmtNum(CORPUS.holdingsIndexed)} label="Holdings indexed" demo={!live} />
            <Stat figure={`${CORPUS.consistency}%`} label="Domain consistency" demo={!live} />
            <Stat figure={String(CORPUS.domainsCovered)} label="Domains covered" demo={!live} />
          </div>
        </div>
      </section>

      {/* ================= PROBLEM ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-28">
          <div className="grid gap-12 md:grid-cols-12">
            <div className="md:col-span-7">
              <span className="label">The problem</span>
              <h2 className="display mt-6 text-[32px] leading-[1.16] text-paper md:text-[44px]">
                GenLayer can reach consensus on a decision.
              </h2>
              <p className="display mt-4 text-[32px] leading-[1.16] text-copper md:text-[44px]">
                HOLDING makes that decision useful to the decisions that follow.
              </p>
            </div>
            <div className="md:col-span-5 md:pt-4">
              <p className="max-w-[42ch] text-[14px] leading-[1.7] text-stone">
                Roughly 25,800 decisions are adjudicated every day. Every one of them is discarded
                the moment it becomes final. Nothing is carried forward: no memory of how a case
                like yours was decided last Tuesday, and no ground for an appeal beyond asking more
                validators and hoping.
              </p>
              <div className="mt-8">
                <a
                  href="https://cryptodaily.co.uk/2026/07/genlayer-ai-agent-court-defi-dispute-resolution"
                  target="_blank"
                  rel="noreferrer"
                  className="mt-2 inline-block py-[6px] font-mono text-[10px] uppercase tracking-[0.14em] text-muted underline decoration-white/20 underline-offset-4 hover:text-copper"
                >
                  CryptoDaily · Jul 2026
                </a>
              </div>
            </div>
          </div>

          {/* before / after */}
          <div className="mt-20 grid gap-px overflow-hidden rounded-[10px] border border-white/[0.08] bg-white/[0.06] md:grid-cols-2">
            <div className="bg-obsidian p-8 md:p-10">
              <div className="flex items-center justify-between">
                <span className="label">Before</span>
                <MetaTag tone="neutral">Stateless</MetaTag>
              </div>
              <ol className="mt-8 space-y-0">
                {[
                  { k: "Decision", d: "Five validators rule", tone: "text-paper" },
                  { k: "Finality", d: "Appeal window closes", tone: "text-stone" },
                  { k: "Gone", d: "Nothing carried forward", tone: "text-muted" },
                ].map((s, i) => (
                  <li key={s.k} className="relative pl-7">
                    {i < 2 ? (
                      <span className="absolute left-[6px] top-[22px] h-[18px] w-px bg-white/10" />
                    ) : null}
                    <span
                      className={cx(
                        "absolute left-0 top-[6px] h-[5px] w-[5px] rounded-full",
                        i === 2 ? "bg-dissent/70" : "bg-white/25",
                      )}
                    />
                    <div className={i < 2 ? "pb-6" : ""}>
                      <p className={cx("font-mono text-[12px] uppercase tracking-[0.14em]", s.tone)}>
                        {s.k}
                      </p>
                      <p className="mt-1 text-[13px] text-muted">{s.d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>

            <div className="bg-ink p-8 md:p-10">
              <div className="flex items-center justify-between">
                <span className="label">After</span>
                <MetaTag tone="copper">Precedent</MetaTag>
              </div>
              <ol className="mt-8">
                {[
                  { k: "Decision", d: "Five validators rule", tone: "text-paper" },
                  { k: "Holding", d: "Issue, facts, ratio recorded", tone: "text-paper" },
                  { k: "Precedent", d: "Indexed and authority-weighted", tone: "text-paper" },
                  { k: "New decision", d: "Panel sees the nearest holdings", tone: "text-copper" },
                  { k: "New holding", d: "Followed or distinguished on the record", tone: "text-copper" },
                ].map((s, i) => (
                  <li key={s.k} className="relative pl-7">
                    {i < 4 ? (
                      <span className="absolute left-[6px] top-[22px] h-[18px] w-px bg-copper/25" />
                    ) : null}
                    <span
                      className={cx(
                        "absolute left-0 top-[6px] h-[5px] w-[5px] rounded-full",
                        i >= 3 ? "bg-copper" : "bg-white/30",
                      )}
                    />
                    <div className={i < 4 ? "pb-6" : ""}>
                      <p className={cx("font-mono text-[12px] uppercase tracking-[0.14em]", s.tone)}>
                        {s.k}
                      </p>
                      <p className="mt-1 text-[13px] text-muted">{s.d}</p>
                    </div>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        </div>
      </section>

      {/* ================= MEMORY ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-24">
          <PrecedentMemory />
        </div>
      </section>

      {/* ================= LIVE DEMO ================= */}
      <section id="how" className="border-b border-white/[0.08] scroll-mt-20">
        <div className="shell py-20 md:py-28">
          <SectionHeading
            eyebrow="Live demonstration"
            title="Watch precedent form."
            text="A case is decided, turns into a holding, and is retrieved by the next panel — which follows it. Nothing here is a mock-up of a chart: this is the sequence a HOLDING-enabled contract actually runs."
          />
          <div className="mt-12">
            <LiveDemo />
          </div>
        </div>
      </section>

      {/* ================= DISTINGUISHMENT ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-28">
          <SectionHeading
            eyebrow="The distinguishing test"
            title="Precedent is not a cage. It is a thing you have to answer."
            text="Two cases can look identical and still deserve different outcomes. HOLDING does not force the second panel to repeat the first — it requires that the panel say, on the record, what is different. That sentence becomes part of the new holding."
          />
          <div className="mt-12">
            <DistinguishmentDemo />
          </div>
        </div>
      </section>

      {/* ================= FOUR PARTS (light) ================= */}
      <section className="paper-surface grain relative border-b border-black/10">
        <div className="shell py-20 md:py-28">
          <div className="grid gap-6 md:grid-cols-12">
            <div className="md:col-span-7">
              <span
                className="font-mono text-[10px] uppercase tracking-[0.18em]"
                style={{ color: "#686A67" }}
              >
                The build
              </span>
              <h2
                className="display mt-4 text-[30px] leading-[1.15] md:text-[38px]"
                style={{ color: "#111317" }}
              >
                Four parts. One of them is the product.
              </h2>
            </div>
            <div className="md:col-span-5 md:pt-9">
              <p className="max-w-[42ch] text-[14px] leading-[1.7]" style={{ color: "#686A67" }}>
                The registry is the easy part. The deliverable is the schema, and the retrieval that
                every contract can afford to call before it rules.
              </p>
            </div>
          </div>

          <div className="mt-16 grid gap-x-12 gap-y-12 md:grid-cols-2">
            {PARTS.map((p) => (
              <div key={p.n} className="border-t pt-6" style={{ borderColor: "rgba(0,0,0,0.14)" }}>
                <div className="flex items-baseline gap-4">
                  <span className="font-mono text-[11px] tracking-[0.14em]" style={{ color: "#686A67" }}>
                    {p.n}
                  </span>
                  <h3 className="display text-[24px]" style={{ color: "#111317" }}>
                    {p.title}
                  </h3>
                  <span
                    className="font-mono text-[10px] uppercase tracking-[0.14em]"
                    style={{ color: "#686A67" }}
                  >
                    {p.sub}
                  </span>
                </div>
                <p className="mt-4 max-w-[52ch] text-[14px] leading-[1.75]" style={{ color: "#45474A" }}>
                  {p.body}
                </p>
                <p
                  className="mt-4 font-mono text-[10px] uppercase tracking-[0.12em]"
                  style={{ color: "#686A67" }}
                >
                  {p.foot}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ================= CONSISTENCY + DOMAINS ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-28">
          <div className="grid gap-16 md:grid-cols-12">
            <div className="md:col-span-5">
              <ConsistencyMeter
                followed={94}
                distinguished={6}
                note="Digital commerce · demo figure"
              />
            </div>

            <div className="md:col-span-7">
              <Label>By domain</Label>
              <div className="mt-6">
                {DOMAINS.slice(0, 5).map((d) => (
                  <Link
                    key={d.slug}
                    href={`/domains#${d.slug}`}
                    className="group grid grid-cols-12 items-center gap-4 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
                  >
                    <span className="col-span-5 text-[13.5px] text-paper group-hover:text-copper">
                      {d.name}
                    </span>
                    <span className="col-span-3 font-mono text-[11px] tabular-nums text-muted">
                      {fmtNum(d.holdings)} holdings
                    </span>
                    <span className="col-span-4 flex items-center gap-3">
                      <span className="h-[3px] flex-1 bg-white/[0.06]">
                        <span
                          className="block h-[3px] bg-verdict/80"
                          style={{ width: `${d.consistency}%` }}
                        />
                      </span>
                      <span className="w-9 text-right font-mono text-[11px] tabular-nums text-stone">
                        {d.consistency}%
                      </span>
                    </span>
                  </Link>
                ))}
              </div>
              <Link
                href="/domains"
                className="mt-4 inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
              >
                All domains
                <ArrowRight size={12} strokeWidth={1.5} />
              </Link>
            </div>
          </div>
        </div>
      </section>

      {/* ================= INTEGRATION ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-28">
          <SectionHeading
            eyebrow="Integration"
            title="Your contract calls it. The panel answers it."
            text="HOLDING sits inside the adjudication loop, not beside it. A contract asks for precedent before it rules; the panel either follows it or writes down why it does not."
          />
          <IntegrationFlow className="mt-14" />

          <div className="mt-20 grid gap-10 border-t border-white/[0.08] pt-12 md:grid-cols-12">
            <div className="md:col-span-5">
              <span className="label">Developers</span>
              <h3 className="display mt-4 text-[28px] leading-[1.2] text-paper md:text-[34px]">
                Give your Intelligent Contract a memory.
              </h3>
              <div className="mt-8">
                <ActionLink href="/developers">Read the integration</ActionLink>
              </div>
            </div>

            <div className="md:col-span-7">
              <ol className="grid gap-8 sm:grid-cols-3">
                {STEPS.map((s) => (
                  <li key={s.n}>
                    <span className="font-mono text-[10px] tracking-[0.16em] text-copper">{s.n}</span>
                    <p className="mt-3 font-mono text-[12px] uppercase tracking-[0.12em] text-paper">
                      {s.k}
                    </p>
                    <p className="mt-2 text-[13px] leading-[1.6] text-stone">{s.v}</p>
                  </li>
                ))}
              </ol>

              <div className="mt-10 overflow-hidden rounded-[9px] border border-white/[0.08] bg-ink">
                <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-2">
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                    Python · Intelligent Contract
                  </span>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                    Demo
                  </span>
                </div>
                <pre className="overflow-x-auto p-5 font-mono text-[12.5px] leading-[1.8] text-stone">
{`precedent = holding_registry.get_precedent(
    case_digest = self.case_digest,
    domain      = "digital-commerce",
    k           = 3,
)`}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ================= NETWORK FACTS ================= */}
      <section className="border-b border-white/[0.08]">
        <div className="shell py-20 md:py-24">
          <SectionHeading
            eyebrow="Why now"
            title="Mainnet is Q4 2026."
            text="Precedent that exists before scale is clean law. Precedent retro-fitted onto millions of unstructured past decisions is a migration project."
          />
          <div className="mt-14 grid gap-10 sm:grid-cols-2 lg:grid-cols-4">
            {NETWORK_FACTS.map((f) => (
              <Stat
                key={f.label}
                figure={f.figure}
                label={f.label}
                detail={f.detail}
                source={f.source}
                url={f.url}
                size="sm"
              />
            ))}
          </div>
        </div>
      </section>

      {/* ================= CTA ================= */}
      <section>
        <div className="shell py-20 md:py-28">
          <div className="grid gap-10 md:grid-cols-12 md:items-end">
            <div className="md:col-span-7">
              <h2 className="display text-[34px] leading-[1.14] text-paper md:text-[48px]">
                Start from the record, not from the model.
              </h2>
              <p className="mt-6 max-w-[52ch] text-[15px] leading-[1.7] text-stone">
                Open the Reporter and read a holding. Then open a case and watch the panel answer
                it. Everything you see is simulated; the mechanism is not.
              </p>
            </div>
            <div className="md:col-span-5 md:justify-self-end">
              <div className="flex flex-wrap gap-3">
                <ActionLink href="/reporter">Explore the precedent</ActionLink>
                <ActionLink href="/developers" variant="ghost">
                  Developers
                </ActionLink>
              </div>
              <p className="mt-6 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                Demo environment · simulated records
              </p>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
