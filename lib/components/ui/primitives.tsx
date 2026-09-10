import Link from "next/link";
import type { ReactNode } from "react";
import type { Verdict, AppealStatus, Authority } from "@/lib/data/types";

export const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");

/* ------------------------------------------------------------------ */
/* Typographic atoms                                                    */
/* ------------------------------------------------------------------ */
export function Label({
  children,
  className,
  light,
}: {
  children: ReactNode;
  className?: string;
  light?: boolean;
}) {
  return (
    <span className={cx("label", light && "text-muted", className)}>{children}</span>
  );
}

export function Rule({ className, light }: { className?: string; light?: boolean }) {
  return <div className={cx(light ? "rule-light" : "rule", className)} />;
}

export function DemoTag({ className }: { className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-[6px] rounded-[4px] border border-white/[0.14] px-[7px] py-[2px]",
        "font-mono text-[9px] uppercase tracking-[0.18em] text-stone",
        className,
      )}
    >
      <span className="h-[4px] w-[4px] rounded-full bg-copper/80" />
      Demo
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Semantic tags                                                        */
/* ------------------------------------------------------------------ */
const verdictColor: Record<Verdict, string> = {
  APPROVED: "text-verdict border-verdict/30 bg-verdict/[0.07]",
  REJECTED: "text-dissent border-dissent/30 bg-dissent/[0.07]",
  PARTIAL: "text-copper border-copper/30 bg-copper/[0.07]",
};
const verdictSwatch: Record<Verdict, string> = {
  APPROVED: "bg-verdict",
  REJECTED: "bg-dissent",
  PARTIAL: "bg-copper",
};

export function VerdictTag({
  verdict,
  size = "sm",
  className,
}: {
  verdict: Verdict | string;
  size?: "sm" | "lg";
  className?: string;
}) {
  const v = verdict as Verdict;
  const tone = verdictColor[v] ?? "text-stone border-white/15 bg-white/[0.03]";
  const swatch = verdictSwatch[v] ?? "bg-stone";
  return (
    <span
      className={cx(
        "inline-flex items-center gap-2 rounded-[5px] border font-mono uppercase tracking-[0.14em]",
        size === "sm" ? "px-[8px] py-[3px] text-[10px]" : "px-[12px] py-[6px] text-[12px]",
        tone,
        className,
      )}
    >
      <span className={cx("h-[5px] w-[5px] rounded-[1px]", swatch)} />
      {verdict}
    </span>
  );
}

