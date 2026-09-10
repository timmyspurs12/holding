"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { RotateCcw, ArrowRight } from "lucide-react";
import Link from "next/link";
import { getCase, getHolding, CORPUS, fmtNum } from "@/lib/data";
import { Label, VerdictTag, MetaTag, cx } from "./ui/primitives";

const SCENARIOS = [
  { id: "0392", label: "Recurring plan cancellation", hint: "40% consumed · mid-cycle" },
  { id: "0417", label: "Full delivery before cancellation", hint: "100% delivered · then cancelled" },
  { id: "0731", label: "Access lost to account breach", hint: "Purchaser-caused loss of access" },
  { id: "1042", label: "SLA missed, third-party fault", hint: "Upstream dependency outage" },
];

type Stage = "idle" | "retrieving" | "retrieved" | "voting" | "done";

export function PrecedentConsole() {
  const [scenario, setScenario] = useState("0392");
  const [k, setK] = useState(3);
  const [stage, setStage] = useState<Stage>("idle");
  const [revealed, setRevealed] = useState(0);
  const [count, setCount] = useState(0);

  const record = getCase(scenario)!;
  const retrieved = useMemo(() => record.retrieved.slice(0, k), [record, k]);
  const nearest = retrieved[0] ? getHolding(retrieved[0].holdingId) : undefined;

  const reset = () => {
    setStage("idle");
    setRevealed(0);
    setCount(0);
  };

  /* retrieval animation */
  useEffect(() => {
    if (stage !== "retrieving") return;
    const start = performance.now();
    const dur = 1300;
    let raf = 0;
    const tick = (t: number) => {
      const p = Math.min(1, (t - start) / dur);
      setCount(Math.floor(p * CORPUS.holdingsIndexed));
      if (p < 1) raf = requestAnimationFrame(tick);
      else setStage("retrieved");
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [stage]);

  useEffect(() => {
    if (stage !== "retrieved") return;
    const t = setTimeout(() => setStage("voting"), 900);
    return () => clearTimeout(t);
  }, [stage]);

  useEffect(() => {
    if (stage !== "voting") return;
    if (revealed >= record.panel.length) {
      setStage("done");
      return;
    }
    const t = setTimeout(() => setRevealed((r) => r + 1), revealed === 0 ? 200 : 380);
    return () => clearTimeout(t);
  }, [stage, revealed, record.panel.length]);

  const followVotes = record.panel.filter((p) => p.vote === "FOLLOW" && p.reviewed).length;
  const reviewed = record.panel.filter((p) => p.reviewed).length;

  return (
    <div className="grid gap-px overflow-hidden rounded-[10px] border border-white/[0.08] bg-white/[0.06] lg:grid-cols-12">
      {/* ---------------- input ---------------- */}
      <div className="bg-obsidian p-6 lg:col-span-5 lg:p-8">
        <Label>Case</Label>
        <div className="mt-4">
          {SCENARIOS.map((s) => (
            <button
              key={s.id}
              onClick={() => {
                setScenario(s.id);
                reset();
              }}
              className={cx(
                "group block w-full border-b border-white/[0.06] py-3 text-left last:border-b-0",
              )}
            >
              <div className="flex items-center gap-3">
                <span
                  className={cx(
                    "h-[5px] w-[5px] rounded-full transition-colors",
                    scenario === s.id ? "bg-copper" : "bg-white/15",
                  )}
                />
                <span
                  className={cx(
                    "flex-1 text-[13.5px] transition-colors",
                    scenario === s.id ? "text-paper" : "text-stone group-hover:text-paper",
                  )}
                >
                  {s.label}
                </span>
              </div>
              <p className="mt-1 pl-[20px] font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                {s.hint}
              </p>
            </button>
          ))}
        </div>

        <div className="mt-8">
          <Label>Material facts</Label>
          <ul className="mt-4 space-y-[9px]">
            {record.facts.map((f) => (
              <li key={f} className="flex gap-3">
                <span className="mt-[8px] h-px w-3 shrink-0 bg-white/20" />
                <span className="text-[13px] leading-[1.55] text-stone">{f}</span>
              </li>
            ))}
          </ul>
        </div>

        <div className="mt-8 flex items-center gap-4">
          <div>
            <Label>k</Label>
            <div className="mt-2 flex gap-1">
              {[1, 3, 5].map((n) => (
                <button
                  key={n}
                  onClick={() => {
                    setK(n);
                    reset();
                  }}
                  className={cx("chip", k === n && "chip-active")}
                >
                  {n}
                </button>
              ))}
            </div>
          </div>
          <div className="ml-auto">
            <button
              onClick={() => {
                reset();
                setStage("retrieving");
              }}
              disabled={stage === "retrieving" || stage === "voting"}
              className={cx(
                "rounded-[8px] px-4 py-[9px] text-[13px] font-medium transition-all duration-200",
                stage === "retrieving" || stage === "voting"
                  ? "cursor-not-allowed border border-white/[0.1] text-muted"
                  : "bg-copper text-obsidian hover:brightness-110",
              )}
            >
              {stage === "idle" ? "Run the panel" : stage === "done" ? "Run again" : "Running…"}
            </button>
          </div>
        </div>

        <div className="mt-8 overflow-hidden rounded-[8px] border border-white/[0.08] bg-ink">
          <div className="border-b border-white/[0.06] px-4 py-2">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              What the contract calls
            </span>
          </div>
          <pre className="overflow-x-auto p-4 font-mono text-[12px] leading-[1.8] text-stone">
{`get_precedent(
  case_digest = case_digest,
  domain      = "${record.domainSlug}",
  k           = ${k},
)`}
          </pre>
        </div>

        <button
          onClick={reset}
          className="mt-4 inline-flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
        >
          <RotateCcw size={11} strokeWidth={1.5} />
          Reset
        </button>
      </div>

      {/* ---------------- output ---------------- */}
      <div className="bg-ink p-6 lg:col-span-7 lg:p-8">
        <div className="flex items-center justify-between">
          <Label>{stage === "idle" ? "Idle" : stage === "done" ? "Final" : stage}</Label>
          <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
            Demo · simulated
          </span>
        </div>

        {/* idle */}
        {stage === "idle" ? (
          <div className="mt-16 text-center">
            <p className="display text-[22px] leading-[1.4] text-paper">
              Ask HOLDING what has already been decided.
            </p>
            <p className="mx-auto mt-4 max-w-[42ch] text-[13px] leading-[1.7] text-stone">
              Pick a case and run the panel. Retrieval runs inside GenVM, so every validator
              recomputes the same result — the panel cannot be shown a curated set of precedents.
            </p>
          </div>
        ) : null}

        {/* retrieving */}
        {stage === "retrieving" ? (
          <div className="mt-16">
            <Label>Retrieving precedent</Label>
            <p className="mt-3 text-[15px] text-paper">
              Searching {fmtNum(CORPUS.holdingsIndexed)} holdings…
            </p>
            <div className="mt-5 h-px w-full overflow-hidden bg-white/[0.07]">
              <motion.div
                className="h-px w-1/3 bg-copper"
                animate={{ x: ["-100%", "300%"] }}
                transition={{ duration: 1.1, repeat: Infinity, ease: "linear" }}
              />
            </div>
            <p className="mt-4 font-mono text-[11px] tabular-nums text-muted">
              {fmtNum(count)} / {fmtNum(CORPUS.holdingsIndexed)} compared · k = {k}
            </p>
          </div>
        ) : null}

        {/* retrieved + voting + done */}
        {stage !== "idle" && stage !== "retrieving" ? (
          <div className="mt-8">
            <div className="flex items-center justify-between">
              <Label>Precedent retrieved</Label>
              <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-copper">
                {retrieved.length} found
              </span>
            </div>

            <div className="mt-4">
              {retrieved.map((r, i) => {
                const h = getHolding(r.holdingId)!;
                return (
                  <motion.div
                    key={r.holdingId}
                    initial={{ opacity: 0, y: 6 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ delay: i * 0.08, duration: 0.35 }}
                    className="border-b border-white/[0.06] py-4"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <Link
                          href={`/holdings/${h.id}`}
                          className="font-mono text-[12px] tracking-[0.1em] text-paper hover:text-copper"
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
                        <motion.div
                          className="h-[3px] bg-copper/80"
                          initial={{ width: 0 }}
                          animate={{ width: `${r.similarity}%` }}
                          transition={{ delay: 0.15 + i * 0.08, duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
                        />
                      </div>
                      <span className="w-[64px] text-right font-mono text-[11px] tabular-nums text-stone">
                        {r.similarity}%
                      </span>
                    </div>
                    <p className="mt-2 text-[12.5px] leading-[1.6] text-muted">{r.note}</p>
                  </motion.div>
                );
              })}
            </div>

            {/* panel */}
            <div className="mt-10">
              <div className="flex items-center justify-between">
                <Label>Panel review</Label>
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                  {Math.min(revealed, reviewed)} / {record.panel.length} reviewed
                </span>
              </div>

              <div className="mt-4">
                {record.panel.map((m, i) => {
                  const state =
                    i < revealed && m.reviewed
                      ? "REVIEWED"
                      : i === revealed
                        ? "REVIEWING"
                        : "QUEUED";
                  return (
                    <div
                      key={m.index}
                      className="flex items-center justify-between gap-4 border-b border-white/[0.06] py-[10px]"
                    >
                      <div className="flex min-w-0 items-center gap-3">
                        <span className="font-mono text-[10px] tabular-nums text-muted">
                          {String(m.index).padStart(2, "0")}
                        </span>
                        <span className="truncate text-[13px] text-paper">{m.model}</span>
                      </div>
                      <div className="flex shrink-0 items-center gap-4">
                        {state === "REVIEWED" ? (
                          <span
                            className={cx(
                              "font-mono text-[10px] uppercase tracking-[0.12em]",
                              m.vote === "FOLLOW" ? "text-verdict" : "text-dissent",
                            )}
                          >
                            {m.vote === "FOLLOW" ? "Follow" : "Distinguish"}
                          </span>
                        ) : null}
                        <span
                          className={cx(
                            "w-[74px] text-right font-mono text-[10px] uppercase tracking-[0.12em]",
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
            </div>

            {/* verdict */}
            <AnimatePresence>
              {stage === "done" ? (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className="mt-10 border-t border-white/[0.08] pt-8"
                >
                  {record.materialDifference ? (
                    <div>
                      <div className="flex items-center gap-3">
                        <span className="h-[6px] w-[6px] rotate-45 bg-dissent" />
                        <Label>Material difference</Label>
                      </div>
                      <p className="display mt-3 max-w-[52ch] text-[19px] leading-[1.45] text-paper">
                        {record.materialDifference}
                      </p>
                      {record.distinguishment ? (
                        <p className="mt-5 max-w-[54ch] border-l border-copper/40 pl-4 text-[13.5px] leading-[1.7] text-stone">
                          “{record.distinguishment}”
                        </p>
                      ) : null}
                    </div>
                  ) : (
                    <div>
                      <Label>Suggestion followed</Label>
                      <p className="mt-3 max-w-[52ch] text-[13.5px] leading-[1.7] text-stone">
                        {nearest
                          ? `The panel ruled consistently with Holding #${nearest.id}. No distinguishment was written, because no material difference was found.`
                          : "No precedent was available, so the panel ruled on the terms as written."}
                      </p>
                    </div>
                  )}

                  <div className="mt-8 flex flex-wrap items-end justify-between gap-8">
                    <div>
                      <Label>Consensus</Label>
                      <div className="display mt-2 text-[38px] leading-none tabular-nums text-paper">
                        {followVotes} <span className="text-muted">/ {record.panel.length}</span>
                      </div>
                    </div>
                    <div>
                      <Label>Verdict</Label>
                      <div className="mt-2">
                        {record.verdict ? (
                          <VerdictTag verdict={record.verdict} size="lg" />
                        ) : (
                          <MetaTag tone="copper">Pending</MetaTag>
                        )}
                      </div>
                    </div>
                    <div className="text-right">
                      <Label>Next</Label>
                      {record.resultingHolding ? (
                        <Link
                          href={`/holdings/${record.resultingHolding}`}
                          className="mt-2 inline-flex items-center gap-2 font-mono text-[12px] uppercase tracking-[0.12em] text-copper"
                        >
                          Holding #{record.resultingHolding}
                          <ArrowRight size={11} strokeWidth={1.5} />
                        </Link>
                      ) : (
                        <p className="mt-2 font-mono text-[12px] uppercase tracking-[0.12em] text-stone">
                          Awaiting finality
                        </p>
                      )}
                    </div>
                  </div>
                </motion.div>
              ) : null}
            </AnimatePresence>
          </div>
        ) : null}
      </div>
    </div>
  );
}
