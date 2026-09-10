"use client";

import { useEffect, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Pause, Play, RotateCcw } from "lucide-react";
import { cx, Label, VerdictTag, MetaTag } from "../ui/primitives";
import { useSequencer } from "./useSequencer";
import { CORPUS, fmtNum } from "@/lib/data";

const STAGES = [
  { id: "case", label: "Case filed" },
  { id: "final", label: "Finalised" },
  { id: "holding", label: "Holding created" },
  { id: "indexed", label: "Indexed" },
  { id: "newcase", label: "New case" },
  { id: "retrieve", label: "Precedent retrieved" },
  { id: "related", label: "Related holdings" },
  { id: "suggest", label: "Suggestion" },
  { id: "consensus", label: "Consensus" },
];

const DURATIONS = [2600, 2400, 3000, 2400, 2600, 2400, 3200, 3000, 4200];

const FACTS_184 = [
  "Digital service purchased 14 days before cancellation",
  "Approximately 40% of the entitlement consumed",
  "No usage-based exclusion in the purchase terms",
  "Cancellation inside the stated 30-day window",
];

const FACTS_392 = [
  "Monthly recurring plan, cancelled 14 days into the cycle",
  "Approximately 40% of the cycle entitlement consumed",
  "No usage-based exclusion in the plan terms",
  "Cancellation inside the stated window",
];

const RETRIEVED = [
  { id: "00184", sim: 96, verdict: "APPROVED", status: "UPHELD", outcome: "FOLLOWED" },
  { id: "00117", sim: 91, verdict: "REJECTED", status: "UPHELD", outcome: "CITED" },
  { id: "00263", sim: 88, verdict: "APPROVED", status: "UPHELD", outcome: "DISTINGUISHED" },
] as const;

const MODELS = ["Claude Opus 4", "GPT-5", "Gemini 2.5 Pro", "Llama 4", "Mistral Large 3"];
const VOTES = ["FOLLOW", "FOLLOW", "FOLLOW", "DISTINGUISH", "FOLLOW"];

