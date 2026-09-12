"use client";

/**
 * The nav's connect control.
 *
 * Copy is literal on purpose: it says which step is happening (approve in
 * wallet / sign the message) rather than showing an indeterminate spinner, and
 * it never implies the wallet can write to the registry.
 */

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { cx } from "@/lib/components/ui/primitives";
import { shortAddress } from "./chains";
import { useWallet } from "./WalletProvider";

const INSTALL_URL = "https://metamask.io/download/";

export function WalletButton({ className }: { className?: string }) {
  const wallet = useWallet();
  const [open, setOpen] = useState(false);
  const wrapper = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: MouseEvent) => {
      if (wrapper.current && !wrapper.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const base =
    "inline-flex items-center gap-2 rounded-[7px] border px-[13px] py-[7px] text-[12px] transition-all duration-200 ease-precise";

  if (wallet.status === "unsupported") {
    return (
      <a
        href={INSTALL_URL}
        target="_blank"
        rel="noreferrer"
        title="HOLDING uses an injected browser wallet. Mobile WalletConnect wallets do not inject."
        className={cx(base, "border-white/[0.14] text-paper hover:border-copper/50 hover:text-copper", className)}
      >
        Get a wallet
      </a>
    );
  }

  if (wallet.status === "wrong-network") {
    return (
      <button
        type="button"
        onClick={() => void wallet.switchNetwork()}
        className={cx(base, "border-copper/45 bg-copper/[0.08] text-copper hover:bg-copper/[0.14]", className)}
      >
        Switch to {wallet.expectedChainName ?? "network"}
      </button>
    );
  }

  if (wallet.status !== "connected" || !wallet.address) {
    const label =
      wallet.status === "connecting"
        ? "Approve in wallet…"
        : wallet.status === "signing"
          ? "Sign the message…"
          : wallet.status === "loading"
            ? "Connect wallet"
            : "Connect wallet";
    return (
      <button
        type="button"
        onClick={() => void wallet.connect()}
        disabled={wallet.busy}
        className={cx(
          base,
          "border-white/[0.14] text-paper hover:border-copper/50 hover:text-copper",
          wallet.busy && "cursor-wait text-stone",
          className,
        )}
      >
        <span
          className={cx(
            "h-[5px] w-[5px] rounded-full",
            wallet.busy ? "animate-pulseSoft bg-copper" : "bg-white/25",
          )}
        />
        {label}
      </button>
    );
  }

  return (
    <div ref={wrapper} className={cx("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-expanded={open}
        className={cx(base, "border-white/[0.14] text-paper hover:border-copper/50 hover:text-copper")}
      >
        <span className="h-[5px] w-[5px] rounded-full bg-verdict" />
        <span className="font-mono text-[11px] tracking-[0.04em]">{shortAddress(wallet.address)}</span>
      </button>

      {open ? (
        <div className="absolute right-0 top-[calc(100%+8px)] z-50 w-[286px] border border-white/[0.1] bg-ink p-4 text-left shadow-[0_18px_40px_rgba(0,0,0,0.45)]">
          <p className="label">Signed in</p>
          <p className="mt-2 break-all font-mono text-[11.5px] leading-[1.6] text-paper">
            {wallet.address}
          </p>

          <div className="mt-3 space-y-[6px] border-t border-white/[0.07] pt-3">
            <Row label="Network" value={wallet.expectedChainName ?? (wallet.auth?.expected.mode ?? "—")} />
            <Row label="Wallet chain" value={wallet.chainId ? String(wallet.chainId) : "—"} />
            <Row
              label="Role"
              value={wallet.isOperator ? "Operator" : wallet.auth?.operator_allowlist?.configured ? "Not on the allowlist" : "Signed in"}
            />
            {wallet.sessionExpiresAt ? (
              <Row label="Session ends" value={new Date(wallet.sessionExpiresAt * 1000).toUTCString().slice(5, 22)} />
            ) : null}
          </div>

          <div className="mt-3 border-t border-white/[0.07] pt-3">
            <Link
              href="/developers#register"
              onClick={() => setOpen(false)}
              className="text-[12.5px] text-copper link-underline"
            >
              Register a source contract →
            </Link>
          </div>

          <p className="mt-3 border-t border-white/[0.07] pt-3 font-mono text-[10px] leading-[1.7] text-muted">
            A session can propose a source contract. Approving one — the step that
            writes to the registry — needs the operator key.
          </p>

          <button
            type="button"
            onClick={() => {
              wallet.disconnect();
              setOpen(false);
            }}
            className="mt-3 text-[12px] text-stone transition-colors hover:text-paper"
          >
            Disconnect
          </button>
        </div>
      ) : null}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{label}</span>
      <span className="font-mono text-[11px] text-stone">{value}</span>
    </div>
  );
}
