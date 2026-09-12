"use client";

/**
 * Wallet session state for the whole site.
 *
 * Connecting does three things, in order:
 *
 *   1. eth_requestAccounts  — the wallet's own popup (this is the step people
 *                             expect when they click "Connect")
 *   2. personal_sign        — a free, off-chain signature over a server nonce
 *   3. POST /auth/verify    — exchange the signature for a session token
 *
 * The session is stored in localStorage so a reload does not ask again, and it
 * is dropped the moment the wallet changes account or the token expires.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { WALLET_API_BASE, walletApi, type AuthConfigResponse, type SessionResponse } from "./api";
import { chainName, shortAddress as shorten } from "./chains";
import {
  WalletError,
  ensureChain,
  getInjectedProvider,
  personalSign,
  readChainId,
  requestAccounts,
  type Eip1193Provider,
} from "./provider";

const STORAGE_KEY = "holding.session.v1";

export type WalletStatus =
  | "loading"
  | "unsupported"
  | "disconnected"
  | "connecting"
  | "signing"
  | "wrong-network"
  | "connected";

interface WalletContextValue {
  status: WalletStatus;
  busy: boolean;
  address: string | null;
  displayAddress: string | null;
  chainId: number | null;
  expectedChainId: number | null;
  expectedChainName: string | null;
  isOperator: boolean;
  sessionExpiresAt: number | null;
  error: string | null;
  token: string | null;
  apiBase: string;
  auth: AuthConfigResponse | null;
  connect: () => Promise<void>;
  disconnect: () => void;
  switchNetwork: () => Promise<void>;
}

const WalletContext = createContext<WalletContextValue | null>(null);

function messageOf(error: unknown): string {
  if (error instanceof WalletError) return error.message;
  if (error instanceof Error) return error.message;
  return "Could not connect the wallet.";
}

export function WalletProvider({ children }: { children: ReactNode }) {
  const [provider, setProvider] = useState<Eip1193Provider | null>(null);
  const [status, setStatus] = useState<WalletStatus>("loading");
  const [address, setAddress] = useState<string | null>(null);
  const [chainId, setChainId] = useState<number | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [auth, setAuth] = useState<AuthConfigResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  const expectedChainId = auth?.expected.chain_id ?? null;

  const clearSession = useCallback(() => {
    if (typeof window !== "undefined") window.localStorage.removeItem(STORAGE_KEY);
    setToken(null);
    setSession(null);
    setAddress(null);
  }, []);

  const restore = useCallback(async () => {
    const injected = getInjectedProvider();
    setProvider(injected);

    if (typeof window !== "undefined") {
      const stored = window.localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const result = await walletApi.session(stored);
        if (result.ok) {
          setToken(stored);
          setSession(result.data);
          setAddress(result.data.address);
          if (injected) {
            try {
              setChainId(await readChainId(injected));
            } catch {
              /* the wallet may be locked; the session still stands */
            }
          }
          setStatus("connected");
          return;
        }
        window.localStorage.removeItem(STORAGE_KEY);
      }
    }
    setStatus(injected ? "disconnected" : "unsupported");
  }, []);

  useEffect(() => {
    void restore();
  }, [restore]);

  useEffect(() => {
    let active = true;
    void walletApi.authConfig().then((result) => {
      if (active && result.ok) setAuth(result.data);
    });
    return () => {
      active = false;
    };
  }, []);

  const connect = useCallback(async () => {
    setError(null);
    const injected = getInjectedProvider();
    if (!injected) {
      setProvider(null);
      setStatus("unsupported");
      setError("No browser wallet found. Install MetaMask, Rabby or Brave, then reload.");
      return;
    }
    setProvider(injected);
    setStatus("connecting");
    try {
      // Always request: this is what opens the wallet's own popup.
      const accounts = await requestAccounts(injected);
      if (!accounts.length) throw new WalletError("UNKNOWN", "Your wallet returned no accounts.");
      const account = accounts[0].toLowerCase();
      setAddress(account);

      const configResult = await walletApi.authConfig();
      if (!configResult.ok) throw new WalletError("UNKNOWN", configResult.error);
      setAuth(configResult.data);

      const expected = configResult.data.expected.chain_id;
      if (expected > 0) {
        const current = await readChainId(injected);
        setChainId(current);
        if (current !== expected) {
          const after = await ensureChain(injected, expected);
          setChainId(after);
          if (after !== expected) {
            setStatus("wrong-network");
            setError(`Switch your wallet to ${chainName(expected)} to continue.`);
            return;
          }
        }
      }

      setStatus("signing");
      const nonceResult = await walletApi.nonce(account);
      if (!nonceResult.ok) throw new WalletError("UNKNOWN", nonceResult.error);

      const signature = await personalSign(injected, nonceResult.data.message, account);
      const verifyResult = await walletApi.verify({
        address: account,
        nonce: nonceResult.data.nonce,
        signature,
      });
      if (!verifyResult.ok) throw new WalletError("UNKNOWN", verifyResult.error);

      if (typeof window !== "undefined") {
        window.localStorage.setItem(STORAGE_KEY, verifyResult.data.token);
      }
      setToken(verifyResult.data.token);
      setSession(verifyResult.data.session as SessionResponse);
      setStatus("connected");
    } catch (caught) {
      setError(messageOf(caught));
      setStatus("disconnected");
    }
  }, []);

  const disconnect = useCallback(() => {
    clearSession();
    setError(null);
    setStatus(getInjectedProvider() ? "disconnected" : "unsupported");
  }, [clearSession]);

  const switchNetwork = useCallback(async () => {
    if (!provider || !expectedChainId || expectedChainId <= 0) return;
    setError(null);
    try {
      const after = await ensureChain(provider, expectedChainId);
      setChainId(after);
      if (after !== expectedChainId) {
        setStatus("wrong-network");
        setError(`Still on the wrong network. Select ${chainName(expectedChainId)} in your wallet.`);
      } else {
        setStatus(address && token ? "connected" : "disconnected");
      }
    } catch (caught) {
      setError(messageOf(caught));
    }
  }, [provider, expectedChainId, address, token]);

  // React when the wallet itself changes underneath us.
  useEffect(() => {
    if (!provider?.on) return;
    const onAccounts = (...args: never[]) => {
      const accounts = args[0] as unknown as string[] | undefined;
      const next = accounts?.[0]?.toLowerCase() ?? null;
      if (!next || (address && next !== address)) {
        clearSession();
        setStatus("disconnected");
      }
    };
    const onChain = (...args: never[]) => {
      const raw = args[0] as unknown as string | undefined;
      const next = raw ? Number.parseInt(String(raw), 16) : null;
      setChainId(next);
      if (expectedChainId && expectedChainId > 0 && next !== expectedChainId) {
        setStatus("wrong-network");
      }
    };
    provider.on("accountsChanged", onAccounts as never);
    provider.on("chainChanged", onChain as never);
    return () => {
      provider.removeListener?.("accountsChanged", onAccounts as never);
      provider.removeListener?.("chainChanged", onChain as never);
    };
  }, [provider, address, clearSession, expectedChainId]);

  const value = useMemo<WalletContextValue>(
    () => ({
      status,
      busy: status === "connecting" || status === "signing",
      address,
      displayAddress: address ? shorten(address) : null,
      chainId,
      expectedChainId,
      expectedChainName: expectedChainId && expectedChainId > 0 ? chainName(expectedChainId) : null,
      isOperator: Boolean(session?.is_operator),
      sessionExpiresAt: session?.expires_at ?? null,
      error,
      token,
      apiBase: WALLET_API_BASE,
      auth,
      connect,
      disconnect,
      switchNetwork,
    }),
    [status, address, chainId, expectedChainId, session, error, token, auth, connect, disconnect, switchNetwork],
  );

  return <WalletContext.Provider value={value}>{children}</WalletContext.Provider>;
}

export function useWallet(): WalletContextValue {
  const context = useContext(WalletContext);
  if (!context) throw new Error("useWallet must be used inside <WalletProvider>");
  return context;
}
