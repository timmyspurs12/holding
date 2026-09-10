import type { NetworkInfo } from "@/lib/api/client";
import { MetaTag } from "./primitives";
import { DemoTag } from "./primitives";

/**
 * Every figure on the site says where it came from. A live network tag shows the
 * mode and the registry address; anything else keeps the DEMO tag.
 */
export function SourceTag({
  live,
  network,
  className,
}: {
  live: boolean;
  network: NetworkInfo | null;
  className?: string;
}) {
  if (!live || !network || network.simulated) return <DemoTag className={className} />;
  return (
    <MetaTag tone={network.mode === "MAINNET" ? "green" : "copper"} className={className}>
      {network.mode}
    </MetaTag>
  );
}
