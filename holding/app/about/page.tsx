import type { Metadata } from "next";
import { PageHeader } from "@/lib/components/site/PageHeader";
import { Label, Rule, Stat } from "@/lib/components/ui/primitives";
import { NETWORK_FACTS } from "@/lib/data";

export const metadata: Metadata = {
  title: "About",
  description: "Why precedent is the missing layer in on-chain adjudication, and why only GenLayer can build it.",
};

const QUOTES = [
  {
    text:
      "No on-chain platform currently asks jurors to rely on jurisdictional precedent, rigorous legal analysis, or even simple legal tests… The first problem is that of consistency. Similar facts may lead to wildly different outcomes… Such a system cannot stand.",
    cite: "University of Pennsylvania Law Review",
    href: "https://scholarship.law.upenn.edu/cgi/viewcontent.cgi?article=9702&context=penn_law_review",
  },
  {
    text:
      "Judging is about weighing reasons in the search for the most justified answer. Guessing is not.",
    cite: "Oxford Business Law Blog · June 2026",
    href:
      "https://blogs.law.ox.ac.uk/oblb/blog-post/2026/06/guessing-not-judging-why-crowdsourced-blockchain-decisions-are-not-arbitral",
  },
  {
    text:
      "Coupling smart contracts with legal knowledge graphs and precedent databases could enhance accuracy and contextual awareness.",
    cite: "Nature · Scientific Reports · 2025 · listed as future work",
    href: "https://www.nature.com/articles/s41598-025-21313-x",
  },
];

const INGREDIENTS = [
  {
    k: "Structured, reasoned verdicts at scale",
    v: "You cannot derive a holding from a vote count. You need the issue, the material facts and the ratio. GenLayer produces roughly 25,800 reasoned decisions a day.",
    ok: true,
  },
  {
    k: "Consensus-verified semantic retrieval",
    v: "GenLayer ships a native on-chain vector store with pinned, deterministic embeddings. Retrieval inside GenVM is recomputed by every validator — the index cannot be poisoned by whoever is asking the question.",
    ok: true,
  },
  {
    k: "Permanence with an appeal process",
    v: "Authority needs a finality event and a survival signal. GenLayer has both: a roughly thirty-minute appeal window, and panels that expand from 5 to 11 validators on appeal.",
    ok: true,
  },
];

const NOT = [
  {
    k: "A vector database",
    v: "That is a component. VecDB is the storage primitive HOLDING uses, not the product.",
  },
  {
    k: "RAG",
    v: "Retrieval informs an answer. A holding binds: it creates a default outcome and a cost for departing from it. The distinguishing test has no analogue in RAG.",
  },
  {
    k: "A case-law search engine",
    v: "Search finds documents. HOLDING sits inside the adjudication loop, generates its own corpus, and changes the next verdict.",
  },
  {
    k: "A dashboard",
    v: "The Reporter is the surface. The deliverable is the schema and the retrieval contract every other contract calls.",
  },
];

const SOURCES = [
  {
    label: "GenLayer Vector Store — native on-chain VecDB",
    href: "https://docs.genlayer.com/developers/intelligent-contracts/advanced-features/vector-store",
  },
  { label: "GenLayer documentation", href: "https://docs.genlayer.com/" },
  { label: "GenLayer use cases", href: "https://genlayer.com/use-cases" },
  {
    label: "GenLayer — the intelligence layer of the internet (2024)",
    href: "https://www.genlayer.com/news/genlayer-the-intelligence-layer-of-the-internet",
  },
  {
    label: "CryptoDaily — 25,800 daily decisions, Internet Court consortium",
    href: "https://cryptodaily.co.uk/2026/07/genlayer-ai-agent-court-defi-dispute-resolution",
  },
  {
    label: "CryptoBriefing — panel composition, cost per ruling, mainnet target",
    href: "https://cryptobriefing.com/genlayer-ai-court-validators/",
  },
  {
    label: "CoinDesk — transaction time, appeal window, validator expansion",
    href: "https://www.coindesk.com/tech/2025/04/30/ai-powered-court-system-is-coming-to-crypto-with-genlayer",
  },
  {
    label: "Penn Law Review — precedent in smart-contract dispute resolution",
    href: "https://scholarship.law.upenn.edu/cgi/viewcontent.cgi?article=9702&context=penn_law_review",
  },
  {
    label: "Oxford Business Law Blog — guessing, not judging",
    href:
      "https://blogs.law.ox.ac.uk/oblb/blog-post/2026/06/guessing-not-judging-why-crowdsourced-blockchain-decisions-are-not-arbitral",
  },
  { label: "Nature — AI-powered digital arbitration", href: "https://www.nature.com/articles/s41598-025-21313-x" },
  {
    label: "PLOS ONE — AnyCase, token-curated registry of human court decisions",
    href: "https://journals.plos.org/plosone/article?id=10.1371%2Fjournal.pone.0240041",
  },
];

