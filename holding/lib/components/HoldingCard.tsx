import Link from "next/link";
import type { Holding } from "@/lib/data/types";
import { Label, VerdictTag, AuthorityTag, AppealTag, cx } from "./ui/primitives";
import { fmtDate } from "@/lib/data";

export function HoldingCard({ holding, compact }: { holding: Holding; compact?: boolean }) {
  return (
    <Link
      href={`/holdings/${holding.id}`}
      className={cx(
        "group block rounded-[9px] border border-white/[0.08] bg-ink p-5 transition-all duration-200 ease-precise",
        "hover:-translate-y-[1px] hover:border-copper/35 hover:bg-ink2",
      )}
    >
      <div className="flex items-start justify-between gap-4">
        <span className="font-mono text-[12px] tracking-[0.1em] text-paper transition-colors group-hover:text-copper">
          #{holding.id}
        </span>
        <span className="label text-right">{holding.domain}</span>
      </div>

      <div className="mt-5 border-t border-white/[0.06] pt-4">
        <Label>Issue</Label>
        <p className="mt-2 text-[14.5px] leading-[1.5] text-paper">{holding.issue}</p>
      </div>

      {!compact ? (
        <p className="mt-3 line-clamp-2 text-[13px] leading-[1.65] text-stone">{holding.ratio}</p>
      ) : null}

      <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-white/[0.06] pt-4">
        <VerdictTag verdict={holding.verdict} />
        <AuthorityTag authority={holding.authority} />
        <AppealTag status={holding.appeal} />
      </div>

      <div className="mt-4 grid grid-cols-2 gap-4">
        <div>
          <Label>Citations</Label>
          <p className="mt-1 font-mono text-[15px] tabular-nums text-paper">
            {String(holding.citations).padStart(2, "0")}
          </p>
        </div>
        <div>
          <Label>Distinguished</Label>
          <p className="mt-1 font-mono text-[15px] tabular-nums text-paper">
            {String(holding.distinguishedBy).padStart(2, "0")}
          </p>
        </div>
      </div>

      <div className="mt-4 flex items-center justify-between border-t border-white/[0.06] pt-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Finality {fmtDate(holding.finalityTs)}
        </span>
        <span className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          Open →
        </span>
      </div>
    </Link>
  );
}

/** Dense table row for the holdings index. */
export function HoldingRow({ holding }: { holding: Holding }) {
  return (
    <Link
      href={`/holdings/${holding.id}`}
      className="group grid grid-cols-12 items-center gap-4 border-b border-white/[0.06] py-4 transition-colors duration-150 hover:bg-white/[0.02]"
    >
      <span className="col-span-3 font-mono text-[12px] tracking-[0.1em] text-paper group-hover:text-copper sm:col-span-2">
        #{holding.id}
      </span>
      <span className="col-span-9 text-[13.5px] text-stone sm:col-span-4">{holding.issue}</span>
      <span className="col-span-4 hidden text-[12px] text-muted sm:block">{holding.domain}</span>
      <span className="col-span-1 hidden md:block">
        <VerdictTag verdict={holding.verdict} />
      </span>
      <span className="col-span-2 hidden text-right font-mono text-[11px] tabular-nums text-stone md:block">
        {String(holding.citations).padStart(2, "0")}
      </span>
      <span className="col-span-2 hidden text-right font-mono text-[11px] tabular-nums text-stone md:block">
        {fmtDate(holding.finalityTs)}
      </span>
    </Link>
  );
}
