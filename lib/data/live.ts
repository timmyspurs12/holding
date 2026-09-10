/**
 * Live/demo corpus bridge.
 *
 * The UI renders one shape (see ./types). This module produces that shape from
 * either the Reporter API or the bundled demo corpus, and tells the caller which
 * one it used so the page can label it.
 *
 * Contract rule: the frontend must not present simulated records as real
 * GenLayer records. Anything from the demo corpus keeps `demo: true`, and the
 * page shows the DEMO tag. Anything from a live network carries its tx ref.
 */

import { API_CONFIGURED, api } from "@/lib/api/client";
import type { ApiHolding, NetworkInfo } from "@/lib/api/client";
import { HOLDINGS, CASES, DOMAINS, CORPUS } from "./index";
import type { Holding, CaseRecord, DomainSummary } from "./types";

export interface Corpus {
  holdings: Holding[];
  cases: CaseRecord[];
  domains: DomainSummary[];
  live: boolean;
  network: NetworkInfo | null;
  stats: {
    holdingsIndexed: number;
    casesProcessed: number;
    domainsCovered: number;
    citationsRecorded: number;
    distinguishments: number;
    consistency: number;
    lastIndexed: string;
  };
}

/* ------------------------------------------------------------------ */
/* mapping: Reporter JSON -> UI shape                                   */
/* ------------------------------------------------------------------ */
const DOMAIN_LABELS: Record<string, string> = Object.fromEntries(
  DOMAINS.map((d) => [d.slug, d.name]),
);