const ROADMAP = [
  { k: "Holding schema + emitter SDK", v: "1 week", note: "The deliverable" },
  { k: "HoldingRegistry contract", v: "1.5 weeks", note: "VecDB, authority scoring, citation graph" },
  { k: "Indexer", v: "1 week", note: "Finalised transactions → embeddings → anchored batch roots" },
  { k: "Reporter", v: "1.5 weeks", note: "Search, citation chains, consistency metrics" },
  { k: "Reference integrations", v: "1 week", note: "Two visible ecosystem projects wired up" },
];

export default function AboutPage() {
  return (
    <>
      <PageHeader
        eyebrow="About"
        title="Precedent is the difference between a court and a coin flip."
        lede="On-chain adjudication is fast, cheap and reasoned — and it remembers nothing. That missing memory is the single reason these systems are not treated as adjudication at all."
      />

      {/* ---------- the gap ---------- */}
      <section className="shell py-16 md:py-20">
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-5">
            <Label>The gap</Label>
            <h2 className="display mt-4 text-[28px] leading-[1.2] text-paper md:text-[34px]">
              A decision is produced, then discarded.
            </h2>
          </div>
          <div className="md:col-span-6 md:col-start-7">
            <p className="max-w-[48ch] text-[14px] leading-[1.75] text-stone">
              Two cases with identical facts can produce opposite verdicts, because the panel that
              decides the second one has no way to see the first. Every case pays full price for
              judgement that has already been bought. And an appeal cannot argue that a ruling
              contradicts an earlier one, because the earlier one was never recorded as something
              that could be contradicted.
            </p>
          </div>
        </div>

        <div className="mt-14 grid gap-10 border-t border-white/[0.08] pt-12 sm:grid-cols-2 lg:grid-cols-4">
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
      </section>

      {/* ---------- named by lawyers ---------- */}
      <section id="why" className="scroll-mt-20 border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <Label>Named by lawyers, not builders</Label>
          <div className="mt-10 grid gap-10 md:grid-cols-3">
            {QUOTES.map((q) => (
              <figure key={q.href} className="border-t border-white/[0.12] pt-6">
                <blockquote className="text-[15px] leading-[1.7] text-paper">“{q.text}”</blockquote>
                <figcaption className="mt-6">
                  <a
                    href={q.href}
                    target="_blank"
                    rel="noreferrer"
                    className="mt-2 inline-block py-[6px] font-mono text-[10px] uppercase tracking-[0.12em] text-muted underline decoration-white/20 underline-offset-4 hover:text-copper"
                  >
                    {q.cite}
                  </a>
                </figcaption>
              </figure>
            ))}
          </div>
          <p className="display mt-14 max-w-[34ch] text-[24px] leading-[1.35] text-paper md:text-[30px]">
            Read together: the reason on-chain adjudication is not taken seriously as adjudication
            is not speed, cost, or model quality. It is the absence of precedent.
          </p>
        </div>
      </section>

      {/* ---------- why genlayer ---------- */}
      <section className="border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <div className="grid gap-6 md:grid-cols-12">
            <div className="md:col-span-5">
              <Label>Why only GenLayer</Label>
              <h2 className="display mt-4 text-[28px] leading-[1.2] text-paper md:text-[34px]">
                Three ingredients. One chain has all of them.
              </h2>
            </div>
            <div className="md:col-span-6 md:col-start-7 md:pt-3">
              <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
                Build this with an off-chain vector database and you have a search tool whose
                operator can quietly decide which precedents a panel sees. On other chains you have
                votes, not holdings. Off GenLayer, the binding part is impossible.
              </p>
            </div>
          </div>

          <div className="mt-12">
            {INGREDIENTS.map((i) => (
              <div
                key={i.k}
                className="grid gap-6 border-t border-white/[0.08] py-7 md:grid-cols-12 md:gap-10"
              >
                <div className="md:col-span-4">
                  <div className="flex items-start gap-3">
                    <span className="mt-[6px] h-[6px] w-[6px] shrink-0 rotate-45 bg-copper" />
                    <h3 className="text-[15px] leading-[1.4] text-paper">{i.k}</h3>
                  </div>
                </div>
                <p className="max-w-[62ch] text-[13.5px] leading-[1.7] text-stone md:col-span-7">
                  {i.v}
                </p>
                <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-verdict md:col-span-1 md:text-right">
                  GenLayer
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- what it is not ---------- */}
      <section className="border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <Label>What this is not</Label>
          <div className="mt-10 grid gap-px overflow-hidden rounded-[10px] border border-white/[0.08] bg-white/[0.06] md:grid-cols-2">
            {NOT.map((n) => (
              <div key={n.k} className="bg-obsidian p-7">
                <h3 className="font-mono text-[11px] uppercase tracking-[0.14em] text-dissent">
                  Not {n.k.toLowerCase()}
                </h3>
                <p className="mt-4 max-w-[46ch] text-[13.5px] leading-[1.7] text-stone">{n.v}</p>
              </div>
            ))}
          </div>

          <div className="mt-12 grid gap-8 border-t border-white/[0.08] pt-10 md:grid-cols-12">
            <div className="md:col-span-5">
              <h3 className="display text-[22px] leading-[1.3] text-paper md:text-[26px]">
                It is also GenLayer&apos;s own unbuilt use case.
              </h3>
            </div>
            <div className="md:col-span-6 md:col-start-7">
              <p className="max-w-[48ch] text-[14px] leading-[1.7] text-stone">
                GenLayer&apos;s 2024 launch post describes a &ldquo;World Database&rdquo;: reward
                proposers for new and relevant information, let the contract check novelty,
                relevance and quality, and add it to its database. Described, never built. HOLDING
                is that idea, narrowed to the corpus GenLayer is already producing every day.
              </p>
              <a
                href="https://www.genlayer.com/news/genlayer-the-intelligence-layer-of-the-internet"
                target="_blank"
                rel="noreferrer"
                className="mt-4 inline-block py-[6px] font-mono text-[10px] uppercase tracking-[0.12em] text-muted underline decoration-white/20 underline-offset-4 hover:text-copper"
              >
                genlayer.com · 2024
              </a>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- roadmap ---------- */}
      <section className="border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <div className="grid gap-6 md:grid-cols-12">
            <div className="md:col-span-5">
              <Label>Scope</Label>
              <h2 className="display mt-4 text-[28px] leading-[1.2] text-paper md:text-[34px]">
                Roughly six weeks, solo.
              </h2>
            </div>
            <div className="md:col-span-6 md:col-start-7 md:pt-3">
              <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
                No novel protocol research. Every primitive it needs — on-chain vector storage,
                consensus, appeals, structured outputs, pinned deterministic embeddings — already
                ships. The risk is not the code; it is whether contracts adopt the schema.
              </p>
            </div>
          </div>

          <div className="mt-12">
            {ROADMAP.map((r) => (
              <div
                key={r.k}
                className="grid grid-cols-12 items-baseline gap-4 border-t border-white/[0.08] py-5"
              >
                <span className="col-span-12 text-[14px] text-paper md:col-span-5">{r.k}</span>
                <span className="col-span-6 text-[13px] text-stone md:col-span-5">{r.note}</span>
                <span className="col-span-6 text-right font-mono text-[11px] tabular-nums text-copper md:col-span-2">
                  {r.v}
                </span>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- sources ---------- */}
      <section id="sources" className="scroll-mt-20 border-t border-white/[0.08]">
        <div className="shell py-16 md:py-20">
          <Label>Sources</Label>
          <h2 className="display mt-4 text-[24px] leading-[1.25] text-paper md:text-[30px]">
            Every figure and quotation above is checkable.
          </h2>

          <div className="mt-10 grid gap-x-12 md:grid-cols-2">
            {SOURCES.map((s) => (
              <a
                key={s.href}
                href={s.href}
                target="_blank"
                rel="noreferrer"
                className="group flex items-start justify-between gap-6 border-b border-white/[0.06] py-4 transition-colors hover:bg-white/[0.02]"
              >
                <span className="text-[13.5px] text-stone group-hover:text-paper">{s.label}</span>
                <span className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-muted group-hover:text-copper">
                  Open ↗
                </span>
              </a>
            ))}
          </div>

          <p className="mt-12 max-w-[64ch] font-mono text-[10px] uppercase leading-[2] tracking-[0.12em] text-muted">
            This site is a demo environment. Holdings, cases, panels, similarity scores and corpus
            figures are simulated and do not represent live GenLayer records. Published ecosystem
            figures are attributed to their sources above.
          </p>
        </div>
      </section>
    </>
  );
}
