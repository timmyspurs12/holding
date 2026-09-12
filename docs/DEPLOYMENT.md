# HOLDING — testing and deployment

Order matters: prove the checkout, deploy the API, deploy the site, then — and only
then — point everything at a live GenLayer network.

---

## Phase 0 — prove the checkout (5 minutes)

```bash
git clone https://github.com/<USERNAME>/holding.git holding-check && cd holding-check

python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**Python version.** CPython 3.11–3.13 is recommended. Python 3.14 works, but only
with `pydantic >= 2.12` — older pydantic has no cp314 wheel, so pip falls back to
compiling `pydantic-core` from Rust and fails without Visual Studio C++ build
tools. If you see `Failed building wheel for pydantic-core`, either install
Python 3.12, or install the deps unpinned:

```bash
pip install "pydantic>=2.12" "fastapi>=0.115" "uvicorn>=0.34" \
            "httpx>=0.27" "pytest>=8" "python-dotenv"
```

`genlayer-py` is deliberately kept out of `requirements.txt` (it is only needed for
live networks and pulls heavy web3 dependencies). Install it with
`pip install -r requirements-live.txt` when you reach Phase 4.

python scripts/render_contract.py --check   # generated contract is current
python -m pytest tests/ -q                  # 127 passed
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

Finally, the one-command gate — the same script you will run against production:

```bash
python scripts/smoke_test.py --base-url http://127.0.0.1:8000 \
                             --admin-token dev-admin-token --expect-mode DEMO
# 27/27 checks passed
```

It asserts every route responds, that search returns only `FINAL` holdings, that
every holding carries provenance and authority components, and that admin writes
are refused on authorization *before* the payload is validated.

---

## Phase 2 — deploy the Reporter API

Any host that runs a container or a Python process. The repo ships a `Dockerfile`.

### Docker (local or any VPS)

```bash
docker build -t holding-reporter .
docker run -p 8000:8000 --env-file .env holding-reporter
curl localhost:8000/health
```

**Verify any deployment** (local Docker, Railway, Render, Fly) with:

```bash
python scripts/smoke_test.py --base-url https://YOUR-API-HOST \
                             --admin-token "$HOLDING_ADMIN_TOKEN" --expect-mode DEMO
# add --expect-mode TESTNET once Phase 4 is live; the script fails on a mode mismatch
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
vercel env add HOLDING_API_URL production     # https://YOUR-API-HOST
vercel --prod
```

Or in the Vercel dashboard: Framework **Next.js**, root `.`, build `npm run build`,
env `HOLDING_API_URL=https://YOUR-API-HOST`.

Leave `NEXT_PUBLIC_HOLDING_API_URL` unset. The browser calls `/api/reporter/*` on
the site's own origin and Next proxies it to `HOLDING_API_URL`, so there is no
CORS to configure and no API address in the page. Set it only if the API lives on
another origin — and then add that origin to the API's `CORS_ORIGINS`.

If you do host them apart, also set on the **API**:

```
HOLDING_PUBLIC_ORIGIN=https://YOUR-SITE     # stamped into the wallet sign-in message
HOLDING_SESSION_SECRET=<random>               # sessions survive an admin-token rotation
HOLDING_OPERATOR_ADDRESSES=0x…,0x…            # wallets that count as operators
```

Without `HOLDING_PUBLIC_ORIGIN` the signed message shows the API's own host, which
works but reads badly. Without a session secret, rotating `HOLDING_ADMIN_TOKEN`
logs every wallet out.

Post-deploy check: open `https://YOUR-SITE/holdings`. Live rows appear first and the
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

2. **Install the fee-capable SDK.** Consensus v0.6 requires a fee payload on
   every deploy and write. Those fields exist in `genlayer-py` **0.19.0rc2** and
   later — not in 0.18.0.

   ```bash
   pip install -r requirements-live.txt
   ```

   You do **not** have to write any fee code. The fee payload is already wired
   up: `services/lib/genlayer/live.py` detects whether the installed SDK accepts
   a `fees` argument (by inspecting the signature, not by version sniffing),
   estimates the fee for each specific call, and attaches it. On 0.18 and
   earlier it sends the call unchanged.

   Escape hatches:

   ```bash
   HOLDING_FEE_ESTIMATE=off       # never attach fees
   HOLDING_FEE_ESTIMATE=auto      # default: estimate, and send anyway if it fails
   ```

   If a transaction is rejected for running out of fee budget mid-consensus,
   top it up with `client.top_up_fees(tx_id, distribution, value)` rather than
   resubmitting — resubmitting replays the call.

   `pip install "genlayer-py==0.19.0rc*"` does **not** work: pip does not accept
   a wildcard in a `==` specifier. Use the exact version, as above.

