"use client";

import { useEffect } from "react";
import { Label } from "@/lib/components/ui/primitives";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="shell flex min-h-[58vh] flex-col justify-center py-24">
      <Label>Error · Index unavailable</Label>
      <h1 className="display mt-6 max-w-[22ch] text-[34px] leading-[1.1] text-paper md:text-[48px]">
        The record could not be retrieved.
      </h1>
      <p className="mt-7 max-w-[48ch] text-[15px] leading-[1.7] text-stone">
        Something failed while loading this view. Retrying re-runs the request; if it fails again,
        the registry is unreachable rather than the data being missing.
      </p>
      <div className="mt-10">
        <button onClick={reset} className="btn-primary">
          Retry
        </button>
      </div>
      {error.digest ? (
        <p className="mt-8 font-mono text-[10px] uppercase tracking-[0.12em] text-muted">
          Reference {error.digest}
        </p>
      ) : null}
    </div>
  );
}
