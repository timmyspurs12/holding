/**
 * Minimal EIP-1193 client. No SDK, no WalletConnect project id, no provider
 * abstraction layer — just the four calls HOLDING needs.
 *
 * Supported: any injected wallet (MetaMask, Rabby, Brave, Frame, …) that
 * exposes `window.ethereum`. Mobile wallets held behind WalletConnect do not
 * inject, so they are not supported; the UI says so instead of failing
 * silently.
 */

import { GENLAYER_CHAINS, type ChainSpec } from "./chains";

export type WalletErrorCode =
  | "NO_PROVIDER"
  | "USER_REJECTED"
  | "REQUEST_PENDING"
  | "UNKNOWN_CHAIN"
  | "UNKNOWN";

export class WalletError extends Error {
  code: WalletErrorCode;

  constructor(code: WalletErrorCode, message: string) {
    super(message);
    this.name = "WalletError";
    this.code = code;
  }
}

export interface Eip1193Provider {
  request(args: { method: string; params?: unknown[] | Record<string, unknown> }): Promise<unknown>;
  on?(event: string, handler: (...args: never[]) => void): void;
  removeListener?(event: string, handler: (...args: never[]) => void): void;
  isMetaMask?: boolean;
  /** Present when several wallets are installed at once. */
  providers?: Eip1193Provider[];
}

declare global {
  interface Window {
    ethereum?: Eip1193Provider;
  }
}

export function getInjectedProvider(): Eip1193Provider | null {
  if (typeof window === "undefined") return null;
  const injected = window.ethereum;
  if (!injected) return null;
  // Brave and some multi-wallet setups expose an array behind window.ethereum.
  if (Array.isArray(injected.providers) && injected.providers.length > 0) {
    return injected.providers[0];
  }
  return injected;
}

function normalise(error: unknown): WalletError {
  const code = (error as { code?: unknown })?.code;
  const message = error instanceof Error ? error.message : String(error ?? "");
  if (code === 4001) {
    return new WalletError("USER_REJECTED", "You declined the request in your wallet.");
  }
  if (code === -32002) {
    return new WalletError(
      "REQUEST_PENDING",
      "Your wallet already has a connection request open. Check the wallet window.",
    );
  }
  if (code === 4902 || /unrecognized chain/i.test(message)) {
    return new WalletError("UNKNOWN_CHAIN", "This network is not in your wallet yet.");
  }
  return new WalletError("UNKNOWN", message || "The wallet request failed.");
}

export async function requestAccounts(provider: Eip1193Provider): Promise<string[]> {
  try {
    const accounts = (await provider.request({ method: "eth_requestAccounts" })) as string[];
    return Array.isArray(accounts) ? accounts : [];
  } catch (error) {
    throw normalise(error);
  }
}

export async function readAccounts(provider: Eip1193Provider): Promise<string[]> {
  try {
    const accounts = (await provider.request({ method: "eth_accounts" })) as string[];
    return Array.isArray(accounts) ? accounts : [];
  } catch {
    return [];
  }
}

export async function readChainId(provider: Eip1193Provider): Promise<number> {
  const raw = (await provider.request({ method: "eth_chainId" })) as string;
  return typeof raw === "string" ? Number.parseInt(raw, 16) : Number(raw);
}

function hexChainId(id: number): string {
  return `0x${id.toString(16)}`;
}

/**
 * Switch to `id`, adding the network first if the wallet has never seen it.
 * Resolves to the chain id the wallet ended up on — callers compare, they do
 * not assume.
 */
export async function ensureChain(provider: Eip1193Provider, id: number): Promise<number> {
  const spec: ChainSpec | null = GENLAYER_CHAINS[id] ?? null;
  try {
    await provider.request({
      method: "wallet_switchEthereumChain",
      params: [{ chainId: hexChainId(id) }],
    });
  } catch (error) {
    const walletError = normalise(error);
    if (walletError.code === "UNKNOWN_CHAIN" || !spec) {
      if (!spec) throw new WalletError("UNKNOWN_CHAIN", `HOLDING does not know chain ${id}.`);
      try {
        await provider.request({
          method: "wallet_addEthereumChain",
          params: [
            {
              chainId: spec.hex,
              chainName: spec.name,
              rpcUrls: [spec.rpc],
              nativeCurrency: { name: "GenLayer", symbol: spec.symbol, decimals: 18 },
              ...(spec.explorer ? { blockExplorerUrls: [spec.explorer] } : {}),
            },
          ],
        });
      } catch (addError) {
        throw normalise(addError);
      }
    } else if (walletError.code !== "USER_REJECTED") {
      throw walletError;
    } else {
      throw walletError;
    }
  }
  return readChainId(provider);
}

function toHex(text: string): string {
  const bytes = new TextEncoder().encode(text);
  let out = "0x";
  for (const byte of bytes) out += byte.toString(16).padStart(2, "0");
  return out;
}

/** `personal_sign` — off-chain, free, and cannot move funds. */
export async function personalSign(
  provider: Eip1193Provider,
  message: string,
  address: string,
): Promise<string> {
  try {
    const signature = (await provider.request({
      method: "personal_sign",
      params: [toHex(message), address],
    })) as string;
    return signature ?? "";
  } catch (error) {
    throw normalise(error);
  }
}
