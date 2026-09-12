# How to deploy HOLDING — plain-English guide

This is the beginner-friendly version of `docs/DEPLOYMENT.md`. It explains **what**
you are deploying, **why**, and gives one command at a time. The detailed technical
version (with every flag and edge case) stays in `docs/DEPLOYMENT.md`.

---

## 1 · The big picture — what "going live" actually means here

HOLDING is three separate pieces, and they go live **in this order**:

| # | Piece | What it is | Where it lives when "live" |
|---|---|---|---|
| 1 | **Reporter API** | A Python server that answers all the data questions (search, holdings, cases, wallet sign-in) | A cloud host that runs containers (Railway, Render, Fly.io, any VPS) |
| 2 | **Website (frontend)** | The Next.js site people visit in their browser | Vercel (recommended) |
| 3 | **The contracts** | The `HoldingRegistry` and `Adjudicator` Intelligent Contracts | The GenLayer blockchain (Bradbury testnet first, then mainnet) |

The website and the API can go live **today**, in "DEMO mode" — everything works
end-to-end, but the records are clearly labelled **DEMO** (simulated cases, no real
blockchain). Only step 3 touches a real blockchain, and you do that **last**, on the
testnet first.

**The golden rule:** prove it locally → deploy the API → deploy the site → then and
only then point everything at a real GenLayer network.

---

## 2 · Before you start (one-time setup)

You need:

- **Python 3.11–3.13** (3.14 works, but needs `pydantic >= 2.12`)
- **Node.js 18+**
- A **GitHub** account
- A **Railway / Render / Fly.io** account (for the API) and a **Vercel** account (for the site)
- A **MetaMask** browser wallet (only needed for step 3, the blockchain part)

---

## 3 · Is the build ready to deploy? (verify it yourself)

Run these four commands from the repo root. **All four must be green** before you
deploy anything.

```bash
# 1. Is the generated contract up to date?
python scripts/render_contract.py --check
#    ✅ "contracts/HoldingRegistry.py is up to date"

# 2. Do all the tests pass?
python -m pytest tests/ -q
#    ✅ "181 passed"

# 3. Does the demo loop run end to end?
GENLAYER_NETWORK=demo python scripts/demo_loop.py
#    ✅ ends with HOLDING 000001/000002/000003 … APPROVED/REJECTED … FINAL

# 4. Does the website compile?
npm install        # first time only
npm run build
#    ✅ "✓ Generating static pages"
```

### What a green result looks like

| Check | Green | Red means |
|---|---|---|
| Contract render | "is up to date" | you edited the template but didn't regenerate — run `python scripts/render_contract.py` |
| Tests | `181 passed` | a real bug — fix before deploying |
| Demo loop | three `FINAL` holdings printed | the core contract logic broke |
| Frontend build | static pages generated, no errors | see the two notes below |

### Two frontend notes that trip people up

