"use client";

/**
 * Source-contract registration on the /developers page.
 *
 * A connected wallet proposes; an operator approves. The UI says so in those
 * words, because the difference is the one that matters: proposing writes
 * nothing, approving is what registers the contract on-chain.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import { cx } from "@/lib/components/ui/primitives";
import { walletApi, type SourceProposal } from "@/lib/wallet/api";
import { WalletButton } from "@/lib/wallet/WalletButton";
import { useWallet } from "@/lib/wallet/WalletProvider";

const ADDRESS = /^0x[0-9a-fA-F]{40}$/;
const TX = /^0x[0-9a-fA-F]{64}$/;
const SLUG = /^[a-z0-9][a-z0-9-]{1,47}$/;

const EMPTY = {
  contract_address: "",
  domain: "digital-commerce",
  contract_class: "",
  label: "",
  deploy_tx: "",
  notes: "",
};

type Draft = typeof EMPTY;

const STATUS_TONE: Record<string, string> = {
  PENDING: "text-copper border-copper/35 bg-copper/[0.06]",
  APPROVED: "text-verdict border-verdict/30 bg-verdict/[0.06]",
  REJECTED: "text-dissent border-dissent/30 bg-dissent/[0.06]",
};

function newIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `k-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export function RegisterSource() {
  const wallet = useWallet();
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ proposal_id: string; status: string; next: string } | null>(null);
  const [proposals, setProposals] = useState<SourceProposal[] | null>(null);
  const [listError, setListError] = useState<string | null>(null);
  const keyRef = useRef<string>(newIdempotencyKey());

  const load = useCallback(async () => {
    const response = await walletApi.proposals();
    if (response.ok) {
      setProposals(response.data.items);
      setListError(null);
    } else {
      setProposals([]);
      setListError(response.error);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const set = (field: keyof Draft) => (event: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
    setDraft((current) => ({ ...current, [field]: event.target.value }));
  };

  const localErrors = (): string[] => {
    const errors: string[] = [];
    if (!ADDRESS.test(draft.contract_address.trim())) {
      errors.push("Contract address must be a 0x-prefixed 20-byte address.");
    }
    if (!SLUG.test(draft.domain.trim().toLowerCase())) {
      errors.push("Domain must be 2–48 characters: lowercase letters, digits and hyphens.");
    }
    if (!SLUG.test(draft.contract_class.trim().toLowerCase())) {
      errors.push("Contract class must be 2–48 characters: lowercase letters, digits and hyphens.");
    }
    if (draft.deploy_tx.trim() && !TX.test(draft.deploy_tx.trim())) {
      errors.push("Deploy transaction must be a 0x-prefixed 32-byte hash, or empty.");
    }
    return errors;
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    setResult(null);
    const errors = localErrors();
    if (errors.length) {
      setError(errors.join(" "));
      return;
    }
    if (!wallet.token) {
      setError("Sign in with your wallet first.");
      return;
    }
    setSubmitting(true);
    const response = await walletApi.propose(
      wallet.token,
      {
        contract_address: draft.contract_address.trim(),
        domain: draft.domain.trim().toLowerCase(),
        contract_class: draft.contract_class.trim().toLowerCase(),
        label: draft.label.trim(),
        deploy_tx: draft.deploy_tx.trim(),
        notes: draft.notes.trim(),
      },
      keyRef.current,
    );
    setSubmitting(false);
    if (!response.ok) {
      setError(response.error);
      return;
    }
    keyRef.current = newIdempotencyKey();
    setResult({
      proposal_id: response.data.proposal_id,
      status: response.data.status,
      next: response.data.next,
    });
    setDraft((current) => ({ ...current, contract_address: "", deploy_tx: "" }));
    void load();
  };

  return (
    <section id="register" className="scroll-mt-20 border-t border-white/[0.08]">
      <div className="shell py-16 md:py-20">
        <div className="grid gap-8 md:grid-cols-12">
          <div className="md:col-span-5">
            <span className="label">Register a source contract</span>
            <h2 className="display mt-4 text-[28px] leading-[1.16] text-paper md:text-[34px]">
              Two signatures, in that order.
            </h2>
          </div>
          <div className="md:col-span-6 md:col-start-7 md:pt-3">
            <p className="max-w-[46ch] text-[14px] leading-[1.7] text-stone">
              Your wallet proposes the contract. An operator checks the deployment and
              approves it — the approval is the call that registers you on-chain and lets
              your decisions become holdings. Proposing costs nothing and writes nothing.
            </p>
            <ol className="mt-6 space-y-2">
              {[
                "Connect a browser wallet and sign the nonce the Reporter issues.",
                "Submit the contract address, its domain and its class.",
                "Wait for operator approval; the proposal id is your reference.",
              ].map((step, index) => (
                <li key={step} className="flex gap-3 text-[13px] leading-[1.6] text-stone">
                  <span className="mt-[3px] font-mono text-[10px] tracking-[0.14em] text-copper">
                    {String(index + 1).padStart(2, "0")}
                  </span>
                  {step}
                </li>
              ))}
            </ol>
          </div>
        </div>

        <div className="mt-10 grid gap-8 md:grid-cols-12">
          {/* ---------------- form ---------------- */}
          <div className="md:col-span-7">
            {wallet.status !== "connected" ? (
              <div className="panel p-6">
                <p className="text-[14px] leading-[1.7] text-stone">
                  {wallet.status === "unsupported"
                    ? "No browser wallet was detected. HOLDING uses injected wallets — MetaMask, Rabby or Brave. Mobile WalletConnect wallets do not inject into a page."
                    : "Connect a wallet to propose a source contract. Signing is free and off-chain: it proves you control the address, and it is not a transaction."}
                </p>
                <div className="mt-5">
                  <WalletButton />
                </div>
                {wallet.error ? (
                  <p className="mt-4 font-mono text-[11px] leading-[1.6] text-dissent">{wallet.error}</p>
                ) : null}
              </div>
            ) : (
              <form onSubmit={submit} className="panel p-6">
                <div className="flex items-center justify-between border-b border-white/[0.07] pb-4">
                  <span className="label">Proposal</span>
                  <span className="font-mono text-[11px] text-stone">{wallet.displayAddress}</span>
                </div>

                <div className="mt-5 grid gap-5 sm:grid-cols-2">
                  <Field
                    label="Contract address"
                    hint="0x… the address GenLayer deployed"
                    value={draft.contract_address}
                    onChange={set("contract_address")}
                    placeholder="0x…"
                    className="sm:col-span-2"
                    mono
                  />
                  <Field label="Domain" hint="escrow, moderation, prediction-markets…" value={draft.domain} onChange={set("domain")} mono />
                  <Field label="Contract class" hint="RefundArbiter" value={draft.contract_class} onChange={set("contract_class")} mono />
                  <Field label="Label" hint="optional" value={draft.label} onChange={set("label")} />
                  <Field label="Deploy transaction" hint="optional" value={draft.deploy_tx} onChange={set("deploy_tx")} mono />
                  <div className="sm:col-span-2">
                    <label className="label">Notes for the operator</label>
                    <textarea
                      value={draft.notes}
                      onChange={set("notes")}
                      rows={3}
                      maxLength={500}
                      className="field mt-2 resize-none"
                      placeholder="What does this contract decide?"
                    />
                  </div>
                </div>

                {error ? (
                  <p className="mt-5 border border-dissent/25 bg-dissent/[0.06] px-4 py-3 font-mono text-[11px] leading-[1.65] text-dissent">
                    {error}
                  </p>
                ) : null}

                {result ? (
                  <div className="mt-5 border border-verdict/25 bg-verdict/[0.05] px-4 py-3">
                    <p className="font-mono text-[11px] uppercase tracking-[0.14em] text-verdict">
                      {result.status} · {result.proposal_id}
                    </p>
                    <p className="mt-2 text-[13px] leading-[1.65] text-stone">{result.next}</p>
                  </div>
                ) : null}

                <div className="mt-6 flex items-center gap-4">
                  <button type="submit" disabled={submitting} className="btn-primary disabled:opacity-60">
                    {submitting ? "Submitting…" : "Submit proposal"}
                  </button>
                  <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-muted">
                    Free · off-chain · nothing is registered yet
                  </span>
                </div>
              </form>
            )}
          </div>

          {/* ---------------- queue ---------------- */}
          <div className="md:col-span-5">
            <div className="flex items-baseline justify-between">
              <span className="label">Proposals</span>
              {proposals ? (
                <span className="font-mono text-[11px] text-muted">{proposals.length}</span>
              ) : null}
            </div>
            <div className="mt-3 border border-white/[0.08] bg-ink">
              {listError ? (
                <p className="px-5 py-6 font-mono text-[11px] leading-[1.7] text-dissent">{listError}</p>
              ) : proposals === null ? (
                <p className="px-5 py-6 font-mono text-[11px] text-muted">Loading…</p>
              ) : proposals.length === 0 ? (
                <p className="px-5 py-6 text-[13px] leading-[1.65] text-stone">
                  No proposals yet. The first one is the cold start: nothing is
                  registered until an operator approves it.
                </p>
              ) : (
                <div className="divide-y divide-white/[0.05]">
                  {proposals.slice(0, 8).map((proposal) => (
                    <div key={proposal.proposal_id} className="px-5 py-4">
                      <div className="flex items-center justify-between gap-3">
                        <code className="font-mono text-[12px] text-paper">
                          {proposal.short_address ?? proposal.contract_address}
                        </code>
                        <span
                          className={cx(
                            "rounded-[4px] border px-[6px] py-[1px] font-mono text-[9px] uppercase tracking-[0.14em]",
                            STATUS_TONE[proposal.status] ?? "border-white/12 text-stone",
                          )}
                        >
                          {proposal.status}
                        </span>
                      </div>
                      <p className="mt-[6px] font-mono text-[10.5px] uppercase tracking-[0.12em] text-muted">
                        {proposal.domain} · {proposal.contract_class} · {proposal.proposal_id}
                      </p>
                      {proposal.decision_note ? (
                        <p className="mt-2 text-[12.5px] leading-[1.6] text-stone">{proposal.decision_note}</p>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </div>
            <p className="mt-3 font-mono text-[10px] leading-[1.7] text-muted">
              A PENDING proposal is a request. Only APPROVED entries have been
              written to the registry contract.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}

function Field({
  label,
  hint,
  value,
  onChange,
  placeholder,
  className,
  mono,
}: {
  label: string;
  hint?: string;
  value: string;
  onChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  placeholder?: string;
  className?: string;
  mono?: boolean;
}) {
  return (
    <div className={className}>
      <label className="label">{label}</label>
      <input
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={cx("field mt-2", mono && "font-mono text-[12px]")}
      />
      {hint ? (
        <p className="mt-[6px] font-mono text-[10px] uppercase tracking-[0.12em] text-muted">{hint}</p>
      ) : null}
    </div>
  );
}
