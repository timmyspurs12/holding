"use client";

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Plus, Minus } from "lucide-react";
import type { EvidenceItem } from "@/lib/data/types";
import { Label, cx } from "./ui/primitives";

export function EvidenceList({ items }: { items: EvidenceItem[] }) {
  const [open, setOpen] = useState<number | null>(0);

  return (
    <div className="border-t border-white/[0.08]">
      {items.map((e, i) => (
        <div key={e.hash} className="border-b border-white/[0.06]">
          <button
            onClick={() => setOpen(open === i ? null : i)}
            aria-expanded={open === i}
            className="flex w-full items-center justify-between gap-6 py-4 text-left transition-colors hover:bg-white/[0.015]"
          >
            <div className="flex items-center gap-4">
              <span className="font-mono text-[10px] tabular-nums text-muted">
                {String(i + 1).padStart(2, "0")}
              </span>
              <span className="text-[13.5px] text-paper">{e.label}</span>
              <span className="label hidden sm:inline">{e.kind}</span>
            </div>
            <div className="flex items-center gap-5">
              <span className="hidden font-mono text-[10px] tracking-[0.1em] text-muted md:inline">
                {e.hash}
              </span>
              <span className="text-stone">
                {open === i ? <Minus size={12} strokeWidth={1.5} /> : <Plus size={12} strokeWidth={1.5} />}
              </span>
            </div>
          </button>

          <AnimatePresence initial={false}>
            {open === i ? (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                transition={{ duration: 0.28, ease: [0.16, 1, 0.3, 1] }}
                className="overflow-hidden"
              >
                <div className="grid gap-4 pb-6 pl-[38px] md:grid-cols-2">
                  <div>
                    <Label>Recorded hash</Label>
                    <p className="mt-2 break-all font-mono text-[11px] text-paper">{e.hash}</p>
                  </div>
                  <div>
                    <Label>Kind</Label>
                    <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.12em] text-stone">
                      {e.kind}
                    </p>
                  </div>
                  <p className="md:col-span-2 text-[12.5px] leading-[1.65] text-muted">
                    Evidence is referenced by hash at finality. The panel reasoned over the
                    retrieved record, not a re-fetch — so the basis of the decision can be audited
                    afterwards.
                  </p>
                </div>
              </motion.div>
            ) : null}
          </AnimatePresence>
        </div>
      ))}
    </div>
  );
}