3. **Deploy the contracts.** The repo ships a deployer that does both, in order,
   waits for real `FINALIZED` receipts, and prints the `.env` block:

   ```bash
   pip install -r requirements-live.txt
   export GENLAYER_PRIVATE_KEY="0xPASTE_YOUR_TESTNET_KEY"

   python scripts/deploy_contracts.py --dry-run        # validates files + args, no network
   python scripts/deploy_contracts.py --network bradbury --write-env
   ```

   Output you need:

   ```
   registry address      0x…
   adjudicator address   0x…
   --- add to .env ---
   GENLAYER_NETWORK=bradbury
   HOLDING_REGISTRY_ADDRESS=0x…
   ADJUDICATOR_ADDRESS=0x…
   HOLDING_DEMO_SEED=false
   ```

   The deployer account becomes the registry **owner** (the only address that can
   register sources and attestors) unless you pass `--owner 0x…`. If a receipt
   does not expose the created address, copy it from the explorer link the script
   prints, then resume without redeploying:

   ```bash
   python scripts/deploy_contracts.py --network bradbury --registry-address 0xPASTE_REGISTRY_ADDRESS --write-env
   ```

   Deploying is not the last step. The script then calls
   `register_source(<adjudicator>, true)` and `register_attestor(your address, true)` and
   waits for `FINALIZED` receipts, because the registry refuses holdings from
   unregistered contracts. Pass `--no-register` to skip that, or `--attestor 0x…`
   to name a different attestor.

   Explorer: https://explorer-bradbury.genlayer.com

   `--dry-run` is safe to run anywhere: it parses both contracts and prints the
   constructor arguments without touching a network.

4. **Configure the API** and restart:

   ```
   GENLAYER_NETWORK=bradbury
   GENLAYER_RPC_URL=https://rpc-bradbury.genlayer.com
   GENLAYER_CHAIN_ID=4221
   HOLDING_REGISTRY_ADDRESS=0x…
   ADJUDICATOR_ADDRESS=0x…
   GENLAYER_PRIVATE_KEY="0xPASTE_YOUR_TESTNET_KEY"
   HOLDING_DEMO_SEED=false
   ```

   With `GENLAYER_NETWORK` not `demo`, the adapter refuses to start without a
   registry address — it will not silently serve demo data.

5. **Confirm the registration** step 3 performed (owner only, on-chain):

   ```
   register_source(<adjudicator address>, true)     # its holdings arrive as PENDING
   register_attestor(<attestor address>, true)      # it may attest finality
   ```

   If you deployed with `--no-register`, do both now:

   ```bash
   python scripts/deploy_contracts.py --network bradbury \
     --registry-address 0xPASTE_REGISTRY_ADDRESS --no-adjudicator --attestor 0xPASTE_YOUR_ADDRESS
   ```

   Until a source is registered, `create_holding` from that contract is rejected
   with *"registered source contract or owner only"* — that is the corpus-poisoning
   defence working, not a bug.

6. **Run one real case** and watch the lifecycle:

   ```
   PROPOSED → VALIDATING → CONSENSUS → appeal window (~30 min) → FINALIZED
   ```

   Then attest: status **7 (Finalized)** *and* execution result
   `FINISHED_WITH_RETURN`. Status alone is not success.

   ```bash
   curl -X POST https://YOUR-API-HOST/admin/holdings/THE-HOLDING-ID/finality \
     -H "X-Admin-Token: $TOKEN" -H "Idempotency-Key: attest-<id>-1" \
     -H "Content-Type: application/json" \
     -d '{"holding_id":"HLD-000001","tx_status_code":7,
          "execution_result":"FINISHED_WITH_RETURN",
          "finality_timestamp":<unix>,"source_tx":"0x…"}'
   ```

