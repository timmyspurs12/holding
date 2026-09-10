/**
 * Reporter API client.
 *
 * The frontend never decides what matters: retrieval, ranking and authority are
 * computed by the registry contract and served by the Reporter. This module only
 * fetches typed JSON and maps it into the shapes the UI renders.
 *
 * If HOLDING_API_URL / NEXT_PUBLIC_HOLDING_API_URL is unset, every call returns
 * null and the site falls back to its labelled demo corpus.
 */

const RAW =
  process.env.NEXT_PUBLIC_HOLDING_API_URL ||
  process.env.HOLDING_API_URL ||
  "";

export const API_BASE = RAW.replace(/\/+$/, "");
export const API_CONFIGURED = API_BASE.length > 0;

export interface NetworkInfo {
  mode: "DEMO" | "TESTNET" | "MAINNET";
  network: string;
  chain_id: number | null;
  rpc_url: string;
  registry_address: string;
  adjudicator_address: string;
  simulated: boolean;
  note: string;
}

export interface ApiAuthority {
  score: number;
  score_bp: number;
  band: "HIGH" | "MODERATE" | "DEVELOPING";
  components_bp: Record<string, number>;
  weights_bp: Record<string, number>;
  breakdown: {
    component: string;
    value_bp: number;
    weight_bp: number;
    contribution_bp: number;
    meaning: string;
  }[];
  formula: string;
  explanation: string;
}

export interface ApiHolding {
  holding_id: string;
  display_id: string;
  case_id: string;
  domain: string;
  contract_class: string;
  issue: string;
  facts_digest: string;
  verdict: string;
  reason_codes: string[];
  ratio: string;
  evidence_hashes: string[];
  panel_size: number;
  status: string;
  finality_timestamp: number | null;
  created_at: number | null;
  authority_bp: number;
  citation_count: number;
  distinguishment_count: number;
  parent_holdings: string[];
  contract_address: string | null;
  transaction_reference: string | null;
  finality: {
    status: string;
    tx_status_code: number | null;
    execution_result: string;
    finality_timestamp: number | null;
    appeal_status: string;
    appeal_outcome: string;
  };
  authority: ApiAuthority | null;
  provenance: {
    case_id: string;
    source_contract: string | null;
    source_tx: string | null;
    holding_hash: string | null;
    created_at: number | null;
    schema_version: string;
    mode: string;
    simulated: boolean;
  };
  distinguishment: string;
  simulated: boolean;
}

export interface ApiCitation {
  source_holding_id: string;
  target_holding_id: string;
  relationship: "CITES" | "FOLLOWS" | "DISTINGUISHES";
  case_id: string;
  created_at: number;
  direction: "outgoing" | "incoming";
}

export interface ApiCase {
  case_id: string;
  status: string;
  domain: string;
  contract_class: string;
  facts: string[];
  verdict: string;
  ratio: string;
  issue: string;
  reason_codes: string[];
  precedent_used: string[];
  followed: boolean;
  distinguished: boolean;
  distinguishment_reason: string;
  reasoning: string;
  panel_size: number;
  submitted_at: number | null;
  holding_id: string | null;
  simulated: boolean;
}

export interface ApiPrecedentHit {
  holding_id: string;
  display_id: string;
  case_id: string;
  domain: string;
  issue: string;
  ratio: string;
  verdict: string;
  similarity: number;
  similarity_bp: number;
  authority_bp: number;
  authority: ApiAuthority | null;
  status: string;
  citation_count: number;
  distinguishment_count: number;
  created_at: number | null;
  relationship: string;
}

export interface ApiStats {
  sequence: number;
  total: number;
  final: number;
  pending: number;
  rejected: number;
  unverified: number;
  citations: number;
  follows: number;
  distinguishes: number;
  domains: number;
  schema_version: string;
  embedding_model: string;
  embedding_dim: number;
  mode: string;
  simulated: boolean;
  authority_bands?: Record<string, number>;
  network?: NetworkInfo;
}

export interface ApiDomain {
  domain: string;
  holdings: number;
  final: number;
  follows: number;
  distinguishes: number;
}

export interface Envelope<T> {
  network: NetworkInfo;
  total: number;
  limit: number;
  offset: number;
  items: T[];
}

type Params = Record<string, string | number | undefined | null>;

function url(path: string, params: Params = {}): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    search.set(key, String(value));
  }
  const query = search.toString();
  return `${API_BASE}${path}${query ? `?${query}` : ""}`;
}

async function getJson<T>(path: string, params: Params = {}, revalidate = 15): Promise<T | null> {
  if (!API_CONFIGURED) return null;
  try {
    const response = await fetch(url(path, params), {
      headers: { accept: "application/json" },
      next: { revalidate },
    } as RequestInit & { next?: { revalidate: number } });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch (error) {
    if (process.env.NODE_ENV !== "production") console.warn(`[reporter] ${path} failed`, error);
    return null;
  }
}

export const api = {
  health: () => getJson<{ status: string; network: NetworkInfo; registry: { reachable: boolean } }>("/health", {}, 5),
  stats: () => getJson<ApiStats>("/stats"),
  domains: () => getJson<Envelope<ApiDomain>>("/domains"),
  holdings: (params: Params = {}) => getJson<Envelope<ApiHolding>>("/holdings", params),
  search: (q: string, params: Params = {}) => getJson<Envelope<ApiHolding>>("/holdings/search", { q, ...params }),
  holding: (id: string) => getJson<ApiHolding>(`/holdings/${encodeURIComponent(id)}`),
  citations: (id: string) => getJson<Envelope<ApiCitation>>(`/holdings/${encodeURIComponent(id)}/citations`),
  precedent: (id: string, k = 3) => getJson<Envelope<ApiPrecedentHit>>(`/holdings/${encodeURIComponent(id)}/precedent`, { k }),
  distinguishments: (id: string) =>
    getJson<Envelope<{ holding_id: string; case_id: string; issue: string; ratio: string; verdict: string; created_at: number; reason: string }>>(
      `/holdings/${encodeURIComponent(id)}/distinguishments`,
    ),
  cases: () => getJson<Envelope<ApiCase>>("/cases"),
  case: (id: string) => getJson<ApiCase & { holding?: ApiHolding }>(`/cases/${encodeURIComponent(id)}`),
};
