"use client";

import { useRef, useState, useEffect } from "react";
import { motion, useScroll, useSpring, useMotionValueEvent, AnimatePresence } from "framer-motion";
import { cx, Label, VerdictTag } from "./ui/primitives";

type Step = {
  kind: "CASE" | "HOLDING" | "CITATION" | "RETRIEVAL" | "PANEL" | "DISTINCTION";
  title: string;
  detail: string;
  meta?: string;
  verdict?: "APPROVED" | "REJECTED" | "PARTIAL";
  tags?: string[];
};

const STEPS: Step[] = [
  {
    kind: "CASE",
    title: "CASE 0184",
    detail: "Refund eligibility · digital service · partial consumption",
    meta: "Panel of 5 · different models",
  },
  {
    kind: "HOLDING",
    title: "HOLDING #00184",
    detail: "Issue, facts, reason codes and ratio written to the registry",
    meta: "Finality 02 Apr 2026",
    verdict: "APPROVED",
  },
  {
    kind: "CITATION",
    title: "CITATION ACCUMULATES",
    detail: "Six later holdings cite it; authority weighting rises",
    meta: "Appeal: UPHELD",
  },
  {
    kind: "CASE",
    title: "CASE 0392",
    detail: "Recurring plan · cancelled mid-cycle · 40% consumed",
    meta: "Materially identical facts",
  },
  {
    kind: "RETRIEVAL",
    title: "PRECEDENT RETRIEVED",
    detail: "#00184 · 96% · #00117 · 91% · #00263 · 88%",
    meta: "Consensus-verified k-NN, inside GenVM",
  },
  {
    kind: "PANEL",
    title: "PANEL FOLLOWS",
    detail: "Four of five validators follow the nearest holding",
    meta: "4 / 5 · FOLLOWED",
  },
  {
    kind: "DISTINCTION",
    title: "CASE 0417 DISTINGUISHES",
    detail: "Full delivery before cancellation · one material difference",
    meta: "5 / 5 · DISTINGUISHED",
    verdict: "REJECTED",
  },
  {
    kind: "HOLDING",
    title: "HOLDING #00417",
    detail: "The distinguishment is recorded and joins the chain",
    meta: "Precedent extended without being erased",
    verdict: "REJECTED",
  },
];

