"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { cx } from "../ui/primitives";
import { WalletButton } from "@/lib/wallet/WalletButton";
import { Menu, X } from "lucide-react";

const LINKS = [
  { href: "/reporter", label: "Reporter" },
  { href: "/cases", label: "Cases" },
  { href: "/domains", label: "Domains" },
  { href: "/developers", label: "Developers" },
  { href: "/about", label: "About" },
];

const MOBILE_LINKS = [
  { href: "/", label: "Home" },
  { href: "/reporter", label: "Reporter" },
  { href: "/precedent", label: "Precedent" },
  { href: "/holdings", label: "Holdings" },
  { href: "/developers", label: "Devs" },
];

export interface NetworkBadge {
  mode: "DEMO" | "TESTNET" | "MAINNET";
  network: string;
  simulated: boolean;
  registry_address: string;
}

const PILL_TONE: Record<string, string> = {
  DEMO: "bg-copper/90",
  TESTNET: "bg-verdict/90",
  MAINNET: "bg-verdict/90",
};

export function Nav({ network }: { network?: NetworkBadge | null }) {
  const mode = network?.mode ?? "DEMO";
  const simulated = network?.simulated ?? true;
  const pathname = usePathname();
  const [scrolled, setScrolled] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 8);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  useEffect(() => setOpen(false), [pathname]);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <>
      <header
        className={cx(
          "sticky top-0 z-50 border-b transition-colors duration-300",
          scrolled
            ? "border-white/[0.08] bg-obsidian/85 backdrop-blur-[10px]"
            : "border-transparent bg-obsidian",
        )}
      >
        <div className="shell flex h-[58px] items-center justify-between gap-6">
          {/* wordmark */}
          <Link href="/" className="group flex h-[44px] items-center gap-[10px]">
            <Mark />
            <span className="font-mono text-[13px] font-medium uppercase tracking-[0.22em] text-paper">
              Holding
            </span>
          </Link>

          {/* desktop links */}
          <nav className="hidden items-center gap-8 md:flex">
            {LINKS.map((l) => (
              <Link
                key={l.href}
                href={l.href}
                className={cx(
                  "relative text-[12px] tracking-[0.01em] transition-colors duration-150",
                  isActive(l.href) ? "text-paper" : "text-stone hover:text-paper",
                )}
              >
                {l.label}
                {isActive(l.href) ? (
                  <span className="absolute -bottom-[6px] left-0 h-px w-full bg-copper" />
                ) : null}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-3">
            <span className="hidden items-center gap-2 rounded-[5px] border border-white/[0.12] px-[8px] py-[3px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone sm:inline-flex">
              <span className={`h-[5px] w-[5px] rounded-full ${PILL_TONE[mode] ?? "bg-copper/90"}`} />
              {mode}
            </span>
            <WalletButton className="hidden md:inline-flex" />
            <button
              aria-label="Menu"
              onClick={() => setOpen((v) => !v)}
              className="inline-flex h-[32px] w-[32px] items-center justify-center rounded-[6px] border border-white/[0.12] text-stone transition-colors hover:text-paper md:hidden"
            >
              {open ? <X size={15} strokeWidth={1.5} /> : <Menu size={15} strokeWidth={1.5} />}
            </button>
          </div>
        </div>

        {/* mobile drawer */}
        {open ? (
          <div className="border-t border-white/[0.08] bg-obsidian md:hidden">
            <div className="shell py-4">
              <p className="mb-3 font-mono text-[9px] uppercase tracking-[0.18em] text-muted">
                {mode}
                {simulated ? " · simulated records" : " · live contract data"}
              </p>
              {[{ href: "/", label: "Home" }, ...LINKS].map((l) => (
                <Link
                  key={l.href}
                  href={l.href}
                  className={cx(
                    "block border-b border-white/[0.05] py-3 text-[15px] last:border-b-0",
                    isActive(l.href) ? "text-copper" : "text-stone",
                  )}
                >
                  {l.label}
                </Link>
              ))}
              <Link href="/precedent" className="block py-3 text-[15px] text-stone">
                Precedent console
              </Link>
              <div className="mt-3 flex items-center justify-between border-t border-white/[0.06] pt-3">
                <span className="font-mono text-[9px] uppercase tracking-[0.18em] text-muted">Wallet</span>
                <WalletButton />
              </div>
            </div>
          </div>
        ) : null}
      </header>

      {/* mobile bottom nav */}
      <nav className="fixed bottom-0 left-0 right-0 z-50 border-t border-white/[0.08] bg-obsidian/95 backdrop-blur-[10px] md:hidden">
        <div className="grid grid-cols-5">
          {MOBILE_LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={cx(
                "flex flex-col items-center gap-[5px] py-[9px] font-mono text-[9px] uppercase tracking-[0.12em] transition-colors",
                isActive(l.href) ? "text-copper" : "text-stone",
              )}
            >
              <span
                className={cx(
                  "h-[3px] w-[3px] rounded-full",
                  isActive(l.href) ? "bg-copper" : "bg-white/20",
                )}
              />
              {l.label}
            </Link>
          ))}
        </div>
      </nav>
    </>
  );
}

export function Mark({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 20 20" fill="none" aria-hidden>
      <rect x="0.5" y="0.5" width="19" height="19" rx="4.5" stroke="rgba(255,255,255,0.14)" />
      <path d="M5.5 5v10M14.5 5v10M5.5 10h9" stroke="#D7A45A" strokeWidth="1.25" strokeLinecap="square" />
      <path d="M5.5 15h9" stroke="#F3F0E8" strokeWidth="1.25" strokeLinecap="square" opacity="0.55" />
    </svg>
  );
}
