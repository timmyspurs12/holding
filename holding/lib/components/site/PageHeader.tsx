import type { ReactNode } from "react";
import { Label } from "../ui/primitives";

export function PageHeader({
  eyebrow,
  title,
  lede,
  meta,
  children,
}: {
  eyebrow: string;
  title: ReactNode;
  lede?: ReactNode;
  meta?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <header className="border-b border-white/[0.08]">
      <div className="shell py-14 md:py-20">
        <div className="grid gap-8 md:grid-cols-12">
          <div className="md:col-span-8">
            <Label>{eyebrow}</Label>
            <h1 className="display mt-5 text-[38px] leading-[1.02] text-paper md:text-[58px]">
              {title}
            </h1>
            {lede ? (
              <p className="mt-7 max-w-[54ch] text-[15px] leading-[1.65] text-stone md:text-[17px]">
                {lede}
              </p>
            ) : null}
          </div>
          {meta ? <div className="md:col-span-4 md:justify-self-end md:text-right">{meta}</div> : null}
        </div>
        {children ? <div className="mt-12">{children}</div> : null}
      </div>
    </header>
  );
}
