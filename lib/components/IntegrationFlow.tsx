"use client";

import { useEffect, useState } from "react";
import { motion } from "framer-motion";
import { cx, Label } from "./ui/primitives";

const NODES = [
  { k: "Your contract", v: "Intelligent Contract", d: "Emits a case digest on submission" },
  { k: "Holding", v: "get_precedent()", d: "Consensus-verified k-NN retrieval" },
  { k: "Relevant precedent", v: "k = 3", d: "Nearest holdings with authority weights" },
  { k: "GenLayer panel", v: "5 validators", d: "Follows, or writes a distinguishment" },
  { k: "New holding", v: "Indexed", d: "Joins the permanent record" },
];

export function IntegrationFlow({ className }: { className?: string }) {
  const [active, setActive] = useState(0);

  useEffect(() => {
    const t = setInterval(() => setActive((a) => (a + 1) % (NODES.length + 1)), 1700);
    return () => clearInterval(t);
  }, []);

  return (
    <div className={className}>
      {/* desktop: horizontal */}
      <div className="hidden md:block">
        <div className="flex items-stretch">
          {NODES.map((n, i) => (
            <div key={n.k} className="flex flex-1 items-stretch">
              <NodeBox node={n} active={active === i} passed={active > i} index={i} />
              {i < NODES.length - 1 ? (
                <div className="relative flex w-10 items-center">
                  <div className="h-px w-full bg-white/[0.08]" />
                  <motion.div
                    className="absolute left-0 h-px w-full origin-left bg-copper/80"
                    animate={{ scaleX: active > i ? 1 : 0 }}
                    transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              ) : null}
            </div>
          ))}
        </div>
      </div>

      {/* mobile: vertical */}
      <div className="md:hidden">
        {NODES.map((n, i) => (
          <div key={n.k}>
            <NodeBox node={n} active={active === i} passed={active > i} index={i} />
            {i < NODES.length - 1 ? (
              <div className="relative ml-[18px] h-8 w-px bg-white/[0.08]">
                <motion.div
                  className="absolute top-0 w-px origin-top bg-copper/80"
                  style={{ height: "100%" }}
                  animate={{ scaleY: active > i ? 1 : 0 }}
                  transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            ) : null}
          </div>
        ))}
      </div>
    </div>
  );
}

function NodeBox({
  node,
  active,
  passed,
  index,
}: {
  node: (typeof NODES)[number];
  active: boolean;
  passed: boolean;
  index: number;
}) {
  return (
    <motion.div
      animate={{
        borderColor: active ? "rgba(215,164,90,0.5)" : "rgba(255,255,255,0.08)",
        backgroundColor: active ? "rgba(215,164,90,0.05)" : "rgba(17,19,23,1)",
      }}
      transition={{ duration: 0.4 }}
      className="flex-1 rounded-[9px] border p-4"
    >
      <div className="flex items-center gap-2">
        <span className="font-mono text-[9px] tabular-nums text-muted">
          {String(index + 1).padStart(2, "0")}
        </span>
        <span
          className={cx(
            "font-mono text-[10px] uppercase tracking-[0.14em] transition-colors duration-300",
            active ? "text-copper" : passed ? "text-stone" : "text-muted",
          )}
        >
          {node.k}
        </span>
      </div>
      <p className="mt-3 text-[13.5px] leading-[1.4] text-paper">{node.v}</p>
      <p className="mt-2 text-[12px] leading-[1.5] text-muted">{node.d}</p>
    </motion.div>
  );
}