7. **Verify the live path** with the same gate you used locally:

   ```bash
   python scripts/smoke_test.py --base-url https://YOUR-API-HOST \
                                --admin-token "$HOLDING_ADMIN_TOKEN" --expect-mode TESTNET
   ```


   * `/health` → `network.mode: TESTNET`, `simulated: false`
   * `/holdings` → only contract records; the site tag flips to `TESTNET`
   * `POST /demo/cases` → `403` unless `HOLDING_ALLOW_SIMULATION=true`
   * `get_precedent` on an empty registry → `[]`, never an error
   * `/auth/config` → `expected.chain_id` is `4221`, not `0`
   * `POST /operator/source-contracts` with no session → `401`, not `422`

   Then do it for real: open `/developers`, connect a wallet, propose the
   adjudicator address you just deployed, and confirm it lands as `PENDING`.
   Approving it is intentionally not possible from the browser — that needs
   `HOLDING_ADMIN_TOKEN`.

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
* [ ] `HOLDING_PUBLIC_ORIGIN` set to the site origin (wallet sign-in message)
* [ ] `HOLDING_SESSION_SECRET` set, so admin-token rotation does not log everyone out
* [ ] `HOLDING_OPERATOR_ADDRESSES` lists the operator wallets, or is deliberately empty
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
| Connect button does nothing | no injected wallet in this browser. MetaMask/Rabby/Brave inject; WalletConnect and mobile wallets do not |
| Wallet connects but `/operator/*` returns 401 | session expired (8 h) or `HOLDING_ADMIN_TOKEN` rotated without a `HOLDING_SESSION_SECRET` |
| Signature rejected after a domain change | the nonce is bound to `HOLDING_PUBLIC_ORIGIN`; set it and sign again |
| Wallet asks to switch network and will not | chain id from `/auth/config` is not in the wallet — accept the add-network prompt, or check `GENLAYER_CHAIN_ID` |
| Live writes rejected by the node | v0.6 fee fields — see Phase 4 step 2 |
| `Transaction HexBytes('0x…') is not in the chain after 600 seconds` | the EVM envelope (addTransaction) never got an L2 receipt — see "Live deployment (2026-09-12)" below. Track it with `scripts/check_deploy_tx.py 0x… --watch`; resume with `--registry-tx 0x…` |

---

## Live deployment (verified 2026-09-11)

### Root cause: the SDK and the deployed contract speak different ABIs

genlayer-py 0.19 always encodes consensus calls with the v0.6 **fee-bearing**
entrypoint:

```
addTransaction((tuple, ...))   selector 0x35a251fb
```

Bradbury's deployed consensus contract does not implement that function. Calling
an unknown selector reverts with **empty revert data**, which is why every
failure looked like a bare `execution reverted` with no reason, no matter what
was tried.

The same SDK still ships the pre-fee ABI, and forcing it makes the SDK emit:

```
addTransaction(address,address,uint256,uint256,bytes,uint256)   selector 0xe71d5196
```

That selector **is** implemented, and transactions using it are succeeding on
Bradbury right now — the most recent ones sampled all returned `status=1`.

Measured side by side, same network, same moment:

| encoding | selector | result |
|---|---|---|
| fee-bearing (0.19 default) | `0x35a251fb` | reverted |
| pre-fee (legacy ABI) | `0xe71d5196` | accepted |

### The fix

`deploy_contracts.py` now detects this automatically. If the network's fee
policy call reverts, it swaps in the pre-fee consensus ABI and omits fees (they
can only travel on the fee-bearing path). You will see:

```
  ! this network does not implement the v0.6 fee-bearing addTransaction
    (its fee policy call reverts), so genlayer-py's default encoding would
    revert with no reason. Switching to the pre-fee consensus ABI.
```

Control it with `--consensus-abi {auto,fees,legacy}` (env
`HOLDING_CONSENSUS_ABI`, default `auto`).

Verified end to end: after the switch, the failure changes from
`execution reverted` to `InvalidTransaction`/`LackOfFundForMaxFee`, which is the
**balance** check — the transaction shape is accepted. A funded key should
deploy.