1. **The website build needs internet at build time.** The site loads
   `Instrument Serif` and `IBM Plex Mono` from Google Fonts via `next/font/google`,
   which downloads them during `npm run build`. That's automatic on Vercel and in
   GitHub Actions. It only fails if you build **offline or behind a firewall that
   blocks `fonts.googleapis.com`** (it fails with "Failed to fetch … from Google
   Fonts"). If you hit that, it's the network, not your code.

2. **`npm run lint` asks an interactive question the first time.** ESLint isn't
   configured yet, so `next lint` prompts to set it up. It's optional — `next build`
   does not require it. Skip it for now or run the one-time setup when you're ready.

> Verified on this checkout (2026-09-12): contract current ✅ · 181 tests ✅ ·
> demo loop ✅ · full API smoke test 27/27 ✅ · TypeScript compiles ✅.
> `npm run build` could not be completed *inside the sandbox* because Google Fonts
> is blocked here — it is expected to succeed on Vercel/CI/local with normal internet.

---

## 4 · Step 1 — Deploy the Reporter API (the data server)

The API is packaged as a container (`Dockerfile` is already in the repo), so any
Docker host works. Pick one:

### Option A — Railway (easiest)

```bash
npm i -g @railway/cli        # or install the Railway CLI from their site
railway login
railway init
railway up --dockerfile Dockerfile
railway variables set \
  GENLAYER_NETWORK=demo \
  HOLDING_ADMIN_TOKEN=<make-up-a-long-random-string> \
  RATE_LIMIT_PER_MINUTE=120
railway domain               # prints your API address, e.g. https://xxx.up.railway.app
```

### Option B — Render

1. New → **Web Service** → Runtime: **Docker**, root directory `.`
2. Health check path: `/health`
3. Add these environment variables:

   | Variable | Value |
   |---|---|
   | `GENLAYER_NETWORK` | `demo` |
   | `HOLDING_ADMIN_TOKEN` | a long random string — **not** `dev-admin-token` |
   | `HOLDING_DEMO_SEED` | `true` (while demoing) |
   | `RATE_LIMIT_PER_MINUTE` | `120` |

   > ⚠️ **Render port gotcha.** Render looks for your app on the `PORT`
   > environment variable (default **10000**). If the deploy fails with
   > "failed to detect open port 10000", either set `PORT=8000` in the
   > environment — or better, use the Dockerfile that binds to `$PORT`
   > (it does since the fix). A hard-coded 8000 is why a fresh Render deploy
   > times out at the very last step even though the build succeeded.

### Option C — Fly.io

```bash
fly launch --dockerfile Dockerfile
fly secrets set GENLAYER_NETWORK=demo HOLDING_ADMIN_TOKEN=<long-random-string>
fly deploy
```

### How you know it worked

```bash
curl https://YOUR-API-HOST/health
#    ✅ {"status":"ok","network":{"mode":"DEMO", ...}}
```

Then run the same one-command gate the repo uses against production:

```bash
python scripts/smoke_test.py --base-url https://YOUR-API-HOST \
                             --admin-token "$HOLDING_ADMIN_TOKEN" --expect-mode DEMO
#    ✅ "27/27 checks passed"
```

---

## 5 · Step 2 — Deploy the website (the part people see)

Vercel is the recommended host for Next.js.

```bash
npm i -g vercel
vercel link
vercel env add HOLDING_API_URL production     # set it to https://YOUR-API-HOST
vercel --prod
```

Or do it in the Vercel dashboard: Framework **Next.js**, root `.`, build command
`npm run build`, and one environment variable:

```
HOLDING_API_URL=https://YOUR-API-HOST
```

**Leave `NEXT_PUBLIC_HOLDING_API_URL` unset.** The browser talks to the site's own
`/api/reporter/*`, and Next quietly forwards those calls to `HOLDING_API_URL` on the
server. That means **no CORS config and no API address exposed in the page**.

### How you know it worked

Open `https://YOUR-SITE/holdings`. You should see rows `000001–000003` at the top,
each tagged **DEMO**. If the API is down, the site deliberately falls back to its
bundled demo data instead of showing an error — so "it renders" is not enough; make
sure the rows come from the API (they change when you change the API's data).

---

## 6 · Step 3 — Go live on GenLayer (blockchain), testnet first

This is the part that touches a real network. Do **Bradbury testnet** first, then
mainnet. Nothing here spends real money — testnet uses faucet GEN.

1. **Get testnet money.** Fund an account at the faucet:
   https://testnet-faucet.genlayer.foundation

2. **Install the live SDK** (only needed for real networks):

   ```bash
   pip install -r requirements-live.txt
   ```

   (This installs `genlayer-py==0.19.0rc2`, which carries the fee fields consensus
   v0.6 requires. The repo already wires fees up for you — no fee code to write.)

3. **Deploy the contracts.** This does a dry-run first (safe, no network), then the
   real deploy. It prints a ready-made `.env` block at the end:

   ```bash
   export GENLAYER_PRIVATE_KEY="0xPASTE_YOUR_TESTNET_KEY"

   python scripts/deploy_contracts.py --dry-run
   python scripts/deploy_contracts.py --network bradbury --write-env
   ```

   Copy the two addresses it prints (`registry address` and `adjudicator address`).
   You can watch the deploy on https://explorer-bradbury.genlayer.com.

4. **Point the API at the real network** by updating its environment variables and
   restarting it:

   ```
   GENLAYER_NETWORK=bradbury
   GENLAYER_RPC_URL=https://rpc-bradbury.genlayer.com
   GENLAYER_CHAIN_ID=4221
   HOLDING_REGISTRY_ADDRESS=0x…   (from step 3)
   ADJUDICATOR_ADDRESS=0x…        (from step 3)
   GENLAYER_PRIVATE_KEY=0x…       (same testnet key)
   HOLDING_DEMO_SEED=false
   ```

   Safety net: with `GENLAYER_NETWORK` set to anything but `demo`, the API **refuses
   to start** if the registry address is missing — so it can never silently serve
   demo data while pretending to be live.

5. **Verify the live path** with the same gate as before (note `TESTNET`):

   ```bash
   python scripts/smoke_test.py --base-url https://YOUR-API-HOST \
                                --admin-token "$HOLDING_ADMIN_TOKEN" --expect-mode TESTNET
   ```

   Things to check:
   - `/health` → `network.mode: TESTNET`, `simulated: false`
   - `/holdings` → only real contract records; the site tag flips from `DEMO` to `TESTNET`
   - `/auth/config` → `expected.chain_id` is `4221` (not `0`)

6. **Mainnet.** Same steps with `GENLAYER_NETWORK=mainnet` (and real GEN). On
   mainnet the `/demo/*` routes are hard-disabled.

---

## 7 · The production checklist (tick before calling it done)

- [ ] `HOLDING_ADMIN_TOKEN` is long and random, stored only in the host's secret store
- [ ] `GENLAYER_PRIVATE_KEY` is a dedicated operator key — never logged, never committed
- [ ] `.env` is git-ignored (only `.env.example` lives in the repo)
- [ ] HTTPS everywhere; `CORS_ORIGINS` set only if the browser calls the API directly
- [ ] `HOLDING_DEMO_SEED=false` on any network that is not `demo`
- [ ] `HOLDING_PUBLIC_ORIGIN` set to the site origin (so the wallet sign-in message reads correctly)
- [ ] `HOLDING_SESSION_SECRET` set (so rotating the admin token doesn't log everyone out)
- [ ] Indexer has a persistent volume for `data/indexer.db` (if you run it)
- [ ] Alerts on `/health` → `status: degraded`

---

## 8 · If something breaks

| Symptom | Cause |
|---|---|
| `503 … HOLDING_REGISTRY_ADDRESS is required` | live mode without an address — set it, or use `demo` |
| `401 admin authorization required` | missing / wrong `X-Admin-Token` |
| `400 Idempotency-Key header is required` | a write without its replay key |
| `429 rate limit exceeded` | too many requests — raise `RATE_LIMIT_PER_MINUTE` |
| Site shows only demo rows | `HOLDING_API_URL` unset or the API unreachable — the site falls back deliberately |
| Wallet "Connect" does nothing | no injected wallet in this browser (MetaMask/Rabby/Brave inject; mobile wallets don't) |
| Live writes rejected by the node | v0.6 fee fields — see the ABI note at the bottom of `docs/DEPLOYMENT.md` |

The full troubleshooting table, plus the recent Bradbury ABI fix and every deployer
flag, is in `docs/DEPLOYMENT.md`.
