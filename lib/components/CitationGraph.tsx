"use client";

import { useMemo, useState } from "react";
import { motion } from "framer-motion";
import { buildCitationGraph, getHolding } from "@/lib/data";
import { cx, Label, VerdictTag, AuthorityTag } from "./ui/primitives";
import type { EdgeKind } from "@/lib/data";

const strokeFor: Record<EdgeKind, string> = {
  CITED_BY: "rgba(255,255,255,0.20)",
  DISTINGUISHES: "rgba(201,107,98,0.55)",
  DERIVED_FROM: "rgba(215,164,90,0.55)",
};
const dashFor: Record<EdgeKind, string> = {
  CITED_BY: "0",
  DISTINGUISHES: "3 3",
  DERIVED_FROM: "0",
};

export function CitationGraph({ rootId }: { rootId: string }) {
  const { nodes, edges } = useMemo(() => buildCitationGraph(rootId), [rootId]);
  const [active, setActive] = useState<string | null>(null);
  const preview = active ? getHolding(active) : getHolding(rootId);
  const pos = (id: string) => nodes.find((n) => n.id === id)!;

  return (
    <div className="grid gap-8 lg:grid-cols-12">
      {/* ---------- map ---------- */}
      <div className="lg:col-span-8">
        <div className="panel relative overflow-hidden rounded-[10px]">
          <div className="flex items-center justify-between border-b border-white/[0.08] px-5 py-3">
            <Label>Citation map</Label>
            <div className="flex flex-wrap items-center gap-4">
              {(["CITED_BY", "DISTINGUISHES", "DERIVED_FROM"] as EdgeKind[]).map((k) => (
                <span key={k} className="flex items-center gap-2">
                  <svg width="16" height="4" aria-hidden>
                    <line
                      x1="0"
                      y1="2"
                      x2="16"
                      y2="2"
                      stroke={strokeFor[k]}
                      strokeWidth="1"
                      strokeDasharray={dashFor[k]}
                    />
                  </svg>
                  <span className="font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
                    {k.replace("_", " ").toLowerCase()}
                  </span>
                </span>
              ))}
            </div>
          </div>

          <div className="relative h-[360px] w-full md:h-[440px]">
            <svg
              viewBox="-280 -190 560 380"
              preserveAspectRatio="xMidYMid meet"
              className="h-full w-full"
              role="img"
              aria-label="Citation map"
              onMouseLeave={() => setActive(null)}
            >
              {/* concentric guides */}
              {[70, 130, 190].map((r) => (
                <ellipse
                  key={r}
                  cx="0"
                  cy="0"
                  rx={r * 1.5}
                  ry={r * 0.95}
                  fill="none"
                  stroke="rgba(255,255,255,0.045)"
                  strokeWidth="1"
                />
              ))}

              {/* edges */}
              {edges.map((e, i) => {
                const a = pos(e.from);
                const b = pos(e.to);
                if (!a || !b) return null;
                const lit = active === e.from || active === e.to;
                return (
                  <motion.line
                    key={`${e.from}-${e.to}-${e.kind}-${i}`}
                    x1={a.x}
                    y1={a.y}
                    x2={b.x}
                    y2={b.y}
                    stroke={strokeFor[e.kind]}
                    strokeDasharray={dashFor[e.kind]}
                    strokeWidth={lit ? 1.3 : 0.7}
                    opacity={active && !lit ? 0.25 : 1}
                    initial={{ pathLength: 0, opacity: 0 }}
                    animate={{ pathLength: 1, opacity: active && !lit ? 0.25 : 1 }}
                    transition={{ duration: 0.9, delay: 0.05 * (i % 12), ease: "easeOut" }}
                  />
                );
              })}

              {/* nodes */}
              {nodes.map((n, i) => {
                const isRoot = n.depth === 0;
                const isActive = active === n.id;
                const r = isRoot ? 7 : n.authority === "HIGH" ? 5.2 : 4;
                return (
                  <g
                    key={n.id}
                    transform={`translate(${n.x} ${n.y})`}
                    onMouseEnter={() => setActive(n.id)}
                    onClick={() => setActive(n.id)}
                    className="cursor-pointer"
                  >
                    {isActive ? (
                      <circle r={r + 7} fill="rgba(215,164,90,0.10)" stroke="rgba(215,164,90,0.45)" strokeWidth="0.7" />
                    ) : null}
                    <motion.circle
                      r={r}
                      fill={isRoot ? "#D7A45A" : n.verdict === "REJECTED" ? "#C96B62" : n.verdict === "APPROVED" ? "#9FBF9A" : "#D7A45A"}
                      fillOpacity={isActive || isRoot ? 1 : 0.62}
                      stroke="#0A0B0D"
                      strokeWidth="1"
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      transition={{ delay: 0.1 + i * 0.02, duration: 0.35 }}
                    />
                    <text
                      y={r + 12}
                      textAnchor="middle"
                      className="font-mono"
                      fontSize="7.5"
                      letterSpacing="0.1em"
                      fill={isActive ? "#F3F0E8" : "rgba(243,240,232,0.45)"}
                    >
                      {n.label.replace(/^0+/, "#")}
                    </text>
                  </g>
                );
              })}
            </svg>

            {nodes.length <= 1 ? (
              <p className="absolute inset-0 flex items-center justify-center text-[13px] text-muted">
                No citations recorded for this holding yet.
              </p>
            ) : null}
          </div>
        </div>
      </div>

      {/* ---------- preview ---------- */}
      <div className="lg:col-span-4">
        <Label>Context</Label>
        <div className="panel mt-4 rounded-[10px] p-5">
          {preview ? (
            <>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[12px] tracking-[0.1em] text-copper">
                  #{preview.id}
                </span>
                <AuthorityTag authority={preview.authority} />
              </div>
              <p className="mt-4 text-[14px] leading-[1.55] text-paper">{preview.issue}</p>
              <div className="mt-4 flex flex-wrap items-center gap-2">
                <VerdictTag verdict={preview.verdict} />
                <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
                  {preview.citations} citations · {preview.distinguishedBy} distinguished
                </span>
              </div>
              <p className="mt-4 line-clamp-4 text-[13px] leading-[1.65] text-stone">{preview.ratio}</p>
              <a
                href={`/holdings/${preview.id}`}
                className={cx(
                  "mt-4 inline-block py-[6px] font-mono text-[10px] uppercase tracking-[0.14em] text-copper",
                  "underline decoration-copper/30 underline-offset-4 hover:decoration-copper",
                )}
              >
                Open holding
              </a>
            </>
          ) : null}
        </div>

        <p className="mt-5 font-mono text-[10px] uppercase leading-[1.8] tracking-[0.12em] text-muted">
          Hover a node for context.
          <br />
          Simulated citation graph · demo data.
        </p>
      </div>
    </div>
  );
}
