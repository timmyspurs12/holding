import Link from "next/link";
import { Label } from "@/lib/components/ui/primitives";

export default function NotFound() {
  return (
    <div className="shell flex min-h-[62vh] flex-col justify-center py-24">
      <Label>404 · Not in the record</Label>
      <h1 className="display mt-6 max-w-[20ch] text-[38px] leading-[1.08] text-paper md:text-[56px]">
        No holding answers to that name.
      </h1>
      <p className="mt-7 max-w-[46ch] text-[15px] leading-[1.7] text-stone">
        The reference may have been mistyped, or the holding has not been indexed. The index is the
        fastest way to find what you are looking for.
      </p>
      <div className="mt-10 flex flex-wrap gap-3">
        <Link href="/reporter" className="btn-primary">
          Open the Reporter
        </Link>
        <Link href="/holdings" className="btn-ghost">
          Holdings index
        </Link>
      </div>
    </div>
  );
}
