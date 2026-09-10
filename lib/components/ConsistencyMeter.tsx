"use client";

import { motion } from "framer-motion";
import { Label } from "./ui/primitives";

export function ConsistencyMeter({
  followed,
  distinguished,
  caption = "Percentage of comparable cases following established precedent.",
  note,
  className,
  animate = true,
}: {
  followed: number;
  distinguished: number;
  caption?: string;
  note?: string;
  className?: string;
  animate?: boolean;
}) {
  return (
    <div className={className}>
      <div className="flex items-end justify-between gap-6">
        <div>
          <Label>Domain consistency</Label>
          <div className="display mt-3 text-[44px] leading-none tabular-nums text-paper md:text-[56px]">
            {followed}
            <span className="text-[26px] text-muted">%</span>
          </div>
        </div>
        <div className="text-right">
          <div className="flex items-baseline justify-end gap-2">
            <span className="h-[6px] w-[6px] rounded-[1px] bg-verdict" />
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
              Followed {followed}%
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-end gap-2">
            <span className="h-[6px] w-[6px] rotate-45 bg-dissent" />
            <span className="font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
              Distinguished {distinguished}%
            </span>
          </div>
        </div>
      </div>

      {/* editorial meter */}
      <div className="mt-7 flex h-[8px] w-full gap-[2px]">
        {Array.from({ length: 40 }).map((_, i) => {
          const isFollowed = i < Math.round((followed / 100) * 40);
          return (
            <motion.span
              key={i}
              className={isFollowed ? "flex-1 bg-verdict/85" : "flex-1 bg-dissent/70"}
              initial={animate ? { opacity: 0 } : false}
              whileInView={animate ? { opacity: 1 } : undefined}
              viewport={{ once: true }}
              transition={{ delay: i * 0.012, duration: 0.4 }}
            />
          );
        })}
      </div>

      <p className="mt-6 max-w-[46ch] text-[13px] leading-[1.65] text-stone">{caption}</p>
      {note ? (
        <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{note}</p>
      ) : null}
    </div>
  );
}