```bash
cd /c/Users/ADMIN/downloads/holding
export GENLAYER_PRIVATE_KEY="0xYOUR_TESTNET_KEY"
python scripts/deploy_contracts.py --network bradbury --write-env
```

### Supporting evidence

- Bradbury fee manager `0xF205868b…`: `GENPerTimeUnit()` = 0 and
  `storageUnitPrice()` = 0, but **`quoteGasPrice()` and
  `messageFeeParamsBudgetFloor()` are absent**, so `get_current_fee_policy()`
  always reverts. Asimov is identical.
- Consensus contract bytecode exposes 6 function selectors, none of which is
  `0x35a251fb`.
- Deployer balance and nonce are fine (90.99 GEN, nonce 0).

### An earlier claim, retracted

A previous revision of this document said Bradbury was rejecting ~83% of
consensus transactions and was effectively down. **That was wrong.** It came
from a 12-transaction sample that did not measure what it looked like it was
measuring: reverted transactions emit no events, so log-based sampling is
biased toward successes, and a re-scan of a different window found a completely
different picture. The network is healthy. The problem was always the ABI
mismatch described above.

### Improvements made while diagnosing this

- `--consensus-abi auto|fees|legacy` — the fix above.
- `--finality-timeout` (env `HOLDING_FINALITY_TIMEOUT`, default **600**).
  genlayer-py's own wait is only 10 polls x 3 s = **30 s**, too short for
  consensus.
- Fee estimation is retried (env `HOLDING_FEE_RETRIES`, default 10) instead of
  degrading to a feeless transaction.
- `--fees {auto,zero,off}` sends an explicit fee distribution.
- `--adjudicator-address` resumes a partial deploy without redeploying.
- `studio_devnet` is selectable as `--network`.
- `diagnose_network.py` probes the four fee-manager methods, reports consensus
  activity via a single `eth_getLogs` call (~20 s), and states in its own output
  that it cannot measure a failure rate.
- `scripts/probe_revert.py` prints the raw revert payload for a deploy.

---

## Live deployment (2026-09-12): "not in the chain after 600 seconds"

### What the 600 seconds actually wait for

A GenLayer write has **two layers**, and the script's error came from the
first one, not from GenLayer consensus:

1. **L2 (EVM) envelope** — genlayer-py signs an EIP-1559 transaction that
   calls `addTransaction` on the consensus contract
   (`0x0112Bf6e…271D` on Bradbury, a ZKsync-based chain) and submits it with
   `eth_sendRawTransaction`. Its return value — the *envelope hash* — is what
   `eth_sendRawTransaction` gives back, and it is the hash in the error
   message. Inside the SDK, `deploy_contract` then waits for the envelope's
   EVM receipt: a blind `eth_getTransactionReceipt` poll with
   `timeout = --tx-timeout` (600 s). If no receipt appears, web3 raises
   `TimeExhausted: Transaction HexBytes('0x…') is not in the chain after 600
   seconds`. **That is the whole 600-second window** — it is L2 inclusion,
   nothing else.
2. **Consensus** — only once the envelope is mined does the consensus
   contract register a GenLayer transaction (a *different* hash, emitted in
   the `NewTransaction` / `CreatedTransaction` log), which then walks
   Pending → Proposing → Committing → Revealing → Accepted → Finalized
   (or Canceled / timeout). Finality is when the appeal window closes; an
   ACCEPTED transaction can wait there for a while. `client.wait_for_
   transaction_receipt(wait_until="finalized")` polls this layer only.

Consequences that cost real time:

- The hash in the error message (and in the explorer link the old script
  printed) is the **envelope hash**. The GenLayer explorer
  (`explorer-bradbury.genlayer.com/tx/…`) is keyed by the **consensus txId**,
  so it answers "Transaction details unavailable" for an envelope hash even
  when the transaction is perfectly healthy. The envelope hash belongs in
  the EVM-layer explorer
  (`zksync-os-testnet-genlayer.explorer.zksync.dev/tx/…`).
