# HOLDING — architecture

GenLayer settles disputes with LLM validators and then forgets them. HOLDING is the
layer that keeps the memory: a **HoldingRegistry Intelligent Contract** that turns
finalized adjudications into citable holdings, retrieves them with on-chain vector
search, and scores their authority from observable facts alone.

This document records what is built, what it rests on, and — explicitly — what is
simulated.

---

## 1. The product loop

```
CASE → ADJUDICATION → FINALITY → HOLDING → INDEX
     → PRECEDENT RETRIEVAL → NEW ADJUDICATION → FOLLOW / DISTINGUISH → NEW HOLDING
```

| Step | Where it happens | What it produces |
|---|---|---|
| CASE | `contracts/Adjudicator.py` | `submit_case(case_id, facts)` → status `PROPOSED` |
| ADJUDICATION | `Adjudicator.adjudicate()` | retrieval → prompt → `run_nondet_unsafe` → validator agreement → status `CONSENSUS` |
| FINALITY | GenLayer consensus, then `HoldingRegistry.attest_finality()` | status 7 + `FINISHED_WITH_RETURN` → `FINAL` |
| HOLDING | `registry.emit(on="finalized").create_holding(...)` | `HLD-000001`, status `PENDING` |
| INDEX | `HoldingRegistry.create_holding()` | VecDB insert + `case_index` + authority components |
| RETRIEVAL | `HoldingRegistry.get_precedent()` | k nearest **final** holdings with similarity + authority |
| FOLLOW / DISTINGUISH | `Adjudicator` + `cite_by_case` | a `FOLLOWS` or `DISTINGUISHES` edge, materialised at finality |

A holding is **never** created because a leader proposed a verdict. The adjudicator
writes through `emit(on="finalized")`, so the holding only exists once the
transaction has settled and an attestor has confirmed status 7 with a successful
execution result.

---

## 2. Layout

```
contracts/
  HoldingRegistry.template.py   # source of truth for editing
  HoldingRegistry.py            # GENERATED — do not edit (scripts/render_contract.py)
  HoldingAdjudicator.py         # the reference consumer contract
shared/holding_core/            # deterministic core, mirrored into the contract
  _mirrored.py                  # the single block reproduced verbatim on-chain
  schema.py  authority.py  validation.py  precedent.py
services/
  lib/genlayer/                 # the adapter layer (client / contracts / types)
    client.py  config.py  base.py  demo.py  live.py  registry.py  types.py
    stub_runtime.py             # development runtime double (used by DEMO + tests)
  api/                          # Reporter API (FastAPI)
  indexer/                      # read-side mirror (never the source of truth)
frontend (Next.js app/)         # the Reporter UI
tests/                          # 124 tests
scripts/
  render_contract.py            # template + mirrored block → generated contract
  demo_loop.py                  # runs the six-step loop live
```

> The brief asked for `/lib/genlayer`. Because the Next.js app already owns the
> repository's root `lib/` (`@/lib/components`, `@/lib/data`), the Python adapter
> lives at `services/lib/genlayer`. Same role, no collision with frontend imports.

---

## 3. The contract

### 3.1 Record

| Field | Notes |
|---|---|
| `holding_id` | `HLD-000001`, zero-padded so lexical order equals numeric order |
| `case_id` | the originating case |
| `domain`, `contract_class` | retrieval filters |
| `issue`, `facts_digest`, `ratio` | short text; the digest, not the evidence |
| `verdict` | `APPROVED` / `REJECTED` / `PARTIAL` |
| `reason_codes`, `evidence_hashes` | lists; hashes only, no documents on-chain |
| `panel_size` | validators in the deciding round |
| `appeal_status`, `appeal_outcome`, `finality_timestamp`, `tx_status_code`, `execution_result` | finality evidence |
| `authority_bp`, `citation_count`, `followed_count`, `distinguishment_count` | integer state — no floats |
| `parent_holdings`, `distinguishment` | lineage and the recorded material difference |
| `contract_address`, `source_tx` | provenance |

No large text is stored on-chain: evidence is referenced by hash, the embedding is
a vector in the native VecDB, and the reasoning is never persisted.

### 3.2 Lifecycle and status

```
PROPOSED → VALIDATING → CONSENSUS → (appeal window) → FINALIZED → HOLDING CREATED
```

Holding statuses:

