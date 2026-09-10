"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ArrowRight } from "lucide-react";
import { cx, Label, VerdictTag, MetaTag } from "../ui/primitives";
import { useSequencer } from "./useSequencer";

const LEFT = [
  { text: "Digital service", match: true },
  { text: "Partial usage before cancellation", match: true },
  { text: "Cancellation inside the stated window", match: true },
  { text: "No usage-based exclusion in the terms", match: true },
];

const RIGHT = [
  { text: "Digital service", match: true },
  { text: "Partial usage before cancellation", match: true },
  { text: "Cancellation inside the stated window", match: true },
  { text: "Service fully delivered before cancellation", match: false },
];

export function DistinguishmentDemo() {
  const { index, playing, atEnd, next, reset, goTo } = useSequencer(4, {
    durations: [2800, 2200, 3400, 4200],
    gate: (i) => i === 1,
  });

  const showDifference = index >= 1;
  const revealed = index >= 2;

  return (
    <div className="panel overflow-hidden rounded-[10px]">
      <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-3 md:px-6">
        <div className="flex items-center gap-3">
          <span className="h-[5px] w-[5px] rounded-full bg-copper" />
          <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-stone">
            Demo · case #0417 vs holding #00184
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="font-mono text-[10px] tabular-nums tracking-[0.14em] text-muted">
            {String(index + 1).padStart(2, "0")} / 04
          </span>
          <button
            onClick={reset}
            className="flex h-[28px] items-center rounded-[6px] border border-white/[0.12] px-3 font-mono text-[10px] text-stone transition-colors hover:text-paper"
          >
            Reset
          </button>
        </div>
      </div>

      <div className="h-px w-full bg-white/[0.06]">
        <motion.div
          className="h-px bg-copper/80"
          animate={{ width: `${((index + 1) / 4) * 100}%` }}
          transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      <div className="p-5 md:p-8">
        {/* ---------- match header ---------- */}
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <Label>Precedent found</Label>
            <div className="mt-2 flex items-center gap-3">
              <span className="font-mono text-[13px] tracking-[0.1em] text-paper">#00184</span>
              <VerdictTag verdict="APPROVED" />
            </div>
          </div>
          <div className="text-right">
            <Label>Similarity</Label>
            <div className="display mt-1 text-[38px] leading-none tabular-nums text-copper">96%</div>
          </div>
        </div>

        {/* ---------- comparison ---------- */}
        <div className="mt-8 grid gap-8 md:grid-cols-2 md:gap-10">
          <div>
            <Label>Holding #00184 · decided 02 Apr 2026</Label>
            <ul className="mt-4 space-y-[11px]">
              {LEFT.map((f, i) => (
                <li key={i} className="flex items-start gap-3">
                  <span className="mt-[8px] font-mono text-[10px] text-verdict">✓</span>
                  <span className="text-[13.5px] leading-[1.5] text-stone">{f.text}</span>
                </li>
              ))}
            </ul>
          </div>

          <div>
            <Label>Case #0417 · before the panel</Label>
            <ul className="mt-4 space-y-[11px]">
              {RIGHT.map((f, i) => (
                <li key={i} className="relative">
                  <motion.div
                    animate={{
                      backgroundColor: !f.match && showDifference ? "rgba(201,107,98,0.09)" : "rgba(0,0,0,0)",
                    }}
                    transition={{ duration: 0.5 }}
                    className="flex items-start gap-3 rounded-[4px] px-2 py-[2px] -mx-2"
                  >
                    <span
                      className={cx(
                        "mt-[8px] font-mono text-[10px]",
                        f.match ? "text-verdict" : "text-dissent",
                      )}
                    >
                      {f.match ? "✓" : "◆"}
                    </span>
                    <span
                      className={cx(
                        "text-[13.5px] leading-[1.5]",
                        f.match ? "text-stone" : "text-paper",
                      )}
                    >
                      {f.text}
                    </span>
                  </motion.div>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* ---------- the gate ---------- */}
        <div className="mt-9 border-t border-white/[0.08] pt-7">
          <AnimatePresence mode="wait">
            {index === 0 ? (
              <motion.div
                key="s0"
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                className="flex items-center gap-3"
              >
                <span className="h-[5px] w-[5px] animate-pulseSoft rounded-full bg-copper" />
                <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-stone">
                  Comparing facts against the nearest holding…
                </span>
              </motion.div>
            ) : null}

            {index === 1 ? (
              <motion.div
                key="s1"
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.4 }}
                className="flex flex-wrap items-center justify-between gap-5"
              >
                <div className="flex items-center gap-3">
                  <span className="h-[6px] w-[6px] rotate-45 bg-dissent" />
                  <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-dissent">
                    Material difference detected
                  </span>
                </div>
                <button
                  onClick={next}
                  className="group inline-flex items-center gap-2 rounded-[8px] border border-copper/40 bg-copper/[0.06] px-4 py-[9px] text-[13px] text-copper transition-all duration-200 hover:border-copper hover:bg-copper/[0.12]"
                >
                  Why different?
                  <ArrowRight
                    size={13}
                    strokeWidth={1.5}
                    className="transition-transform duration-200 group-hover:translate-x-[2px]"
                  />
                </button>
              </motion.div>
            ) : null}

            {revealed ? (
              <motion.div key="s2" initial={{ opacity: 0 }} animate={{ opacity: 1 }}>
                <Label>Distinguishment</Label>
                <motion.p
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  className="display mt-3 max-w-[58ch] text-[22px] leading-[1.42] text-paper md:text-[26px]"
                >
                  “Unlike Holding #00184, the service was already fully delivered before
                  cancellation.”
                </motion.p>

                {index >= 3 ? (
                  <motion.div
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.5, delay: 0.15 }}
                    className="mt-9 grid gap-6 border-t border-white/[0.08] pt-7 md:grid-cols-3"
                  >
                    <div>
                      <Label>Disposition</Label>
                      <p className="mt-3 font-mono text-[15px] uppercase tracking-[0.1em] text-dissent">
                        Distinguished
                      </p>
                    </div>
                    <div>
                      <Label>New verdict</Label>
                      <div className="mt-2">
                        <VerdictTag verdict="REJECTED" size="lg" />
                      </div>
                    </div>
                    <div>
                      <Label>Recorded</Label>
                      <p className="mt-3 font-mono text-[15px] uppercase tracking-[0.1em] text-copper">
                        Holding #00417
                      </p>
                    </div>
                  </motion.div>
                ) : null}

                {index >= 3 ? (
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.4 }}
                    className="mt-8"
                  >
                    <button
                      onClick={reset}
                      className="font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
                    >
                      Replay
                    </button>
                  </motion.div>
                ) : null}
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      </div>

      {/* stage dots */}
      <div className="flex items-center gap-2 border-t border-white/[0.08] px-5 py-3 md:px-6">
        {["Found", "Difference", "Reason", "New holding"].map((s, i) => (
          <button
            key={s}
            onClick={() => goTo(i)}
            className="flex items-center gap-2 py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] transition-colors"
          >
            <span
              className={cx(
                "h-[3px] w-[14px]",
                i === index ? "bg-copper" : i < index ? "bg-white/30" : "bg-white/10",
              )}
            />
            <span className={i === index ? "text-paper" : "text-muted"}>{s}</span>
          </button>
        ))}
        <span className="ml-auto font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          {playing ? "Auto" : atEnd ? "Complete" : "Awaiting input"}
        </span>
      </div>
    </div>
  );
}