function titleize(slug: string): string {
  if (DOMAIN_LABELS[slug]) return DOMAIN_LABELS[slug];
  return slug
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function shortHash(hash: string | null | undefined): string {
  if (!hash) return "—";
  return hash.length > 12 ? `${hash.slice(0, 6)}…${hash.slice(-4)}` : hash;
}

function isoTimestamp(value: number | null | undefined): string {
  return new Date((value ?? 0) * 1000).toISOString();
}

function appealOf(holding: ApiHolding): Holding["appeal"] {
  const outcome = (holding.finality?.appeal_outcome || "NONE").toUpperCase();
  const status = (holding.finality?.appeal_status || "NONE").toUpperCase();
  if (outcome === "OVERTURNED") return "OVERTURNED";
  if (outcome === "UPHELD") return "UPHELD";
  if (outcome === "PENDING" || status === "PENDING") return "PENDING";
  return holding.status === "FINAL" ? "SURVIVED" : "PENDING";
}

function factsOf(holding: ApiHolding): string[] {
  const parts = holding.facts_digest
    .split(/;\s*|\.\s+(?=[A-Z])/)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length > 0 ? parts : [holding.facts_digest];
}

export function mapHolding(
  holding: ApiHolding,
  edges: { derivedFrom: string[]; citedBy: string[]; distinguishes: string[] },
): Holding {
  const band = holding.authority?.band ?? (holding.authority_bp >= 7500 ? "HIGH" : holding.authority_bp >= 4500 ? "MODERATE" : "DEVELOPING");
  const components = holding.authority?.components_bp ?? {};
  const pct = (value: number | undefined) => Math.round(((value ?? 0) / 10000) * 100);

  return {
    id: holding.display_id || holding.holding_id,
    originCase: holding.case_id.replace(/^CASE-/, ""),
    domain: titleize(holding.domain),
    domainSlug: holding.domain,
    contractClass: holding.contract_class,
    issue: holding.issue,
    issueLong: holding.issue,
    facts: factsOf(holding),
    verdict: (["APPROVED", "REJECTED", "PARTIAL"].includes(holding.verdict) ? holding.verdict : "PARTIAL") as Holding["verdict"],
    reasonCodes: holding.reason_codes,
    ratio: holding.ratio,
    evidence: (holding.evidence_hashes ?? []).map((hash, index) => ({
      label: `Evidence ${String(index + 1).padStart(2, "0")}`,
      kind: "LEDGER" as const,
      hash: shortHash(hash),
    })),
    panelSize: holding.panel_size || 5,
    appeal: appealOf(holding),
    citations: holding.citation_count,
    distinguishedBy: holding.distinguishment_count,
    finalityTs: isoTimestamp(holding.finality_timestamp ?? holding.created_at),
    authority: band,
    authorityBreakdown: {
      finality: pct(components.finality),
      appeal: pct(components.appeal),
      citations: pct(components.citations),
      consistency: pct(components.consistency),
    },
    derivedFrom: edges.derivedFrom,
    citedBy: edges.citedBy,
    distinguishes: edges.distinguishes,
    onChainRef: shortHash(holding.provenance?.source_tx || holding.transaction_reference),
  };
}

/* ------------------------------------------------------------------ */
/* loaders                                                              */
/* ------------------------------------------------------------------ */
const DEMO_CORPUS: Corpus = {
  holdings: HOLDINGS,
  cases: CASES,
  domains: DOMAINS,
  live: false,
  network: null,
  stats: CORPUS,
};

export async function getCorpus(): Promise<Corpus> {
  if (!API_CONFIGURED) return DEMO_CORPUS;

  const [health, envelope, stats] = await Promise.all([
    api.health(),
    api.holdings({ limit: 200 }),
    api.stats(),
  ]);

  if (!envelope) return DEMO_CORPUS; // API configured but unreachable — keep the labelled demo corpus

  const citations = await Promise.all(
    envelope.items.map(async (item) => ({
      id: item.display_id || item.holding_id,
      edges: await api.citations(item.holding_id),
    })),
  );

  const edgeMap = new Map(citations.map((entry) => [entry.id, entry.edges]));
  const display = (id: string) => id.replace(/^HLD-/, "");

  const holdings = envelope.items.map((item) => {
    const edges = edgeMap.get(item.display_id || item.holding_id);
    const outgoing = edges?.items.filter((edge) => edge.direction === "outgoing") ?? [];
    const incoming = edges?.items.filter((edge) => edge.direction === "incoming") ?? [];
    return mapHolding(item, {
      derivedFrom: outgoing.filter((e) => e.relationship === "CITES").map((e) => display(e.target_holding_id)),
      citedBy: incoming.map((e) => display(e.source_holding_id)),
      distinguishes: outgoing.filter((e) => e.relationship === "DISTINGUISHES").map((e) => display(e.target_holding_id)),
    });
  });

  const casesEnvelope = await api.cases();
  const cases = (casesEnvelope?.items ?? []).map(mapCase);

  const network = health?.network ?? null;
  const simulated = network?.simulated ?? true;

  // In DEMO mode the contract records are simulated too, so they are shown
  // alongside the bundled demo corpus rather than replacing it. On a live
  // network only contract records are shown.
  const mergedHoldings = simulated
    ? [...holdings, ...HOLDINGS.filter((demo) => !holdings.some((h) => h.id === demo.id))]
    : holdings;
  const mergedCases = simulated
    ? [...cases, ...CASES.filter((demo) => !cases.some((c) => c.id === demo.id))]
    : cases;

  return {
    holdings: mergedHoldings.length > 0 ? mergedHoldings : HOLDINGS,
    cases: mergedCases.length > 0 ? mergedCases : CASES,
    domains: DOMAINS,
    live: true,
    network,
    stats:
      stats && !simulated
        ? {
            holdingsIndexed: stats.total,
            casesProcessed: cases.length || stats.total,
            domainsCovered: stats.domains || DOMAINS.length,
            citationsRecorded: stats.citations,
            distinguishments: stats.distinguishes,
            consistency: consistencyOf(stats),
            lastIndexed: new Date().toISOString(),
          }
        : CORPUS,
  };
}

function consistencyOf(stats: { follows: number; distinguishes: number }): number {
  const total = stats.follows + stats.distinguishes;
  if (total === 0) return CORPUS.consistency;
  return Math.round((stats.follows / total) * 100);
}

export function mapCase(item: import("@/lib/api/client").ApiCase): CaseRecord {
  return {
    id: item.case_id.replace(/^CASE-/, ""),
    domain: titleize(item.domain),
    domainSlug: item.domain,
    issue: item.issue || item.facts[0] || "Adjudication",
    facts: item.facts,
    verdict: (["APPROVED", "REJECTED", "PARTIAL"].includes(item.verdict) ? item.verdict : null) as CaseRecord["verdict"],
    status: item.status === "CONSENSUS" || item.holding_id ? "FINAL" : "PENDING",
    submitted: new Date((item.submitted_at ?? Math.floor(Date.now() / 1000)) * 1000).toISOString(),
    retrieved: item.precedent_used.map((holdingId) => ({
      holdingId: holdingId.replace(/^HLD-/, ""),
      similarity: 0,
      outcome: item.distinguished ? ("DISTINGUISHED" as const) : ("FOLLOWED" as const),
    })),
    panel: Array.from({ length: Math.max(1, item.panel_size || 5) }, (_, index) => ({
      index: index + 1,
      model: `validator-${index + 1}`,
      vote: (item.distinguished ? "DISTINGUISH" : "FOLLOW") as "FOLLOW" | "DISTINGUISH",
      reviewed: index === 0,
      note: item.reasoning || item.ratio,
    })),
    consensus: item.ratio,
    materialDifference: item.distinguishment_reason || undefined,
    distinguishment: item.distinguishment_reason || undefined,
    resultingHolding: item.holding_id ? item.holding_id.replace(/^HLD-/, "") : undefined,
    onChainRef: undefined,
  };
}