export function LiveDemo() {
  const { index, playing, atEnd, next, prev, goTo, reset, toggle } = useSequencer(STAGES.length, {
    durations: DURATIONS,
  });

  return (
    <div className="panel overflow-hidden rounded-[10px]">
      {/* ---------- header ---------- */}
      <div className="flex items-center justify-between gap-4 border-b border-white/[0.08] px-5 py-3 md:px-6">
        <div className="flex items-center gap-3">
          <span className="h-[5px] w-[5px] rounded-full bg-copper" />
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-stone">
            Demo · case #0184 → #0392
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="hidden font-mono text-[10px] tabular-nums tracking-[0.14em] text-muted sm:inline">
            {String(index + 1).padStart(2, "0")} / {String(STAGES.length).padStart(2, "0")}
          </span>
          <button
            onClick={prev}
            aria-label="Previous step"
            className="flex h-[28px] items-center rounded-[6px] border border-white/[0.12] px-3 font-mono text-[10px] text-stone transition-colors hover:text-paper"
          >
            Prev
          </button>
          <button
            onClick={toggle}
            aria-label={playing ? "Pause" : "Play"}
            className="flex h-[26px] w-[26px] items-center justify-center rounded-[6px] border border-white/[0.12] text-stone transition-colors hover:border-copper/50 hover:text-copper"
          >
            {playing ? <Pause size={11} strokeWidth={1.5} /> : <Play size={11} strokeWidth={1.5} />}
          </button>
          <button
            onClick={reset}
            aria-label="Restart"
            className="flex h-[26px] w-[26px] items-center justify-center rounded-[6px] border border-white/[0.12] text-stone transition-colors hover:border-copper/50 hover:text-copper"
          >
            <RotateCcw size={11} strokeWidth={1.5} />
          </button>
        </div>
      </div>

      {/* progress hairline */}
      <div className="h-px w-full bg-white/[0.06]">
        <motion.div
          className="h-px bg-copper/80"
          animate={{ width: `${((index + 1) / STAGES.length) * 100}%` }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      <div className="grid md:grid-cols-12">
        {/* ---------- stage ---------- */}
        <div className="min-h-[430px] p-5 md:col-span-8 md:min-h-[470px] md:p-8">
          <AnimatePresence mode="wait">
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.32, ease: [0.16, 1, 0.3, 1] }}
            >
              {index === 0 ? <StageCase title="CASE #0184" facts={FACTS_184} tag="PENDING" /> : null}

              {index === 1 ? (
                <div>
                  <CaseHeader title="CASE #0184" tag="FINALISED" />
                  <div className="mt-8">
                    <Label>Verdict</Label>
                    <VerdictLock verdict="APPROVED" />
                    <p className="mt-5 font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                      Finality 02 Apr 2026 · 11:24 UTC · panel of 5
                    </p>
                  </div>
                </div>
              ) : null}

              {index === 2 ? <HoldingCard id="00184" /> : null}

              {index === 3 ? <IndexedStage /> : null}

              {index === 4 ? <StageCase title="CASE #0392" facts={FACTS_392} tag="NEW" /> : null}

              {index === 5 ? <PrecedentSearch /> : null}

              {index === 6 ? <RelatedHoldings /> : null}

              {index === 7 ? <Suggestion /> : null}

              {index === 8 ? <Consensus /> : null}
            </motion.div>
          </AnimatePresence>
        </div>

        {/* ---------- rail ---------- */}
        <div className="border-t border-white/[0.08] p-5 md:col-span-4 md:border-l md:border-t-0 md:p-6">
          <Label>Sequence</Label>
          <ol className="mt-4">
            {STAGES.map((s, i) => (
              <li key={s.id}>
                <button
                  onClick={() => goTo(i)}
                  className={cx(
                    "group flex w-full items-center gap-3 border-b border-white/[0.05] py-[9px] text-left last:border-b-0",
                  )}
                >
                  <span
                    className={cx(
                      "font-mono text-[10px] tabular-nums",
                      i === index ? "text-copper" : i < index ? "text-stone" : "text-muted",
                    )}
                  >
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <span
                    className={cx(
                      "flex-1 text-[12.5px] transition-colors duration-200",
                      i === index ? "text-paper" : "text-stone group-hover:text-paper",
                    )}
                  >
                    {s.label}
                  </span>
                  <span
                    className={cx(
                      "h-[3px] w-[3px] rounded-full transition-colors",
                      i === index ? "bg-copper" : i < index ? "bg-white/25" : "bg-white/10",
                    )}
                  />
                </button>
              </li>
            ))}
          </ol>

          <div className="mt-6 border-t border-white/[0.08] pt-5">
            <p className="font-mono text-[10px] uppercase leading-[1.7] tracking-[0.12em] text-muted">
              Simulated sequence.
              <br />
              Records are illustrative, not live GenLayer data.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* stage pieces                                                         */
/* ------------------------------------------------------------------ */
function CaseHeader({ title, tag }: { title: string; tag: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="font-mono text-[13px] uppercase tracking-[0.14em] text-paper">{title}</span>
      <MetaTag tone={tag === "PENDING" ? "neutral" : tag === "NEW" ? "blue" : "green"}>{tag}</MetaTag>
    </div>
  );
}

function StageCase({ title, facts, tag }: { title: string; facts: string[]; tag: string }) {
  return (
    <div>
      <CaseHeader title={title} tag={tag} />
      <div className="mt-6 grid gap-6 md:grid-cols-2">
        <div>
          <Label>Issue</Label>
          <p className="mt-2 text-[14px] leading-[1.6] text-paper">
            Cancellation after partial service delivery
          </p>
          <div className="mt-5">
            <Label>Contract class</Label>
            <p className="mt-2 font-mono text-[12px] text-paper">RefundArbiter</p>
          </div>
        </div>
        <div>
          <Label>Material facts</Label>
          <ul className="mt-2 space-y-[7px]">
            {facts.map((f, i) => (
              <motion.li
                key={f}
                initial={{ opacity: 0, x: -4 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: 0.1 + i * 0.09, duration: 0.35 }}
                className="flex gap-2 text-[13px] leading-[1.5] text-stone"
              >
                <span className="mt-[7px] h-px w-3 shrink-0 bg-white/20" />
                {f}
              </motion.li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function VerdictLock({ verdict }: { verdict: "APPROVED" | "REJECTED" }) {
  return (
    <div className="mt-3 inline-block">
      <motion.div
        initial={{ opacity: 0, y: 6, letterSpacing: "0.06em" }}
        animate={{ opacity: 1, y: 0, letterSpacing: "0.02em" }}
        transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        className={cx(
          "display text-[44px] leading-none md:text-[56px]",
          verdict === "APPROVED" ? "text-verdict" : "text-dissent",
        )}
      >
        {verdict}
      </motion.div>
      <motion.div
        initial={{ scaleX: 0 }}
        animate={{ scaleX: 1 }}
        transition={{ duration: 0.6, delay: 0.2, ease: [0.16, 1, 0.3, 1] }}
        className="mt-3 h-px origin-left bg-copper/70"
      />
    </div>
  );
}

function HoldingCard({ id }: { id: string }) {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="font-mono text-[13px] uppercase tracking-[0.14em] text-copper">
          HOLDING #{id}
        </span>
        <MetaTag tone="copper">Created</MetaTag>
      </div>
      <div className="mt-6 border-t border-white/[0.08] pt-5">
        <Label>Issue</Label>
        <p className="mt-2 max-w-[52ch] text-[14px] leading-[1.6] text-paper">
          Can a customer receive a full refund after partially consuming a digital service?
        </p>
      </div>
      <div className="mt-5 border-t border-white/[0.08] pt-5">
        <Label>Ratio</Label>
        <p className="mt-2 max-w-[56ch] text-[13.5px] leading-[1.7] text-stone">
          Where a digital service has been materially consumed before cancellation but the purchase
          terms contain no usage-based exclusion, refund eligibility is preserved and the refund is
          reduced pro rata to the unconsumed portion.
        </p>
      </div>
      <div className="mt-5 flex flex-wrap gap-2 border-t border-white/[0.08] pt-5">
        {["PARTIAL_CONSUMPTION", "NO_USAGE_EXCLUSION", "IN_WINDOW"].map((c) => (
          <MetaTag key={c}>{c}</MetaTag>
        ))}
      </div>
    </div>
  );
}

function IndexedStage() {
  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="font-mono text-[13px] uppercase tracking-[0.14em] text-paper">
          HOLDING #00184
        </span>
        <MetaTag tone="green">Indexed</MetaTag>
      </div>

      <div className="mt-7 space-y-[10px] font-mono text-[11px] uppercase tracking-[0.12em]">
        {[
          { k: "Embedding", v: "all-MiniLM-L6-v2 · 384d" },
          { k: "Store", v: "VecDB · HoldingRegistry" },
          { k: "Authority", v: "Pending appeal window" },
          { k: "On-chain ref", v: "0xA184…F0C2" },
        ].map((r, i) => (
          <motion.div
            key={r.k}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.08 * i, duration: 0.35 }}
            className="flex items-center justify-between border-b border-white/[0.06] pb-[10px]"
          >
            <span className="text-muted">{r.k}</span>
            <span className="text-paper">{r.v}</span>
          </motion.div>
        ))}
      </div>

      <motion.p
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.5 }}
        className="mt-6 text-[13.5px] leading-[1.7] text-stone"
      >
        Retrieval runs inside GenVM, so every validator recomputes it. The index cannot be poisoned
        by whoever is asking the question.
      </motion.p>
    </div>
  );
}