| Status | Meaning | Returned as precedent? |
|---|---|---|
| `UNVERIFIED` | submitted by an operator or unregistered source | no |
| `PENDING` | created by a registered source contract, not yet attested | no |
| `FINAL` | status 7 **and** `FINISHED_WITH_RETURN` | **yes** |
| `REJECTED` | failed execution, overturned on appeal, or withdrawn | no |

That boundary is the corpus-poisoning defence: only finalized adjudications from
registered source contracts can become precedent, and authority starts low.

### 3.3 Determinism — the mirrored block

GenVM has no imports between contract files and no module-level state to share, so
the deterministic core is **one block of code** (`shared/holding_core/_mirrored.py`)
that is reproduced verbatim inside the generated contract:

```
shared/holding_core/_mirrored.py ──► contracts/HoldingRegistry.template.py ──► contracts/HoldingRegistry.py
                └──────────────────────► contracts/Adjudicator.py (prompt + constants)
```

* `scripts/render_contract.py` renders the template; `--check` verifies it is current.
* `tests/test_mirror_sync.py` fails if the generated file drifts, if the mirrored
  core drifts, if the mirrored prompt constants drift, if the contracts stop
  parsing, or if a float reaches state.

Everything a validator recomputes — normalisation, embedding text, authority
components, similarity conversion — lives in that block. Similarity is stored and
passed as a **decimal string** (`"0.8734"`) and converted with `similarity_to_bp`,
so no float ever reaches contract state.

### 3.4 Retrieval — native VecDB, not an external store

```python
self.vector_store: VecDB[np.float32, typing.Literal[384], HoldingVector]
...
hits = self.vector_store.knn(self._embed(text), k)   # native GenVM vector store
```

* Model pinned as a contract constant: `all-MiniLM-L6-v2`, 384 dimensions.
* `get_precedent(case_digest, domain, k)` normalises, embeds, queries the VecDB,
  filters to `FINAL` holdings, and returns similarity (basis points) plus authority.
* **Cold start returns `[]`** — it never raises and never fabricates a match.
* Ranking: same domain first, then similarity desc, authority desc, `holding_id`
  asc (stable tie-break). The frontend never decides what matters.

No Pinecone, Supabase, Qdrant or pgvector is used for precedent. The optional
SQLite indexer is a Reporter convenience layer only (§6).

### 3.5 Authority — computed, never declared

```
authority_bp = Σ (component_bp × weight_bp) // 10_000
```

| Component | Weight | Derived from |
|---|---|---|
| finality | 3000 | `FINAL` 10_000 · `PENDING` 2_500 · `UNVERIFIED` 1_000 · `REJECTED` 0 |
| appeal | 2500 | `UPHELD` 10_000 · `NONE` 7_000 · `PENDING` 5_000 · `OVERTURNED` 1_000 |
| panel | 1500 | `panel_size × 10_000 // 11`, capped |
| citations | 2000 | `count × 1_000`, saturated at 10 |
| consistency | 1000 | `followed / (followed + distinguished)`, 5_000 neutral when unused |

Every holding stores its components and exposes them, so "why is this
authoritative?" is answerable from the record: the API returns the components,
their weights, their contributions and a sentence naming the strongest and weakest
signal. There is no model-generated score.

### 3.6 Citation graph

`CITES`, `FOLLOWS`, `DISTINGUISHES` (the schema leaves room for `OVERRULE` and
`DERIVE_FROM`). Edges are:

* validated (known holdings, no self-reference, supported relationship),
* idempotent (a duplicate is a no-op, not an error),
* **only writable from a `FINAL` source holding.**

The adjudicator must declare the relationship in the same transaction that emits
the holding, before the holding id exists. `cite_by_case()` parks that intent in
`pending_links`, and `attest_finality()` materialises the edge when the holding
becomes final. A proposal alone can never write to the precedent graph.

### 3.7 Distinguishment

The defining feature. The prompt instructs *follow unless there is a material
difference*, and the contract rejects distinguishments that do not name one:

* shorter than 40 characters → `UserError`
* matching a generic phrase (`"the circumstances differ."`, `"this case is
  different."`, `"not applicable here."`, …) → `UserError`

The accepted form names the difference against the cited holding. The prompt shows
both a rejected and an accepted example.

### 3.8 The adjudicator is a consumer, not a governor

`contracts/Adjudicator.py` is the **reference consumer**: it shows how any
adjudication contract uses HOLDING. It retrieves precedent, builds the prompt,
runs the model, validates the output, and writes the holding. It never claims the
protocol binds panels — GenLayer provides consensus, HOLDING provides precedent,
and the contract merely consumes it.

