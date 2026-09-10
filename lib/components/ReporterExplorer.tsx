"use client";

import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import { Search, X } from "lucide-react";
import { searchHoldings, DOMAINS, CORPUS, fmtNum } from "@/lib/data";
import { HoldingCard } from "./HoldingCard";
import { Label, cx } from "./ui/primitives";

const SORTS = [
  { id: "authority", label: "Authority" },
  { id: "citations", label: "Most cited" },
  { id: "distinguished", label: "Most distinguished" },
  { id: "recent", label: "Most recent" },
] as const;

export function ReporterExplorer() {
  const searchParams = useSearchParams();
  const [query, setQuery] = useState("");
  const [domain, setDomain] = useState(searchParams.get("domain") ?? "all");
  const [verdict, setVerdict] = useState("all");
  const [authority, setAuthority] = useState("all");
  const [appeal, setAppeal] = useState("all");
  const [sort, setSort] = useState<string>("authority");
  const [searching, setSearching] = useState(false);

  useEffect(() => {
    if (!query) {
      setSearching(false);
      return;
    }
    setSearching(true);
    const t = setTimeout(() => setSearching(false), 260);
    return () => clearTimeout(t);
  }, [query]);

  const results = useMemo(
    () => searchHoldings({ query, domain, verdict, authority, appeal, sort }),
    [query, domain, verdict, authority, appeal, sort],
  );

  const active =
    query || domain !== "all" || verdict !== "all" || authority !== "all" || appeal !== "all";

  const clear = () => {
    setQuery("");
    setDomain("all");
    setVerdict("all");
    setAuthority("all");
    setAppeal("all");
  };

  return (
    <div>
      {/* ---------- search ---------- */}
      <div className="flex items-center gap-3 border-b border-white/[0.12] pb-4">
        <Search size={15} strokeWidth={1.5} className="shrink-0 text-stone" />
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search holdings, issues, facts or verdicts…"
          aria-label="Search holdings"
          className="w-full bg-transparent py-[7px] text-[15px] text-paper placeholder:text-muted focus:outline-none md:text-[17px]"
        />
        {query ? (
          <button
            onClick={() => setQuery("")}
            aria-label="Clear search"
            className="shrink-0 rounded-[5px] border border-white/[0.12] p-[5px] text-stone transition-colors hover:text-paper"
          >
            <X size={12} strokeWidth={1.5} />
          </button>
        ) : null}
      </div>

      {/* ---------- filters ---------- */}
      <div className="mt-6 flex flex-wrap items-center gap-3">
        <Select label="Domain" value={domain} onChange={setDomain}>
          <option value="all">All domains</option>
          {DOMAINS.map((d) => (
            <option key={d.slug} value={d.slug}>
              {d.name}
            </option>
          ))}
        </Select>

        <Select label="Decision" value={verdict} onChange={setVerdict}>
          <option value="all">All decisions</option>
          <option value="APPROVED">Approved</option>
          <option value="REJECTED">Rejected</option>
          <option value="PARTIAL">Partial</option>
        </Select>

        <Select label="Authority" value={authority} onChange={setAuthority}>
          <option value="all">Any authority</option>
          <option value="HIGH">High</option>
          <option value="MODERATE">Moderate</option>
          <option value="DEVELOPING">Developing</option>
        </Select>

        <Select label="Appeal" value={appeal} onChange={setAppeal}>
          <option value="all">Any status</option>
          <option value="UPHELD">Upheld</option>
          <option value="SURVIVED">Survived</option>
          <option value="OVERTURNED">Overturned</option>
          <option value="PENDING">Pending</option>
        </Select>

        <div className="ml-auto flex items-center gap-2">
          {SORTS.map((s) => (
            <button
              key={s.id}
              onClick={() => setSort(s.id)}
              className={cx("chip", sort === s.id && "chip-active")}
            >
              {s.label}
            </button>
          ))}
        </div>
      </div>

      {/* ---------- status line ---------- */}
      <div className="mt-8 flex flex-wrap items-center justify-between gap-4 border-t border-white/[0.08] pt-5">
        <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
          {searching ? (
            <span className="text-copper">
              Searching {fmtNum(CORPUS.holdingsIndexed)} holdings…
            </span>
          ) : (
            <>
              {results.length} {results.length === 1 ? "holding" : "holdings"}
              <span className="text-muted"> · sorted by {sort}</span>
            </>
          )}
        </p>
        {active ? (
          <button
            onClick={clear}
            className="font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
          >
            Clear filters
          </button>
        ) : null}
      </div>

      {/* ---------- results ---------- */}
      <div className="mt-8">
        <AnimatePresence mode="wait">
          {searching ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {[0, 1, 2, 3, 4, 5].map((i) => (
                <div key={i} className="h-[210px] rounded-[9px] border border-white/[0.06] bg-ink">
                  <div className="h-full w-full overflow-hidden rounded-[9px]">
                    <motion.div
                      className="h-full w-1/2 bg-gradient-to-r from-transparent via-white/[0.035] to-transparent"
                      animate={{ x: ["-100%", "200%"] }}
                      transition={{ duration: 1.2, repeat: Infinity, ease: "linear", delay: i * 0.08 }}
                    />
                  </div>
                </div>
              ))}
            </motion.div>
          ) : results.length > 0 ? (
            <motion.div
              key="results"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              transition={{ duration: 0.28 }}
              className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3"
            >
              {results.map((h) => (
                <HoldingCard key={h.id} holding={h} />
              ))}
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="border border-white/[0.08] bg-ink px-8 py-16 text-center"
            >
              <Label>No holdings match</Label>
              <p className="mx-auto mt-4 max-w-[42ch] text-[14px] leading-[1.7] text-stone">
                Nothing in the index answers that description. Widen the filters, or clear them and
                start again.
              </p>
              <button
                onClick={clear}
                className="mt-7 rounded-[8px] border border-white/[0.14] px-4 py-[9px] text-[13px] text-paper transition-colors hover:border-copper/50 hover:text-copper"
              >
                Clear filters
              </button>
            </motion.div>
          )}
        </AnimatePresence>
      </div>
    </div>
  );
}

function Select({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="relative inline-flex items-center">
      <span className="pointer-events-none absolute left-3 font-mono text-[9px] uppercase tracking-[0.14em] text-muted">
        {label}
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className={cx(
          "appearance-none rounded-[7px] border border-white/[0.1] bg-ink py-[7px] pl-[62px] pr-8",
          "font-mono text-[11px] uppercase tracking-[0.1em] text-paper transition-colors",
          "hover:border-white/20 focus:border-copper/60 focus:outline-none",
        )}
      >
        {children}
      </select>
      <svg
        width="8"
        height="5"
        viewBox="0 0 8 5"
        className="pointer-events-none absolute right-3"
        aria-hidden
      >
        <path d="M1 1l3 3 3-3" stroke="#A7A39A" strokeWidth="1" fill="none" />
      </svg>
    </label>
  );
}
