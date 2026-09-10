# HOLDING — testing and deployment

Order matters: prove the checkout, deploy the API, deploy the site, then — and only
then — point everything at a live GenLayer network.

---

## Phase 0 — prove the checkout (5 minutes)

```bash
git clone https://github.com/<USERNAME>/holding.git holding-check && cd holding-check

python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python scripts/render_contract.py --check   # generated contract is current
pytest tests/ -q                            # 127 passed
GENLAYER_NETWORK=demo python scripts/demo_loop.py
```

Expected last lines of the demo:

```
HOLDING 000001  APPROVED  FINAL   FOLLOWS← HLD-000002, DISTINGUISHES← HLD-000003
HOLDING 000002  APPROVED  FINAL   FOLLOWS HLD-000001
HOLDING 000003  REJECTED  FINAL   DISTINGUISHES HLD-000001
```

`.github/workflows/ci.yml` runs exactly this on every push — check the Actions tab
is green before deploying anything.

## Phase 1 — test the API and site locally

```bash
# terminal 1
GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=dev-admin-token \
  python -m uvicorn services.api.main:app --host 0.0.0.0 --port 8000

# terminal 2
npm install
HOLDING_API_URL=http://127.0.0.1:8000 npm run dev        # http://localhost:3000
```

Checks:

| Check | Command | Expected |
|---|---|---|
| Health | `curl localhost:8000/health` | `status: ok`, `network.mode: DEMO` |
| Holdings | `curl "localhost:8000/holdings"` | 3 items, all `FINAL` |
| Cold start | `curl "localhost:8000/holdings/search?q=anything"` with an empty registry | `items: []`, never an error |
| Citations | `curl localhost:8000/holdings/HLD-000001/citations` | `FOLLOWS` + `DISTINGUISHES` |
| Writes need auth | `curl -X POST localhost:8000/admin/reload` | `401` |
| Site shows live rows | open `/holdings` | rows `000001–000003` first |
| Honest fallback | stop the API, reload `/holdings` | demo corpus, every figure tagged DEMO |

Then `npm run build` (must print `✓ Generating static pages (36/36)`).

---

## Phase 2 — deploy the Reporter API

Any host that runs a container or a Python process. The repo ships a `Dockerfile`.

### Docker (local or any VPS)

```bash
docker build -t holding-reporter .
docker run -p 8000:8000 --env-file .env holding-reporter
curl localhost:8000/health
```

### Railway

```bash
railway login && railway init
railway up --dockerfile Dockerfile
railway variables set GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=<strong-token> RATE_LIMIT_PER_MINUTE=120
railway domain
```

### Render (render.yaml-free, UI or CLI)

* New → Web Service → Runtime: Docker → root directory `.`
* Health check path: `/health`
* Environment: the variables in the table below.

### Fly.io

```bash
fly launch --dockerfile Dockerfile
fly secrets set GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=<strong-token>
fly deploy
```

**Environment (all hosts)**

| Variable | Value at this stage |
|---|---|
| `GENLAYER_NETWORK` | `demo` |
| `HOLDING_ADMIN_TOKEN` | a long random string — **not** `dev-admin-token` |
| `HOLDING_DEMO_SEED` | `true` while demoing, `false` for a clean registry |
| `RATE_LIMIT_PER_MINUTE` | `120` (raise for the public site) |
| `CORS_ORIGINS` | your site origin, only if the browser calls the API directly |
| `HOLDING_ALLOW_SIMULATION` | leave `false` |
| `GENLAYER_PRIVATE_KEY` | unset until Phase 4 |

---

## Phase 3 — deploy the site

### Vercel (recommended for Next.js)

```bash
npm i -g vercel
vercel link
vercel env add HOLDING_API_URL production     # https://<your-api-host>
vercel --prod
```

Or in the Vercel dashboard: Framework **Next.js**, root `.`, build `npm run build`,
env `HOLDING_API_URL=https://<your-api-host>` (and `NEXT_PUBLIC_HOLDING_API_URL` if
you ever call the API from the browser).

Post-deploy check: open `https://<site>/holdings`. Live rows appear first and the
network tag reads `DEMO` until Phase 4. If the API is unreachable the site falls back
to its labelled demo corpus instead of breaking — verify that by temporarily pointing
`HOLDING_API_URL` at a dead host.

### Indexer (optional worker)

```bash
python -m services.indexer.indexer --interval 30 --db data/indexer.db
```

Run it as a second process/service on the same host as the API, or as a separate
worker with a mounted volume for `data/`. It is read-only against the contract; if it
dies, the site is unaffected.

---

## Phase 4 — go live on GenLayer (Bradbury testnet first)

