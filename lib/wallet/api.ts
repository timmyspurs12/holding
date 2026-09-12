/**
 * Browser-side calls to the Reporter's wallet and operator endpoints.
 *
 * Server components read through lib/api/client.ts (cached, server-side). This
 * module is deliberately separate: it runs in the browser, it is never cached,
 * and it carries the session token.
 *
 * By default calls are same-origin under /api/reporter/*. Set
 * NEXT_PUBLIC_HOLDING_API_URL only when the API is hosted on a different
 * origin (that origin then needs CORS_ORIGINS to include the site).
 */

import type { NetworkInfo } from "@/lib/api/client";

const EXTERNAL = (process.env.NEXT_PUBLIC_HOLDING_API_URL || "").replace(/\/+$/, "");

// Empty means "same origin": the browser calls /api/reporter/* and Next proxies
// it to the Reporter API (see next.config.mjs). That keeps the API's address out
// of the page, avoids CORS entirely, and works behind any preview proxy.
export const WALLET_API_BASE = EXTERNAL;
export const WALLET_API_PREFIX = EXTERNAL ? "" : "/api/reporter";
export const WALLET_API_CONFIGURED = true;

export type Result<T> =
  | { ok: true; status: number; data: T }
  | { ok: false; status: number; error: string };

async function call<T>(
  path: string,
  init: RequestInit & { token?: string } = {},
): Promise<Result<T>> {
  if (!WALLET_API_CONFIGURED) {
    return { ok: false, status: 0, error: "The Reporter API is not reachable." };
  }
  const headers: Record<string, string> = {
    accept: "application/json",
    ...(init.body ? { "content-type": "application/json" } : {}),
    ...((init.headers as Record<string, string>) ?? {}),
  };
  if (init.token) headers["X-Session-Token"] = init.token;

  try {
    const response = await fetch(`${WALLET_API_BASE}${WALLET_API_PREFIX}${path}`, {
      ...init,
      headers,
      cache: "no-store",
    });
    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = null;
      }
    }
    if (!response.ok) {
      const detail =
        payload && typeof payload === "object" && "detail" in payload
          ? String((payload as { detail: unknown }).detail)
          : `Request failed (${response.status})`;
      return { ok: false, status: response.status, error: detail };
    }
    return { ok: true, status: response.status, data: payload as T };
  } catch (error) {
    return {
      ok: false,
      status: 0,
      error:
        error instanceof Error
          ? "Cannot reach the Reporter API. Is it running on the host the site proxies to?"
          : "Request failed",
    };
  }
}

/* ------------------------------- types -------------------------------- */

export interface AuthConfigResponse {
  wallet_auth: {
    available: boolean;
    signer_available: boolean;
    secret_configured: boolean;
    statement: string;
    nonce_ttl_seconds: number;
    session_ttl_seconds: number;
  };
  expected: {
    origin: string;
    chain_id: number;
    chain_id_hex: string | null;
    network: string;
    mode: string;
  };
  operator_allowlist: { configured: boolean; count: number };
  note: string;
}

export interface NonceResponse {
  address: string;
  nonce: string;
  message: string;
  chain_id: number;
  issued_at: number;
  expires_at: number;
}

export interface WalletSession {
  address: string;
  short_address: string;
  expires_at: number;
  is_operator: boolean;
  operator_allowlist: boolean;
}

export interface VerifyResponse {
  token: string;
  token_type: string;
  header: string;
  session: WalletSession;
  network: { mode: string; network: string; chain_id: number };
  grants: string[];
  note: string;
}

export interface SessionResponse extends WalletSession {
  network: { mode: string | null; chain_id: number | null };
  seconds_remaining: number;
}

export interface SourceProposal {
  proposal_id: string;
  contract_address: string;
  domain: string;
  contract_class: string;
  label: string;
  deploy_tx: string;
  notes: string;
  submitted_by: string;
  submitted_at: number;
  status: "PENDING" | "APPROVED" | "REJECTED";
  decided_at: number | null;
  decided_by: string;
  decision_note: string;
  transaction_reference: string | null;
  simulated: boolean;
  short_address?: string;
}

export interface ProposalsResponse {
  network: NetworkInfo;
  total: number;
  counts: { PENDING: number; APPROVED: number; REJECTED: number };
  items: SourceProposal[];
  note: string;
}

export interface ProposeInput {
  contract_address: string;
  domain: string;
  contract_class: string;
  label?: string;
  deploy_tx?: string;
  notes?: string;
}

/* -------------------------------- api --------------------------------- */

export const walletApi = {
  authConfig: () => call<AuthConfigResponse>("/auth/config"),
  nonce: (address: string) =>
    call<NonceResponse>(`/auth/nonce?address=${encodeURIComponent(address)}`),
  verify: (body: { address: string; nonce: string; signature: string }) =>
    call<VerifyResponse>("/auth/verify", { method: "POST", body: JSON.stringify(body) }),
  session: (token: string) => call<SessionResponse>("/auth/session", { token }),
  me: (token: string) =>
    call<{ session: WalletSession; proposals: SourceProposal[]; can_do: string[]; cannot_do: string[] }>(
      "/operator/me",
      { token },
    ),
  proposals: (status = "") =>
    call<ProposalsResponse>(`/operator/source-contracts${status ? `?status=${status}` : ""}`),
  propose: (token: string, body: ProposeInput, idempotencyKey: string) =>
    call<{ proposal_id: string; status: string; submitted_by: string; next: string }>(
      "/operator/source-contracts",
      {
        method: "POST",
        token,
        body: JSON.stringify(body),
        headers: { "Idempotency-Key": idempotencyKey },
      },
    ),
};
