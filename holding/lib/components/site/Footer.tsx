import Link from "next/link";
import { Label, Rule } from "../ui/primitives";
import { Mark } from "./Nav";

const COLS = [
  {
    title: "Product",
    links: [
      { href: "/reporter", label: "Reporter" },
      { href: "/holdings", label: "Holdings index" },
      { href: "/cases", label: "Cases" },
      { href: "/domains", label: "Domains" },
      { href: "/precedent", label: "Precedent console" },
    ],
  },
  {
    title: "Build",
    links: [
      { href: "/developers", label: "Developers" },
      { href: "/integrations", label: "Integrations" },
      { href: "/developers#schema", label: "Holding schema" },
      { href: "/developers#sdk", label: "Emitter SDK" },
    ],
  },
  {
    title: "Reference",
    links: [
      { href: "/about", label: "About HOLDING" },
      { href: "/about#sources", label: "Sources" },
      { href: "/about#why", label: "Why precedent" },
    ],
  },
];

const EXTERNAL = [
  { href: "https://docs.genlayer.com/", label: "GenLayer docs" },
  {
    href: "https://docs.genlayer.com/developers/intelligent-contracts/advanced-features/vector-store",
    label: "Vector Store",
  },
  { href: "https://genlayer.com/use-cases", label: "GenLayer use cases" },
];

export function Footer() {
  return (
    <footer className="mt-24 border-t border-white/[0.08] pb-28 pt-16 md:pb-16">
      <div className="shell">
        <div className="grid gap-12 md:grid-cols-12">
          <div className="md:col-span-4">
            <div className="flex items-center gap-[10px]">
              <Mark />
              <span className="font-mono text-[13px] uppercase tracking-[0.22em] text-paper">Holding</span>
            </div>
            <p className="mt-5 max-w-[30ch] text-[13px] leading-[1.7] text-stone">
              The precedent layer for GenLayer. Every decision becomes precedent.
            </p>
            <p className="mt-6 max-w-[34ch] font-mono text-[10px] uppercase leading-[1.7] tracking-[0.12em] text-muted">
              Demo environment · simulated records · not live GenLayer data
            </p>
          </div>

          {COLS.map((col) => (
            <div key={col.title} className="md:col-span-2 md:col-start-auto">
              <Label>{col.title}</Label>
              <ul className="mt-2">
                {col.links.map((l) => (
                  <li key={l.href}>
                    <Link
                      href={l.href}
                      className="block py-[8px] text-[13px] text-stone transition-colors duration-150 hover:text-paper"
                    >
                      {l.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ))}

          <div className="md:col-span-2">
            <Label>Ecosystem</Label>
            <ul className="mt-4 space-y-[10px]">
              {EXTERNAL.map((l) => (
                <li key={l.href}>
                  <a
                    href={l.href}
                    target="_blank"
                    rel="noreferrer"
                    className="block py-[8px] text-[13px] text-stone transition-colors duration-150 hover:text-paper"
                  >
                    {l.label}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <Rule className="my-12" />

        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
            © {new Date().getFullYear()} HOLDING · Built on GenLayer Intelligent Contracts
          </p>
          <div className="flex items-center gap-6">
            <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
              Mainnet target Q4 2026
            </span>
            <Link
              href="/about#sources"
              className="inline-block py-[8px] font-mono text-[10px] uppercase tracking-[0.14em] text-stone hover:text-copper"
            >
              Sources
            </Link>
          </div>
        </div>
      </div>
    </footer>
  );
}