- If the envelope never gets a receipt (dropped from the mempool — e.g. the
  SDK's `maxFeePerGas = baseFee + 2 gwei` below the sequencer's current gas
  price, or a balance/nonce problem), nothing on the consensus layer ever
  happens, and no contract is created. A 600-second L2-inclusion window is
  already generous; "not in the chain" after that means *dropped*, not
  *slow*.

### What the current state of a submitted hash can be

`scripts/check_deploy_tx.py` classifies it (read-only, no key needed):

| state | meaning | what to do |
|---|---|---|
| PENDING | in the L2 mempool, not in a block | `--watch`; do **not** resend |
| MINED → PROCESSING | envelope in a block; consensus lifecycle moving (incl. ACCEPTED in its appeal window) | wait; finality is not a race |
| FINALIZED | consensus Finalized **and** execution `FINISHED_WITH_RETURN` | take the deployed address, resume |
| FAILED | EVM revert (receipt status 0), consensus Canceled, or a non-accepted decision | nothing was deployed; a fresh deploy is the only path |
| UNKNOWN | not in any block and not in the node's mempool | most likely dropped — see the printed gas/balance/nonce diagnostics before deciding anything |
| SUPERSEDED | the envelope's nonce slot was already used by another tx | can never mine; nothing was deployed |

```bash
pip install "web3>=7"          # the checker needs only web3, no genlayer-py
python scripts/check_deploy_tx.py 0xENVELOPE_HASH          # one-shot
python scripts/check_deploy_tx.py 0xENVELOPE_HASH --watch  # until terminal state
python scripts/check_deploy_tx.py --consensus-tx 0x… --watch

# with the deployer address (no key needed) the drop diagnostics also cover
# the account's balance and nonce, so an UNKNOWN result can be pinned to a
# cause (unfunded / fee-starved / queued) rather than left as "not propagated"
python scripts/check_deploy_tx.py 0xENVELOPE_HASH --sender 0xDEPLOYER
```

Exit codes: 0 FINALIZED · 1 FAILED · 2 UNKNOWN · 3 PENDING/PROCESSING ·
4 finalized but no address exposed.

### Resuming without redeploying

The deploy script never resends a transaction that was already submitted.
When its own wait times out it keeps tracking the same envelope read-only,
prints the state (PENDING / PROCESSING / FINALIZED / FAILED / UNKNOWN) and
exits with the code above. To pick it up in a later run:

```bash
# track the submitted envelope to finality, then continue (adjudicator, registration)
python scripts/deploy_contracts.py --network bradbury --registry-tx 0xENVELOPE_HASH --write-env

# or, once you have the deployed address (explorer / checker output)
python scripts/deploy_contracts.py --network bradbury --registry-address 0xADDRESS --write-env
```

`--adjudicator-tx` works the same way for the adjudicator deploy.

### Where the deployed address lives

**Not** in the EVM envelope receipt's `contractAddress` (that is null — the
envelope calls a contract, it is not a CREATE). The created contract address
is a **consensus-layer** value: the stored `recipient` field of the consensus
transaction record (zero while pending, the created address after the GenVM
executes the deploy). genlayer-py surfaces it as `data.contract_address` on
`get_transaction()` / `wait_for_transaction_receipt()`, and the explorer
shows it as the deploy's "Created contract". The script reads it from the
consensus record and falls back to telling you where to copy it from.

### Improvements shipped with this diagnosis

- Status-aware polling on **both** layers with periodic state printing
  (`PENDING / PROCESSING / FINALIZED / FAILED`, plus `UNKNOWN` and
  `SUPERSEDED` for the EVM layer) instead of one blind 600-second wait.
- The envelope hash is captured at `eth_sendRawTransaction` time, so the
  tracker resumes from the exact submitted transaction even when the SDK's
  error message is unhelpful.
- `--registry-tx` / `--adjudicator-tx` resume from an already-submitted
  envelope (read-only tracking — nothing is ever resent).
- `scripts/check_deploy_tx.py` — standalone read-only checker (pure web3,
  no private key, no genlayer-py) for any submitted hash.
- Distinguishable exit codes (0/1/2/3/4) so a timeout while
  PENDING/PROCESSING is not confused with a failure.
- Failure output now points the envelope hash at the EVM-layer explorer and
  the consensus txId at the GenLayer explorer.