function PrecedentSearch() {
  const [n, setN] = useState(0);
  const total = CORPUS.holdingsIndexed;

  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const dur = 1500;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      setN(Math.floor(p * total));
      if (p < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [total]);

  return (
    <div>
      <Label>Retrieving precedent</Label>
      <p className="mt-3 text-[15px] text-paper">Searching {fmtNum(total)} holdings…</p>
      <div className="mt-5 h-px w-full overflow-hidden bg-white/[0.07]">
        <motion.div
          className="h-px w-1/3 bg-copper"
          animate={{ x: ["-100%", "300%"] }}
          transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
        />
      </div>
      <p className="mt-4 font-mono text-[11px] tabular-nums text-muted">
        {fmtNum(n)} / {fmtNum(total)} compared · k = 3
      </p>
    </div>
  );
}

function RelatedHoldings() {
  return (
    <div>
      <div className="flex items-center justify-between">
        <Label>Related holdings</Label>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-copper">
          3 found
        </span>
      </div>

      <div className="mt-5">
        {RETRIEVED.map((h, i) => (
          <motion.div
            key={h.id}
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 + i * 0.14, duration: 0.4 }}
            className="border-b border-white/[0.06] py-4 last:border-b-0"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <span className="font-mono text-[12px] tracking-[0.08em] text-paper">#{h.id}</span>
                <VerdictTag verdict={h.verdict} />
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                  {h.status}
                </span>
              </div>
              <span
                className={cx(
                  "font-mono text-[10px] uppercase tracking-[0.14em]",
                  h.outcome === "FOLLOWED"
                    ? "text-verdict"
                    : h.outcome === "DISTINGUISHED"
                      ? "text-dissent"
                      : "text-info",
                )}
              >
                {h.outcome}
              </span>
            </div>
            <div className="mt-3 flex items-center gap-4">
              <div className="h-[3px] flex-1 bg-white/[0.06]">
                <motion.div
                  className="h-[3px] bg-copper/80"
                  initial={{ width: 0 }}
                  animate={{ width: `${h.sim}%` }}
                  transition={{ delay: 0.25 + i * 0.14, duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
              <span className="w-[64px] text-right font-mono text-[11px] tabular-nums text-stone">
                {h.sim}% similarity
              </span>
            </div>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

function Suggestion() {
  return (
    <div>
      <Label>Precedent suggestion</Label>
      <motion.div
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45 }}
        className="mt-4 inline-flex items-center gap-3 border border-copper/30 bg-copper/[0.05] px-4 py-[10px]"
      >
        <span className="font-mono text-[12px] uppercase tracking-[0.14em] text-copper">
          Follow holding #00184
        </span>
      </motion.div>

      <div className="mt-7">
        <Label>Panel reasoning</Label>
        <div className="mt-3 space-y-[10px]">
          {[
            "Facts are materially identical to #00184 — same consumption profile, no usage exclusion.",
            "#00117 is cited for the opposite delivery posture, which is absent here.",
            "#00263 is distinguished: it turns on non-delivery, which does not arise.",
          ].map((line, i) => (
            <motion.div
              key={line}
              initial={{ opacity: 0, x: -4 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: 0.2 + i * 0.22, duration: 0.4 }}
              className="flex gap-3"
            >
              <span className="mt-[9px] h-px w-3 shrink-0 bg-copper/50" />
              <p className="text-[13.5px] leading-[1.65] text-stone">{line}</p>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

function Consensus() {
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    if (revealed >= MODELS.length) return;
    const t = setTimeout(() => setRevealed((r) => r + 1), revealed === 0 ? 250 : 520);
    return () => clearTimeout(t);
  }, [revealed]);

  return (
    <div>
      <Label>Panel review</Label>
      <div className="mt-4">
        {MODELS.map((m, i) => {
          const state = i < revealed ? "REVIEWED" : i === revealed ? "REVIEWING" : "QUEUED";
          return (
            <div
              key={m}
              className="flex items-center justify-between border-b border-white/[0.06] py-[11px]"
            >
              <div className="flex items-center gap-3">
                <span className="font-mono text-[10px] tabular-nums text-muted">
                  {String(i + 1).padStart(2, "0")}
                </span>
                <span className="text-[13px] text-paper">{m}</span>
              </div>
              <div className="flex items-center gap-4">
                <AnimatePresence>
                  {state === "REVIEWED" ? (
                    <motion.span
                      initial={{ opacity: 0, x: 6 }}
                      animate={{ opacity: 1, x: 0 }}
                      className={cx(
                        "font-mono text-[10px] uppercase tracking-[0.14em]",
                        VOTES[i] === "FOLLOW" ? "text-verdict" : "text-dissent",
                      )}
                    >
                      {VOTES[i] === "FOLLOW" ? "Follow #00184" : "Distinguish #00263"}
                    </motion.span>
                  ) : null}
                </AnimatePresence>
                <span
                  className={cx(
                    "font-mono text-[10px] uppercase tracking-[0.14em]",
                    state === "REVIEWED"
                      ? "text-stone"
                      : state === "REVIEWING"
                        ? "animate-pulseSoft text-copper"
                        : "text-muted opacity-40",
                  )}
                >
                  {state}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {revealed >= MODELS.length ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5 }}
          className="mt-7 flex flex-wrap items-end justify-between gap-6 border-t border-white/[0.08] pt-6"
        >
          <div>
            <Label>Consensus</Label>
            <div className="display mt-2 text-[40px] leading-none tabular-nums text-paper">
              4 <span className="text-muted">/ 5</span>
            </div>
            <p className="mt-3 font-mono text-[11px] uppercase tracking-[0.14em] text-verdict">
              Followed
            </p>
          </div>
          <div className="text-right">
            <Label>Verdict</Label>
            <div className="display mt-2 text-[32px] leading-none text-verdict">APPROVED</div>
            <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              Holding #00392 created
            </p>
          </div>
        </motion.div>
      ) : null}
    </div>
  );
}