export function MetaTag({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "copper" | "green" | "red" | "blue";
  className?: string;
}) {
  const tones = {
    neutral: "text-stone border-white/[0.12]",
    copper: "text-copper border-copper/35 bg-copper/[0.06]",
    green: "text-verdict border-verdict/30 bg-verdict/[0.06]",
    red: "text-dissent border-dissent/30 bg-dissent/[0.06]",
    blue: "text-info border-info/30 bg-info/[0.06]",
  };
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-[5px] border px-[7px] py-[2px] font-mono text-[10px] uppercase tracking-[0.14em]",
        tones[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function AuthorityTag({ authority }: { authority: Authority | string }) {
  const tone =
    authority === "HIGH" ? "copper" : authority === "MODERATE" ? "blue" : "neutral";
  return <MetaTag tone={tone as any}>{authority}</MetaTag>;
}

export function AppealTag({ status }: { status: AppealStatus | string }) {
  const tone =
    status === "UPHELD" ? "green" : status === "OVERTURNED" ? "red" : status === "PENDING" ? "copper" : "neutral";
  return <MetaTag tone={tone as any}>{status}</MetaTag>;
}

/* ------------------------------------------------------------------ */
/* Editorial meter — bars, not a dial                                   */
/* ------------------------------------------------------------------ */
export function Meter({
  label,
  value,
  max = 100,
  suffix = "%",
  note,
  className,
}: {
  label: string;
  value: number;
  max?: number;
  suffix?: string;
  note?: string;
  className?: string;
}) {
  const pct = Math.round((value / max) * 100);
  const cells = 20;
  const filled = Math.round((pct / 100) * cells);
  return (
    <div className={cx("group", className)}>
      <div className="flex items-baseline justify-between">
        <Label>{label}</Label>
        <span className="font-mono text-[11px] tabular-nums text-paper">
          {value}
          {suffix}
        </span>
      </div>
      <div className="mt-[7px] flex gap-[2px]" aria-hidden>
        {Array.from({ length: cells }).map((_, i) => (
          <span
            key={i}
            className={cx(
              "h-[6px] flex-1 rounded-[1px] transition-colors duration-300",
              i < filled ? "bg-copper/85" : "bg-white/[0.07]",
            )}
          />
        ))}
      </div>
      {note ? <p className="mt-[6px] font-mono text-[10px] text-muted">{note}</p> : null}
      <span className="sr-only">{`${label}: ${value}${suffix}`}</span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Section heading                                                      */
/* ------------------------------------------------------------------ */
export function SectionHeading({
  eyebrow,
  title,
  text,
  aside,
  className,
}: {
  eyebrow?: string;
  title: ReactNode;
  text?: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("grid gap-6 md:grid-cols-12 md:gap-10", className)}>
      <div className="md:col-span-7">
        {eyebrow ? <Label>{eyebrow}</Label> : null}
        <h2 className="display mt-4 text-[28px] leading-[1.14] text-paper md:text-[36px]">{title}</h2>
      </div>
      <div className="md:col-span-5 md:pt-9">
        {text ? <p className="text-[14px] leading-[1.65] text-stone">{text}</p> : null}
        {aside ? <div className="mt-5">{aside}</div> : null}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Statistic                                                            */
/* ------------------------------------------------------------------ */
export function Stat({
  figure,
  label,
  detail,
  demo,
  source,
  url,
  size = "md",
}: {
  figure: string;
  label: string;
  detail?: string;
  demo?: boolean;
  source?: string;
  url?: string;
  size?: "sm" | "md" | "lg";
}) {
  return (
    <div>
      <div
        className={cx(
          "display tabular-nums leading-none text-paper",
          size === "lg" ? "text-[44px] md:text-[56px]" : size === "md" ? "text-[34px] md:text-[40px]" : "text-[26px]",
        )}
      >
        {figure}
      </div>
      <div className="mt-3 flex items-center gap-2">
        <Label>{label}</Label>
        {demo ? <DemoTag /> : null}
      </div>
      {detail ? <p className="mt-3 max-w-[34ch] text-[13px] leading-[1.6] text-muted">{detail}</p> : null}
      {source ? (
        url ? (
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="mt-2 inline-block py-[6px] font-mono text-[10px] uppercase tracking-[0.14em] text-muted underline decoration-white/20 underline-offset-4 hover:text-copper"
          >
            {source}
          </a>
        ) : (
          <p className="mt-3 font-mono text-[10px] uppercase tracking-[0.14em] text-muted">{source}</p>
        )
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Buttons                                                              */
/* ------------------------------------------------------------------ */
export function ActionLink({
  href,
  children,
  variant = "primary",
  external,
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "ghost" | "quiet";
  external?: boolean;
}) {
  const cls =
    variant === "primary" ? "btn-primary" : variant === "ghost" ? "btn-ghost" : "btn-quiet -mx-2";
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className={cls}>
        {children}
      </a>
    );
  }
  return (
    <Link href={href} className={cls}>
      {children}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* Key/value row                                                        */
/* ------------------------------------------------------------------ */
export function DataRow({
  k,
  v,
  children,
}: {
  k: string;
  v?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="flex items-start justify-between gap-6 border-b border-white/[0.06] py-[10px] last:border-b-0">
      <Label className="pt-[3px]">{k}</Label>
      <div className="text-right text-[13px] text-paper">{v ?? children}</div>
    </div>
  );
}
