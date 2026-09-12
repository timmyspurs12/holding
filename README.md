# HOLDING

**The precedent layer for GenLayer. Every decision becomes precedent.**

GenLayer settles disputes with panels of LLM validators and then forgets them. HOLDING
keeps the memory: a registry Intelligent Contract that turns *finalized* adjudications
into citable holdings, retrieves them with on-chain vector search, and scores their
authority from observable facts alone — so the next panel either follows the record or
states the material difference.

Full design, assumptions and limitations: **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**.

---

## What is built

| Layer | Status | Where |
|---|---|---|
| `HoldingRegistry` Intelligent Contract | built, tested locally | `contracts/HoldingRegistry.py` (generated from `.template.py`) |
| `PrecedentAdjudicator` consumer contract | built, tested locally | `contracts/Adjudicator.py` |
| Deterministic core (authority / retrieval / validation) | built, mirrored into the contract | `shared/holding_core/` |
| GenLayer adapter (DEMO ↔ TESTNET ↔ MAINNET) | built | `services/lib/genlayer/` |
| Reporter API | built, running | `services/api/` |
| Indexer (read-side mirror) | built | `services/indexer/` |
| Frontend | built, consumes the API | `app/`, `lib/` |
| Tests | 127 passing | `tests/` |
| Deployment to Bradbury / mainnet | **not deployed** | see Honest status |

---

## Quickstart

```bash
# 1 · Python (3.11–3.13 recommended; 3.14 works with pydantic >= 2.12)
pip install -r requirements.txt
cp .env.example .env

# 2 · the six-step loop, against the contract
python scripts/demo_loop.py

# 3 · the Reporter API  (DEMO mode; seeds the canonical three cases)
GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=dev-admin-token \
  python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000
#   docs: http://127.0.0.1:8000/docs

# 4 · the site, consuming that API
npm install
HOLDING_API_URL=http://127.0.0.1:8000 npm run dev     # http://localhost:3000

# 5 · tests
python -m pytest tests/ -q                                      # 163 passed

# 6 · indexer
python -m services.indexer.indexer --once
```

Without `HOLDING_API_URL` the site renders its bundled demo corpus and labels every
figure **DEMO**. It never presents simulated records as live ones.

---

## The loop

```
CASE → ADJUDICATION → FINALITY → HOLDING → INDEX
     → PRECEDENT RETRIEVAL → NEW ADJUDICATION → FOLLOW / DISTINGUISH → NEW HOLDING
```

`scripts/demo_loop.py` runs it and prints, per case: the precedent retrieved, the
verdict, the disposition, the finality receipt (status 7 + `FINISHED_WITH_RETURN`),
and the holding created. It ends with:

```
HOLDING 000001  APPROVED  FINAL   FOLLOWS← HLD-000002, DISTINGUISHES← HLD-000003
HOLDING 000002  APPROVED  FINAL   FOLLOWS HLD-000001
HOLDING 000003  REJECTED  FINAL   DISTINGUISHES HLD-000001
```

A holding is **never** created because a leader proposed a verdict — the adjudicator
writes through `emit(on="finalized")`, and an attestor must confirm status 7 with a
successful execution result before the record becomes citable.

---

## Repository

```
contracts/            HoldingRegistry (generated), Adjudicator, schemas, authority, precedent
shared/holding_core/  deterministic core; _mirrored.py is reproduced verbatim on-chain
services/lib/genlayer/  adapter: client (factory), contracts (typed facade), types, demo, live
services/api/         Reporter API (FastAPI) + routers for admin writes and simulation
services/indexer/     SQLite read-side mirror — never the source of truth
app/ lib/             Next.js frontend
tests/                124 tests: contract, adjudicator, core, API, indexer, mirror sync
scripts/              render_contract.py, demo_loop.py
docs/ARCHITECTURE.md  design, security, assumptions, limitations, sources
```

`contracts/HoldingRegistry.py` is generated. Edit `HoldingRegistry.template.py`, then:

```bash
python scripts/render_contract.py          # regenerate
python scripts/render_contract.py --check  # verify (also a test)
```

---

## API surface

```
GET  /health
GET  /stats
GET  /domains
GET  /holdings                       filters: domain, contract_class, status, verdict,
                                     appeal_outcome, min/max_authority, since, until, sort
GET  /holdings/search                semantic (q) + the same filters
GET  /holdings/{id}                  authority breakdown + provenance
GET  /holdings/{id}/citations
GET  /holdings/{id}/precedent        what a panel would be shown
GET  /holdings/{id}/distinguishments
GET  /cases · GET /cases/{id}
POST /admin/holdings · /admin/holdings/{id}/finality · /admin/holdings/{id}/reject · /admin/citations
POST /admin/source-contracts/{id}/approve · /reject
POST /demo/cases · /demo/seed        labelled simulation; disabled on mainnet

GET  /auth/config                    what a wallet signs, is sign-in on
GET  /auth/nonce?address=            single-use sign-in nonce
POST /auth/verify                    signature -> session token
GET  /operator/source-contracts      source-contract proposals (public)
POST /operator/source-contracts      propose one (X-Session-Token)
```

Writes need `X-Admin-Token` and an `Idempotency-Key`. With no admin token configured
every write returns `503` — the API fails closed.

### Connect a wallet

