"use client";

import { motion } from "framer-motion";
import { cx, Label, VerdictTag } from "./ui/primitives";

export function CaseCompare({
  left,
  right,
  materialDifference,
  leftVerdict,
  className,
}: {
  left: { id: string; label: string; facts: string[]; verdict?: string; meta?: string };
  right: { id: string; label: string; facts: string[]; verdict?: string; meta?: string };
  materialDifference?: string;
  leftVerdict?: string;
  className?: string;
}) {
  const leftSet = new Set(left.facts.map((f) => f.toLowerCase()));

  return (
    <div className={className}>
      <div className="grid gap-8 md:grid-cols-2 md:gap-12">
        <div>
          <div className="flex items-center justify-between">
            <Label>{left.label}</Label>
            {leftVerdict ? <VerdictTag verdict={leftVerdict} /> : null}
          </div>
          <p className="mt-3 font-mono text-[13px] tracking-[0.1em] text-paper">#{left.id}</p>
          {left.meta ? (
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {left.meta}
            </p>
          ) : null}
          <ul className="mt-5 space-y-[11px]">
            {left.facts.map((f, i) => (
              <motion.li
                key={i}
                initial={{ opacity: 0, x: -4 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: i * 0.06, duration: 0.35 }}
                className="flex items-start gap-3"
              >
                <span className="mt-[8px] font-mono text-[10px] text-verdict">✓</span>
                <span className="text-[13.5px] leading-[1.55] text-stone">{f}</span>
              </motion.li>
            ))}
          </ul>
        </div>

        <div>
          <div className="flex items-center justify-between">
            <Label>{right.label}</Label>
            {right.verdict ? <VerdictTag verdict={right.verdict} /> : null}
          </div>
          <p className="mt-3 font-mono text-[13px] tracking-[0.1em] text-paper">#{right.id}</p>
          {right.meta ? (
            <p className="mt-1 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
              {right.meta}
            </p>
          ) : null}
          <ul className="mt-5 space-y-[11px]">
            {right.facts.map((f, i) => {
              const match = leftSet.has(f.toLowerCase());
              return (
                <motion.li
                  key={i}
                  initial={{ opacity: 0, x: -4 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: true }}
                  transition={{ delay: i * 0.06, duration: 0.35 }}
                  className={cx(
                    "-mx-2 flex items-start gap-3 rounded-[4px] px-2 py-[2px]",
                    !match && "bg-dissent/[0.08]",
                  )}
                >
                  <span
                    className={cx(
                      "mt-[8px] font-mono text-[10px]",
                      match ? "text-verdict" : "text-dissent",
                    )}
                  >
                    {match ? "✓" : "◆"}
                  </span>
                  <span
                    className={cx(
                      "text-[13.5px] leading-[1.55]",
                      match ? "text-stone" : "text-paper",
                    )}
                  >
                    {f}
                  </span>
                </motion.li>
              );
            })}
          </ul>
        </div>
      </div>

      {materialDifference ? (
        <motion.div
          initial={{ opacity: 0, y: 8 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ duration: 0.45 }}
          className="mt-10 border-t border-white/[0.08] pt-7"
        >
          <div className="flex items-center gap-3">
            <span className="h-[6px] w-[6px] rotate-45 bg-dissent" />
            <Label>Material difference</Label>
          </div>
          <p className="display mt-3 max-w-[58ch] text-[20px] leading-[1.45] text-paper md:text-[24px]">
            {materialDifference}
          </p>
        </motion.div>
      ) : null}
    </div>
  );
}
