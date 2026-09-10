import { HOLDINGS } from "./holdings";
import { CASES } from "./cases";
import { DOMAINS } from "./domains";
import type { Holding } from "./types";

export { HOLDINGS, getHolding } from "./holdings";
export { CASES, getCase } from "./cases";
export { DOMAINS, getDomain } from "./domains";
export * from "./types";

/* ------------------------------------------------------------------ */
/* Corpus figures — simulated. Every UI surface labels these DEMO.      */
/* ------------------------------------------------------------------ */
export const CORPUS = {
  holdingsIndexed: 41182,
  casesProcessed: 41207,
  domainsCovered: DOMAINS.length,
  citationsRecorded: 128940,
  distinguishments: 2841,
  consistency: 94,
  lastIndexed: "2026-09-09T21:14:00Z",
};

/* ------------------------------------------------------------------ */
/* Ecosystem reference figures — published, sourced, not simulated.     */
/* ------------------------------------------------------------------ */
export const NETWORK_FACTS: {
  figure: string;
  label: string;
  detail: string;
  source: string;
  url: string;
  demo: false;
}[] = [
  {
    figure: "25,800",
    label: "decisions per day",
    detail: "Adjudicated decisions produced across the network, none of them retained as precedent today.",
    source: "CryptoDaily, Jul 2026",
    url: "https://cryptodaily.co.uk/2026/07/genlayer-ai-agent-court-defi-dispute-resolution",
    demo: false,
  },
  {
    figure: "5",
    label: "validators, different models",
    detail: "Each panel runs a different LLM — divergence between rulings is structural, not accidental.",
    source: "CryptoBriefing",
    url: "https://cryptobriefing.com/genlayer-ai-court-validators/",
    demo: false,
  },
  {
    figure: "~30 min",
    label: "appeal window",
    detail: "A decision is appealable for roughly thirty minutes; on appeal the panel expands from 5 to 11 validators.",
    source: "CoinDesk, Apr 2025",
    url: "https://www.coindesk.com/tech/2025/04/30/ai-powered-court-system-is-coming-to-crypto-with-genlayer",
    demo: false,
  },
  {
    figure: "Q4 2026",
    label: "mainnet target",
    detail: "Precedent that exists before mainnet scale is clean law. After, it becomes a migration.",
    source: "CryptoBriefing",
    url: "https://cryptobriefing.com/genlayer-ai-court-validators/",
    demo: false,
  },
];

/* ------------------------------------------------------------------ */
/* Search + filtering                                                   */
/* ------------------------------------------------------------------ */
export interface HoldingFilters {
  query?: string;
  domain?: string;
  verdict?: string;
  authority?: string;
  appeal?: string;
  sort?: string;
}

const authorityRank: Record<string, number> = { HIGH: 3, MODERATE: 2, DEVELOPING: 1 };

export function searchHoldings(filters: HoldingFilters): Holding[] {
  const q = (filters.query ?? "").trim().toLowerCase();
  let out = HOLDINGS.filter((h) => {
    if (filters.domain && filters.domain !== "all" && h.domainSlug !== filters.domain) return false;
    if (filters.verdict && filters.verdict !== "all" && h.verdict !== filters.verdict) return false;
    if (filters.authority && filters.authority !== "all" && h.authority !== filters.authority) return false;
    if (filters.appeal && filters.appeal !== "all" && h.appeal !== filters.appeal) return false;
    if (!q) return true;
    const haystack = [
      h.id,
      h.domain,
      h.contractClass,
      h.issue,
      h.issueLong,
      h.ratio,
      h.verdict,
      ...h.facts,
      ...h.reasonCodes,
    ]
      .join(" ")
      .toLowerCase();
    return haystack.includes(q);
  });

  const sort = filters.sort ?? "authority";
  out = [...out].sort((a, b) => {
    if (sort === "citations") return b.citations - a.citations;
    if (sort === "recent") return +new Date(b.finalityTs) - +new Date(a.finalityTs);
    if (sort === "distinguished") return b.distinguishedBy - a.distinguishedBy;
    return (
      authorityRank[b.authority] - authorityRank[a.authority] ||
      b.citations - a.citations
    );
  });
  return out;
}

/* ------------------------------------------------------------------ */
/* Citation graph                                                       */
/* ------------------------------------------------------------------ */
export type EdgeKind = "CITED_BY" | "DISTINGUISHES" | "DERIVED_FROM";

export interface GraphNode {
  id: string;
  label: string;
  domain: string;
  verdict: string;
  authority: string;
  x: number;
  y: number;
  depth: number;
}

export interface GraphEdge {
  from: string;
  to: string;
  kind: EdgeKind;
}

export function buildCitationGraph(rootId: string) {
  const root = HOLDINGS.find((h) => h.id === rootId);
  if (!root) return { nodes: [] as GraphNode[], edges: [] as GraphEdge[] };

  const ids = new Set<string>([root.id]);
  root.derivedFrom.forEach((i) => ids.add(i));
  root.citedBy.forEach((i) => ids.add(i));
  root.distinguishes.forEach((i) => ids.add(i));

  // one hop further, so the map reads like a map
  const second = new Set<string>();
  ids.forEach((id) => {
    const h = HOLDINGS.find((x) => x.id === id);
    h?.derivedFrom.forEach((i) => second.add(i));
    h?.citedBy.slice(0, 3).forEach((i) => second.add(i));
  });
  second.forEach((i) => ids.add(i));

  const nodes: GraphNode[] = [];
  const list = [...ids];
  const radius = 150;
  list.forEach((id, i) => {
    const h = HOLDINGS.find((x) => x.id === id)!;
    const depth = id === root.id ? 0 : root.derivedFrom.includes(id) || root.distinguishes.includes(id) ? -1 : 1;
    if (id === root.id) {
      nodes.push({ id, label: h.id, domain: h.domain, verdict: h.verdict, authority: h.authority, x: 0, y: 0, depth: 0 });
    } else {
      const angle = (i / list.length) * Math.PI * 2;
      const r = depth === -1 ? radius * 0.78 : radius * 1.32;
      nodes.push({
        id,
        label: h.id,
        domain: h.domain,
        verdict: h.verdict,
        authority: h.authority,
        x: Math.cos(angle) * r,
        y: Math.sin(angle) * r * 0.66,
        depth,
      });
    }
  });

  const edges: GraphEdge[] = [];
  const has = (id: string) => ids.has(id);
  list.forEach((id) => {
    const h = HOLDINGS.find((x) => x.id === id)!;
    h.citedBy.filter(has).forEach((t) => edges.push({ from: id, to: t, kind: "CITED_BY" }));
    h.distinguishes.filter(has).forEach((t) => edges.push({ from: id, to: t, kind: "DISTINGUISHES" }));
    h.derivedFrom.filter(has).forEach((t) => edges.push({ from: id, to: t, kind: "DERIVED_FROM" }));
  });

  return { nodes, edges };
}

/* ------------------------------------------------------------------ */
/* Formatting                                                           */
/* ------------------------------------------------------------------ */
export const fmtDate = (iso: string) =>
  new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });

export const fmtTime = (iso: string) =>
  new Date(iso).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });

export const fmtNum = (n: number) => n.toLocaleString("en-GB");

export const totalHoldings = HOLDINGS.length;
export const totalCases = CASES.length;
