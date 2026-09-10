"use client";

import { useEffect, useState } from "react";
import { motion, useInView } from "framer-motion";
import { useRef } from "react";
import type { PanelMember } from "@/lib/data/types";
import { Label, cx } from "./ui/primitives";

/** Contextual loading: validators appear sequentially rather than a spinner. */
export function PanelReview({ members }: { members: PanelMember[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-80px" });
  const [revealed, setRevealed] = useState(0);

  useEffect(() => {
    if (!inView) return;
    if (revealed >= members.length) return;
    const t = setTimeout(() => setRevealed((r) => r + 1), revealed === 0 ? 180 : 420);
    return () => clearTimeout(t);
  }, [inView, revealed, members.length]);

  const follow = members.filter((m) => m.vote === "FOLLOW" && m.reviewed).length;
  const reviewed = members.filter((m) => m.reviewed).length;

  return (
    <div ref={ref}>
      <div className="flex items-center justify-between">
        <Label>Panel review</Label>
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {Math.min(revealed, reviewed)} / {members.length} reviewed
        </span>
      </div>

      <div className="mt-5">
        {members.map((m, i) => {
          const state =
            i < revealed && m.reviewed ? "REVIEWED" : i === revealed ? "REVIEWING" : "QUEUED";
          return (
            <div
              key={m.index}
              className="grid grid-cols-12 items-center gap-4 border-b border-white/[0.06] py-[11px]"
            >
              <span className="col-span-1 font-mono text-[10px] tabular-nums text-muted">
                {String(m.index).padStart(2, "0")}
              </span>
              <span className="col-span-4 text-[13px] text-paper">{m.model}</span>
              <span className="col-span-4 text-[12.5px] text-muted">
                {state === "REVIEWED" ? m.note : ""}
              </span>
              <span className="col-span-3 text-right">
                {state === "REVIEWED" ? (
                  <motion.span
                    initial={{ opacity: 0, x: 6 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ duration: 0.3 }}
                    className={cx(
                      "font-mono text-[10px] uppercase tracking-[0.12em]",
                      m.vote === "FOLLOW" ? "text-verdict" : "text-dissent",
                    )}
                  >
                    {m.vote === "FOLLOW" ? "Follow" : "Distinguish"}
                  </motion.span>
                ) : (
                  <span
                    className={cx(
                      "font-mono text-[10px] uppercase tracking-[0.12em]",
                      state === "REVIEWING" ? "animate-pulseSoft text-copper" : "text-muted opacity-40",
                    )}
                  >
                    {state}
                  </span>
                )}
              </span>
            </div>
          );
        })}
      </div>

      {revealed >= members.length && reviewed > 0 ? (
        <motion.div
          initial={{ opacity: 0, y: 6 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.45 }}
          className="mt-8 flex items-baseline gap-6 border-t border-white/[0.08] pt-6"
        >
          <div>
            <Label>Consensus</Label>
            <div className="display mt-2 text-[36px] leading-none tabular-nums text-paper">
              {follow} <span className="text-muted">/ {members.length}</span>
            </div>
          </div>
          <div>
            <Label>Disposition</Label>
            <p
              className={cx(
                "mt-2 font-mono text-[13px] uppercase tracking-[0.12em]",
                follow >= members.length / 2 ? "text-verdict" : "text-dissent",
              )}
            >
              {follow >= members.length / 2 ? "Followed" : "Distinguished"}
            </p>
          </div>
        </motion.div>
      ) : null}
    </div>
  );
}