Reading HOLDING needs nothing: it is a public record. Connecting a wallet is the
way to *register a source contract* — the thing that lets your own Intelligent
Contract emit holdings.

1. Click **Connect wallet** and approve the request in your wallet.
2. Sign the nonce the Reporter issues. It is a `personal_sign` message: free,
   off-chain, and it cannot move funds.
3. Fill in the contract address, its domain and its class on `/developers`.

That queues a `PENDING` proposal and writes nothing. An operator checks the
deployment and approves it, and only the approval calls `register_source()` on
the registry contract — signing a message with a wallet must not by itself let
anyone add an emitter to the canonical corpus.

Injected wallets only (MetaMask, Rabby, Brave, Frame). WalletConnect and mobile
wallets do not inject into a page, so they are not supported yet.

The browser calls `/api/reporter/*` on its own origin and Next proxies it to the
API (`next.config.mjs`), so there is no CORS to configure and no API address in
the page.

---

## Honest status

**Built and verified locally**

* The contract logic — creation, dedupe, malformed-payload rejection, finality
  gating, VecDB retrieval, authority, the citation graph, distinguishment rules —
  runs and is covered by tests.
* The loop produces `#001 → FOLLOWS → #002 → DISTINGUISHES #001 → #003`.
* The Reporter API, indexer and frontend are wired end to end.

**Not deployed**

* Nothing has been deployed to Bradbury or mainnet; `HOLDING_REGISTRY_ADDRESS` is
  empty in `.env.example`. The live adapter is written against the documented
  `genlayer-py` 0.18.0 API and has **not** been exercised against a node.

**Simulated, and labelled as such**

* `GENLAYER_NETWORK=demo` executes the real contract files in a local development
  runtime. There is no consensus, no validator committee, no appeal window, no
  chain and no LLM call — a deterministic scripted responder answers the prompt.
  Every response carries `simulated: true` and a `DEMO` provenance mode. Simulated
  cases are never presented as historical GenLayer cases.
* Consensus v0.6 requires fee fields on every deploy and write; that API exists only
  in the 0.19 release candidate, so the adapter is pinned to 0.18.0 and sends none.
  Deploying on a v0.6 network means moving to 0.19 and threading fees through
  `LiveChain.write` — contained to one file.

---

## Frontend

Next.js 15 · TypeScript · Tailwind · Framer Motion · Lucide (sparingly).

| Route | What it is |
|---|---|
| `/` | Editorial landing: hero chain, the problem, the scroll-driven **PrecedentMemory**, the live demo, the distinguishment demo, the four parts (light section), consistency, integration, why now |
| `/reporter` | The precedent explorer: search + domain / decision / authority / appeal filters, sort, loading + empty states |
| `/holdings` | Archival index — dense table, newest first |
| `/holdings/[id]` | Holding detail: issue, facts, verdict, ratio, evidence accordion, precedent considered, citation map, cited by, distinguished by, authority breakdown |
| `/cases` | Case list with consensus and disposition |
| `/cases/[id]` | Case detail: retrieval, precedent-vs-case comparison, distinguishment, sequential panel review, resulting holding |
| `/precedent` | Live adjudication console — pick a case, run the panel, watch retrieval → vote → verdict |
| `/domains` | Per-domain consistency, volume, velocity, leading issue |
| `/integrations` | Where HOLDING sits in the loop, and what changes per application |
| `/developers` | Emit / retrieve / distinguish, the code, the twelve-field schema |
| `/about` | The gap, the scholarship that named it, why only GenLayer, what this is not, sources |

**Data layer.** Pages render through `getCorpus()` (`lib/data/live.ts`), which fetches
the Reporter (`lib/api/client.ts`) and maps its typed JSON into the UI shape. With no
API configured it falls back to the bundled demo corpus in `lib/data/`; contract
records in DEMO mode are shown alongside it; on a live network only contract records
are shown. `SourceTag` renders DEMO / TESTNET / MAINNET on every figure.

### Design system

- **Type** — Instrument Serif (display), Geist (interface + body), IBM Plex Mono (metadata, code, labels).
- **Palette** — Obsidian `#0A0B0D` and Ink `#111317`, Paper `#F3F0E8`, Verdict Copper `#D7A45A` used only for authority, finality and active state. Green / red / blue are semantic states only.
- **Layout** — 1240px shell, 12-column grid, thin rules, 8–12px radii, editorial whitespace.
- **Motion** — 150–220ms interaction, 250–450ms transitions, `cubic-bezier(0.16, 1, 0.3, 1)`, no springs. Full `prefers-reduced-motion` support.
- **Contrast** — muted ink lifted to `#7C7E77` on dark surfaces (the specified `#686A67` measures ~3.6:1 on obsidian); `#686A67` on paper.

### QA scripts

```bash
node scripts/audit.mjs      # layout overflow, banned fonts, tap targets, h1 count, console errors
node scripts/contrast.mjs   # WCAG contrast on every text node
node scripts/links.mjs      # crawls internal links for 404s
node scripts/interact.mjs   # drives the demos end to end
```

---

## Sources

GenLayer documentation (networks, transaction statuses, finality, appeals, consensus
v0.6, equivalence principle, calling LLMs, vector storage, genlayer-py) — linked in
full at the end of [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#11-sources).
