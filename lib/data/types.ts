export type Verdict = "APPROVED" | "REJECTED" | "PARTIAL";
export type AppealStatus = "UPHELD" | "OVERTURNED" | "SURVIVED" | "PENDING";
export type Authority = "HIGH" | "MODERATE" | "DEVELOPING";

export interface EvidenceItem {
  label: string;
  kind: "DOCUMENT" | "TRANSCRIPT" | "WEB" | "LEDGER" | "IMAGE";
  hash: string;
}

export interface Holding {
  id: string;
  originCase: string;
  domain: string;
  domainSlug: string;
  contractClass: string;
  issue: string;
  issueLong: string;
  facts: string[];
  verdict: Verdict;
  reasonCodes: string[];
  ratio: string;
  evidence: EvidenceItem[];
  panelSize: number;
  appeal: AppealStatus;
  citations: number;
  distinguishedBy: number;
  finalityTs: string;
  authority: Authority;
  authorityBreakdown: {
    finality: number;
    appeal: number;
    citations: number;
    consistency: number;
  };
  derivedFrom: string[];
  citedBy: string[];
  distinguishes: string[];
  onChainRef: string;
}

export interface RetrievedHolding {
  holdingId: string;
  similarity: number;
  outcome: "FOLLOWED" | "DISTINGUISHED" | "CITED";
  note?: string;
}

export interface PanelMember {
  index: number;
  model: string;
  vote: "FOLLOW" | "DISTINGUISH";
  reviewed: boolean;
  note: string;
}

export interface CaseRecord {
  id: string;
  domain: string;
  domainSlug: string;
  issue: string;
  facts: string[];
  verdict: Verdict | null;
  status: "PENDING" | "FINAL";
  submitted: string;
  retrieved: RetrievedHolding[];
  panel: PanelMember[];
  consensus: string;
  materialDifference?: string;
  distinguishment?: string;
  resultingHolding?: string;
  onChainRef?: string;
}

export interface DomainSummary {
  name: string;
  slug: string;
  holdings: number;
  consistency: number;
  followed: number;
  distinguished: number;
  velocity: string;
  leadingIssue: string;
}

export const IS_DEMO = true;