Validators follow the **Equivalence Principle**: they re-run the prompt
independently and compare only stable *decision fields*
`(verdict, FOLLOW|DISTINGUISH, sorted precedent_used, has_reason)` — never the
analysis text.

---

## 4. The adapter layer (`services/lib/genlayer`)

| Mode | `GENLAYER_NETWORK` | Behaviour |
|---|---|---|
| DEMO | `demo`, `localnet` | Executes the **real contract files** in a local development runtime (`stub_runtime.py`). No chain, no committee, no appeal window, no LLM — a scripted responder answers the prompt. Every artefact carries `simulated: true` and a `DEMO` provenance mode. |
| TESTNET | `bradbury`, `asimov`, `studionet` | genlayer-py against the documented RPC. Requires `HOLDING_REGISTRY_ADDRESS`; refuses to start without it. |
| MAINNET | `mainnet` | same, with simulation endpoints hard-disabled. |

`DemoChain` models the real lifecycle rather than shortcutting it:

* `write()` returns an **ACCEPTED** receipt (status 5) and queues the emitted
  messages;
* `settle(tx)` delivers the queued `on="finalized"` messages, then attests the new
  holdings with status 7 + `FINISHED_WITH_RETURN`, which is what materialises the
  citation edges.

Simulated transaction references are valid hex with a visible marker (`0xdef1…`).

**No fake blockchain is presented as live.** If the SDK, the RPC or the address is
missing, the adapter raises `LiveUnavailable` and the API reports the mode; it never
silently serves demo data in place of a live network.

### Live-mode notes (fees, consensus v0.6)

* Client: `create_client(chain=…)`, then `read_contract`, `write_contract`,
  `wait_for_transaction_receipt`, `appeal_transaction`.
* Consensus v0.6 requires fees on every deploy/write. That API exists only in the
  0.19 release candidate, so the adapter is pinned to 0.18.0 and sends no fee
  fields — see Limitations.
* Finality is status **7 (Finalized)** *and* execution result
  `FINISHED_WITH_RETURN`; status alone is not success.
* Reading a contract's view from another contract: `other.view().method()`;
  writing after settlement: `other.emit(on="finalized").method(...)`.

---

## 5. Reporter API (`services/api`)

Clean, typed JSON. No raw receipts, web3 objects or SDK models leave the adapter.

| Route | Purpose |
|---|---|
| `GET /health` | service, network mode, registry reachability |
| `GET /stats` | totals, status split, citation edges, authority bands |
| `GET /domains` | per-domain volume and follow/distinguish counts |
| `GET /holdings` | list + metadata filters (domain, class, status, verdict, appeal, authority, since/until, sort, paging) |
| `GET /holdings/search` | semantic retrieval (`q`) plus the same filters |
| `GET /holdings/{id}` | one holding with authority breakdown and provenance |
| `GET /holdings/{id}/citations?relationship=` | citation graph edges with direction |
| `GET /holdings/{id}/precedent?k=` | what a panel would be shown for this holding |
| `GET /holdings/{id}/distinguishments` | holdings that departed from it, with reasons |
| `GET /cases`, `GET /cases/{id}` | adjudicated cases and the holding each produced |
| `POST /admin/holdings` | create an unverified record (schema-validated) |
| `POST /admin/holdings/{id}/finality` | attest finality |
| `POST /admin/holdings/{id}/reject` | mark ineligible |
| `POST /admin/citations` | record a relationship |
| `POST /demo/cases`, `POST /demo/seed` | labelled simulation (never on mainnet) |
| `GET /auth/config` | what a wallet has to sign, and whether sign-in is on |
| `GET /auth/nonce?address=` | issue a single-use sign-in nonce + message |
| `POST /auth/verify` | verify a `personal_sign` signature, open a session |
| `GET /auth/session` | is this session still valid? |
| `GET /operator/source-contracts` | source-contract proposals (public) |
| `POST /operator/source-contracts` | propose a source (needs a wallet session) |
| `GET /operator/me` | the signed-in address and its proposals |
| `POST /admin/source-contracts/{id}/approve` | approve → `register_source()` on-chain |
| `POST /admin/source-contracts/{id}/reject` | decline a proposal |

Every list response carries the `network` block it came from, so a client cannot
mistake a simulated record for a live one.