1. **Fund an operator account** — faucet: https://testnet-faucet.genlayer.foundation

2. **Move to the fee-capable SDK.** Consensus v0.6 requires fee fields on every
   deploy and write; those exist in `genlayer-py` **0.19 RC**, not the pinned 0.18.0.

   ```bash
   pip install "genlayer-py==0.19.0rc*"          # pin the exact RC you test against
   # then thread FeesDistribution/feeValue through services/lib/genlayer/live.py :: write()
   ```

   Until that is done, live writes will be rejected by the node. This is the one
   blocker for a live deployment and it is isolated to a single file.

3. **Deploy the contract** (GenLayer Studio, or the CLI):

   ```bash
   genlayer deploy contracts/HoldingRegistry.py --network bradbury
   genlayer deploy contracts/Adjudicator.py --network bradbury --args <registry_address> digital-commerce RefundArbiter 5
   ```

   Record both addresses. Confirm on the explorer:
   https://explorer-bradbury.genlayer.com

4. **Configure the API** and restart:

   ```
   GENLAYER_NETWORK=bradbury
   GENLAYER_RPC_URL=https://rpc-bradbury.genlayer.com
   GENLAYER_CHAIN_ID=4221
   HOLDING_REGISTRY_ADDRESS=0x…
   ADJUDICATOR_ADDRESS=0x…
   GENLAYER_PRIVATE_KEY=<operator key>
   HOLDING_DEMO_SEED=false
   ```

   With `GENLAYER_NETWORK` not `demo`, the adapter refuses to start without a
   registry address — it will not silently serve demo data.

5. **Register the writer** (owner only, on-chain):

   ```
   register_source(<adjudicator address>, true)     # its holdings arrive as PENDING
   register_attestor(<attestor address>, true)      # it may attest finality
   ```

6. **Run one real case** and watch the lifecycle:

   ```
   PROPOSED → VALIDATING → CONSENSUS → appeal window (~30 min) → FINALIZED
   ```

   Then attest: status **7 (Finalized)** *and* execution result
   `FINISHED_WITH_RETURN`. Status alone is not success.

   ```bash
   curl -X POST https://<api>/admin/holdings/<id>/finality \
     -H "X-Admin-Token: $TOKEN" -H "Idempotency-Key: attest-<id>-1" \
     -H "Content-Type: application/json" \
     -d '{"holding_id":"HLD-000001","tx_status_code":7,
          "execution_result":"FINISHED_WITH_RETURN",
          "finality_timestamp":<unix>,"source_tx":"0x…"}'
   ```

7. **Verify the live path:**

   * `/health` → `network.mode: TESTNET`, `simulated: false`
   * `/holdings` → only contract records; the site tag flips to `TESTNET`
   * `POST /demo/cases` → `403` unless `HOLDING_ALLOW_SIMULATION=true`
   * `get_precedent` on an empty registry → `[]`, never an error

8. **Mainnet**: repeat with `GENLAYER_NETWORK=mainnet`. `/demo/*` is hard-disabled
   there, and `HOLDING_ALLOW_SIMULATION` is ignored.

---

## Production checklist

* [ ] `HOLDING_ADMIN_TOKEN` is long, random, and stored only in the host's secret store
* [ ] `GENLAYER_PRIVATE_KEY` is a dedicated operator key, never logged, never committed
* [ ] `.env` is git-ignored; only `.env.example` is in the repo
* [ ] HTTPS everywhere; `CORS_ORIGINS` set to the exact site origin
* [ ] Rate limit tuned; `/health` exempt (used by the platform health check)
* [ ] Indexer has a persistent volume for `data/indexer.db`
* [ ] `HOLDING_DEMO_SEED=false` on any network that is not `demo`
* [ ] Alerts on `/health` → `status: degraded` (registry unreachable)

## If something breaks

| Symptom | Cause |
|---|---|
| `503 … HOLDING_REGISTRY_ADDRESS is required` | live mode without an address — set it or use `demo` |
| `503 … genlayer-py is not installed` | live mode on a host missing the SDK |
| `401 admin authorization required` | missing/incorrect `X-Admin-Token` |
| `503 admin writes are disabled` | `HOLDING_ADMIN_TOKEN` unset — by design, fail closed |
| `400 Idempotency-Key header is required` | write without a replay key |
| `429 rate limit exceeded` | lower request rate or raise `RATE_LIMIT_PER_MINUTE` |
| Site shows only the demo corpus | `HOLDING_API_URL` unset or the API is unreachable — the site falls back deliberately |
| Live writes rejected by the node | v0.6 fee fields — see Phase 4 step 2 |