export function PrecedentMemory() {
  const ref = useRef<HTMLDivElement>(null);
  const [active, setActive] = useState(0);
  const [mobile, setMobile] = useState(false);

  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ["start 0.75", "end 0.65"],
  });
  const progress = useSpring(scrollYProgress, { stiffness: 120, damping: 30, mass: 0.4 });

  useMotionValueEvent(progress, "change", (v) => {
    const idx = Math.min(STEPS.length - 1, Math.max(0, Math.floor(v * STEPS.length)));
    setActive(idx);
  });

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 767px)");
    const update = () => setMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, []);

  return (
    <div ref={ref} className="relative">
      {/* ---------------- desktop: vertical chain ---------------- */}
      <div className="relative hidden md:block" style={{ height: `${STEPS.length * 46}vh` }}>
        <div className="sticky top-[14vh]">
          <div className="grid grid-cols-12 items-start gap-10">
            <div className="col-span-4">
              <Label>The chain</Label>
              <h3 className="display mt-4 text-[30px] leading-[1.16] text-paper">
                Memory, accumulating.
              </h3>
              <p className="mt-5 max-w-[36ch] text-[14px] leading-[1.7] text-stone">
                A decision is adjudicated once. A holding is used forever. Scroll to watch one
                verdict become the authority the next panel has to answer.
              </p>
              <div className="mt-8 flex items-baseline gap-3">
                <span className="display text-[40px] leading-none tabular-nums text-copper">
                  {String(active + 1).padStart(2, "0")}
                </span>
                <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted">
                  / {String(STEPS.length).padStart(2, "0")} · {STEPS[active].kind}
                </span>
              </div>
            </div>

            <div className="col-span-8">
              <div className="relative pl-[92px]">
                {/* rail */}
                <div className="absolute left-[70px] top-2 bottom-2 w-px bg-white/[0.07]" />
                <motion.div
                  className="absolute left-[70px] top-2 w-px origin-top bg-copper/70"
                  style={{
                    height: "calc(100% - 16px)",
                    scaleY: progress,
                  }}
                />

                <ol className="space-y-[6px]">
                  {STEPS.map((s, i) => {
                    const on = i <= active;
                    const isCurrent = i === active;
                    return (
                      <motion.li
                        key={s.title}
                        animate={{ opacity: on ? 1 : 0.16 }}
                        transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
                        className="relative"
                      >
                        {/* node */}
                        <span
                          className={cx(
                            "absolute left-[-28px] top-[18px] block rounded-full transition-all duration-500",
                            isCurrent
                              ? "h-[9px] w-[9px] bg-copper shadow-[0_0_0_4px_rgba(215,164,90,0.14)]"
                              : on
                                ? "h-[7px] w-[7px] bg-copper/60"
                                : "h-[5px] w-[5px] bg-white/20",
                          )}
                        />
                        <span className="absolute left-[-62px] top-[15px] w-[28px] text-right font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                          {s.kind.slice(0, 4)}
                        </span>

                        <div
                          className={cx(
                            "border-l border-white/[0.06] py-[12px] pl-5 transition-colors duration-500",
                            isCurrent && "border-copper/60 bg-gradient-to-r from-copper/[0.05] to-transparent",
                          )}
                        >
                          <div className="flex flex-wrap items-center gap-3">
                            <span
                              className={cx(
                                "font-mono text-[12px] uppercase tracking-[0.1em] transition-colors duration-500",
                                isCurrent ? "text-copper" : "text-paper",
                              )}
                            >
                              {s.title}
                            </span>
                            {s.verdict ? <VerdictTag verdict={s.verdict} /> : null}
                          </div>
                          <p className="mt-[7px] max-w-[52ch] text-[13.5px] leading-[1.6] text-stone">
                            {s.detail}
                          </p>
                          {s.meta ? (
                            <p className="mt-[5px] font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                              {s.meta}
                            </p>
                          ) : null}
                        </div>
                      </motion.li>
                    );
                  })}
                </ol>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* ---------------- mobile: horizontal rail ---------------- */}
      <div className="md:hidden">
        <Label>The chain</Label>
        <h3 className="display mt-4 text-[26px] leading-[1.18] text-paper">Memory, accumulating.</h3>
        <p className="mt-4 text-[14px] leading-[1.7] text-stone">
          Scroll to watch one verdict become the authority the next panel has to answer.
        </p>

        <div className="mt-8 overflow-x-auto pb-2">
          <div className="flex min-w-max items-stretch gap-0">
            {STEPS.map((s, i) => (
              <div key={s.title} className="flex items-stretch">
                <div
                  className={cx(
                    "w-[210px] rounded-[8px] border p-4 transition-all duration-500",
                    i === active ? "border-copper/50 bg-copper/[0.05]" : "border-white/[0.08] bg-ink",
                  )}
                >
                  <span className="font-mono text-[9px] uppercase tracking-[0.16em] text-muted">
                    {String(i + 1).padStart(2, "0")} · {s.kind}
                  </span>
                  <p className="mt-3 font-mono text-[12px] uppercase tracking-[0.08em] text-paper">
                    {s.title}
                  </p>
                  <p className="mt-2 text-[13px] leading-[1.55] text-stone">{s.detail}</p>
                </div>
                {i < STEPS.length - 1 ? (
                  <div className="flex w-6 items-center justify-center">
                    <span className="h-px w-6 bg-white/10" />
                  </div>
                ) : null}
              </div>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.p
            key={active}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.25 }}
            className="mt-5 font-mono text-[10px] uppercase tracking-[0.14em] text-copper"
          >
            Step {active + 1} of {STEPS.length}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  );
}