Search is not keyword-only: with a query it uses the contract's embedding + VecDB
and over-fetches before applying metadata filters; without one it is a filtered
catalogue. An unqualified search only returns `FINAL` holdings.

### Security

* **Admin authorization** — `X-Admin-Token`, compared with `hmac.compare_digest`.
  With no token configured every write returns 503 (fail closed).
* **Replay protection** — every write requires an `Idempotency-Key`; a replay
  returns the original result instead of writing twice. Keys are hashed at rest.
* **Schema validation** — payloads are validated against the same core the contract
  enforces (`shared/holding_core/validation.py`) before any write is submitted.
* **Relationship validation** — known ids, supported relationship, no self-citation.
* **Rate limiting** — fixed-window per client, `429 + Retry-After`.
* **Secrets** — `.env` only, never logged, never serialised; `GenLayerConfig`
  marks the key and token `repr=False`.
* **Live writes** — only through the adapter; the API never signs anything itself.

### Wallet sign-in and operator sessions

A registered source contract is the only thing allowed to emit holdings, so who
gets to add one matters. HOLDING splits that in two:

1. **A wallet proves control of an address.** `GET /auth/nonce` issues a
   single-use nonce; the wallet signs it with `personal_sign` (off-chain, free,
   cannot move funds); `POST /auth/verify` recovers the signer and returns an
   HMAC-signed session token. The message is rebuilt *server-side* from the
   stored nonce record, so the client's copy of the text is never trusted, and
   it is bound to one address, one origin and one chain id.
2. **That address proposes, an operator approves.** `POST /operator/source-contracts`
   queues a `PENDING` proposal and writes nothing to the registry. Approval —
   `POST /admin/source-contracts/{id}/approve`, gated by `HOLDING_ADMIN_TOKEN` —
   is what calls `register_source()` on the contract.

That asymmetry is the corpus-poisoning defence. Signing a message with a wallet
is cheap; being able to do it must not let anyone add an emitter to the
canonical registry.

Injected wallets only (EIP-1193: MetaMask, Rabby, Brave, Frame). WalletConnect
and mobile wallets do not inject, so they are not supported — the UI says so
instead of failing silently. Reading anything on HOLDING never needs a wallet:
it is a public record, and the sign-in is not on the path to any read.

| | propose | approve | attest / cite / reject |
|---|---|---|---|
| anyone | — | — | — |
| wallet session | ✓ | — | — |
| `HOLDING_ADMIN_TOKEN` | — | ✓ | ✓ |
| contract owner (on-chain) | — | the account that signs `register_source` | the account that signs the write |

`HOLDING_OPERATOR_ADDRESSES` is a Reporter-side allowlist: it marks which
signed-in wallets count as operators. Empty means *nobody*, not everybody.

---

## 6. Indexer (`services/indexer`)

Polls the registry, mirrors holdings, cases, citations and provenance into SQLite,
and answers "where did this holding come from?" quickly.

In DEMO mode each process holds its own in-memory registry, so an indexer started as a
separate process mirrors an empty chain. Point it at a live network (the normal case),
or run it in the same process as the Reporter, to see it populate.

It is a **read-side convenience layer**:

* it never writes to the contract;
* it never decides status — every row is copied from the contract;
* it stores the holding hash derived from each record, and refreshes on every pass,
  so if the contract and the index disagree the contract wins.

```
python -m services.indexer.indexer --once
python -m services.indexer.indexer --interval 30
```

---

## 7. Frontend

Next.js App Router, server components. Data comes from `getCorpus()`
(`lib/data/live.ts`), which fetches the Reporter (`lib/api/client.ts`) and maps its
JSON into the UI shape.

* `HOLDING_API_URL` unset → the bundled demo corpus, every figure tagged **DEMO**.
* API reachable but simulated (`mode: DEMO`) → contract records are shown alongside
  the demo corpus, still tagged **DEMO**.
* API live (`TESTNET` / `MAINNET`) → only contract records, tagged with the network
  mode and the registry address.

The UI never ranks precedent itself; it renders what the contract returned.

---

## 8. Tests

```
pytest tests/ -q     # 124 tests
```

