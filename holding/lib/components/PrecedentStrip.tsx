"use client";

import { motion } from "framer-motion";
import { cx } from "./ui/primitives";

const CHAIN = [
  { k: "CASE", v: "0184", tone: "ink" },
  { k: "HOLDING", v: "#00184", tone: "copper" },
  { k: "CASE", v: "0392", tone: "ink" },
  { k: "HOLDING", v: "#00392", tone: "copper" },
  { k: "CASE", v: "0417", tone: "ink" },
  { k: "NEW PANEL", v: "0417", tone: "paper" },
] as const;

/** The hero visual: a precedent chain that visibly accumulates. */
export function PrecedentStrip({ className }: { className?: string }) {
  return (
    <div className={cx("border-t border-white/[0.08] pt-10", className)}>
      {/* desktop */}
      <div className="hidden items-center md:flex">
        {CHAIN.map((n, i) => (
          <div key={`${n.k}-${i}`} className="flex flex-1 items-center last:flex-none">
            <div className="min-w-[104px]">
              <span
                className={cx(
                  "block font-mono text-[9px] uppercase tracking-[0.18em]",
                  n.tone === "copper" ? "text-copper" : "text-muted",
                )}
              >
                {n.k}
              </span>
              <span
                className={cx(
                  "mt-2 block font-mono text-[15px] tracking-[0.04em]",
                  n.tone === "copper" ? "text-copper" : "text-paper",
                )}
              >
                {n.v}
              </span>
              <span className="mt-3 block h-px w-full bg-white/[0.08]" />
            </div>

            {i < CHAIN.length - 1 ? (
              <div className="relative mx-4 h-px flex-1 bg-white/[0.08]">
                <motion.span
                  className="absolute top-0 h-px w-6 bg-copper"
                  animate={{ left: ["0%", "100%"], opacity: [0, 1, 1, 0] }}
                  transition={{
                    duration: 2.6,
                    delay: i * 0.32,
                    repeat: Infinity,
                    repeatDelay: 1.6,
                    ease: "easeInOut",
                  }}
                />
              </div>
            ) : null}
          </div>
        ))}
      </div>

      {/* mobile: horizontal scroll rail */}
      <div className="-mx-6 overflow-x-auto px-6 md:hidden">
        <div className="flex min-w-max items-center">
          {CHAIN.map((n, i) => (
            <div key={`${n.k}-${i}`} className="flex items-center">
              <div className="rounded-[8px] border border-white/[0.08] px-4 py-3">
                <span
                  className={cx(
                    "block font-mono text-[9px] uppercase tracking-[0.18em]",
                    n.tone === "copper" ? "text-copper" : "text-muted",
                  )}
                >
                  {n.k}
                </span>
                <span className="mt-1 block font-mono text-[14px] text-paper">{n.v}</span>
              </div>
              {i < CHAIN.length - 1 ? (
                <div className="mx-2 h-px w-6 bg-white/15" />
              ) : null}
            </div>
          ))}
        </div>
      </div>

      <p className="mt-8 font-mono text-[10px] uppercase leading-[1.8] tracking-[0.14em] text-muted">
        A decision is adjudicated once · a holding is used for as long as the record exists
      </p>
    </div>
  );
}