| File | Covers |
|---|---|
| `test_mirror_sync.py` | generated contract is current; mirrored core/prompt in sync; no floats in state |
| `test_contract_registry.py` | creation, authorization, dedupe, malformed payloads, finality, cold start, retrieval, authority, citations, admin, views |
| `test_contract_adjudicator.py` | the loop: cold start, follow, distinguish, generic-distinguishment rejection, `on="finalized"` emission, prompt contents |
| `test_shared_core.py` | authority determinism/bounds/components, ranking, validation, schema, provenance |
| `test_api.py` | cold start, empty registry, filters, semantic search, provenance, authority, citations, admin auth, replay protection, malformed writes, simulation guard rails |
| `test_indexer.py` | mirroring, provenance lookup, refresh when the contract changes |

`tests/stubs` is gone: the runtime double now lives with the adapter
(`services/lib/genlayer/stub_runtime.py`) so tests, DEMO mode and the demo script
share one implementation. Its header documents exactly what it does and does not
prove — it exercises contract logic, not consensus.

---

## 9. Running it

```bash
pip install -r requirements.txt
cp .env.example .env

# the loop, against the contract
python scripts/demo_loop.py

# the Reporter API (DEMO mode, seeds the canonical three cases)
GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=dev-admin-token \
  python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000

# the site, consuming the API
HOLDING_API_URL=http://127.0.0.1:8000 npm run dev

# the indexer
python -m services.indexer.indexer --once
```

`scripts/demo_loop.py` prints, per case: the precedent retrieved, the verdict, the
disposition (`FOLLOWS` / `DISTINGUISHES` / first impression), the finality receipt
(status 7 + execution result), and the holding created — ending with
`#001 → FOLLOWS → #002 → DISTINGUISHES #001 → #003`.

---

## 10. Assumptions, and what is not claimed

**Assumptions** (from the current GenLayer documentation, September 2026):

1. Consensus v0.6 semantics: 14 transaction statuses, 7 = Finalized; finality
   requires status 7 **and** a `FINISHED_WITH_RETURN` execution result.
2. VecDB is available inside GenVM with `insert()` / `knn()` and a pinned
   `SentenceTransformer` model.
3. `@gl.public.view` / `@gl.public.write`, `gl.nondet.exec_prompt`,
   `gl.vm.run_nondet_unsafe`, `gl.get_contract_at`, `.view()`, and
   `.emit(on=…)` behave as documented.
4. `genlayer-py` 0.18.0 is the usable stable client.

**Limitations, stated plainly:**

* **DEMO mode is simulated.** It runs the real contract code, but there is no
  consensus, no validator committee, no appeal window, no chain, and no LLM call —
  a deterministic scripted responder answers the prompt. Nothing produced in DEMO
  mode is a historical GenLayer case.
* **Nothing is deployed.** The contract has not been deployed to Bradbury or
  mainnet; `HOLDING_REGISTRY_ADDRESS` is unset in `.env.example`. The live adapter
  is written against the documented 0.18.0 API and is not exercised against a node.
* **Fees are not sent.** Consensus v0.6 requires a `FeesDistribution` on every
  deploy and write; that API exists only in genlayer-py 0.19 RC, so the adapter is
  pinned to 0.18.0 and omits it. Deploying on a v0.6 network requires moving to
  0.19 and threading fee fields through `LiveChain.write` — a contained change,
  isolated to one file.
* **The content hash is computed off-chain.** `holding_hash` is derived by the
  Reporter/indexer from the canonical fields rather than inside GenVM, to avoid
  depending on a hashing surface GenVM may not expose. It is an integrity check
  for the Reporter, not a consensus-verified value.
* **Case simulation on a testnet is opt-in** (`HOLDING_ALLOW_SIMULATION=true`) and
  impossible on mainnet.
* **Similarity values in DEMO mode are illustrative.** The runtime double replaces
  MiniLM with a deterministic hashing embedder; ranking is meaningful, absolute
  cosine values are not.

## 11. Sources

* GenLayer networks & Bradbury endpoints — https://docs.genlayer.com/developers/networks
* Transaction statuses — https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/transactions/transaction-statuses
* Finality — https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/optimistic-democracy/finality
* Appeal process — https://docs.genlayer.com/understand-genlayer-protocol/core-concepts/optimistic-democracy/appeal-process
* Consensus v0.6 migration — https://docs.genlayer.com/developers/consensus-v06-migration
* Equivalence principle — https://docs.genlayer.com/developers/intelligent-contracts/equivalence-principle
* Calling LLMs — https://docs.genlayer.com/developers/intelligent-contracts/features/calling-llms
* Vector storage — https://docs.genlayer.com/developers/intelligent-contracts/features/vector-storage
* genlayer-py — https://docs.genlayer.com/developers/genlayer-py
