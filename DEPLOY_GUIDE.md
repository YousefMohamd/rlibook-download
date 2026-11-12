# Deploy guide — RliBook download proxy on Fly.io

The user deploys this on **their own Fly.io account**. Muse never deploys
and never asks for credentials.

## ⚠️ Cost — read this first

**Fly.io has no free tier for new accounts anymore** (retired October 2024).
It is pure pay-as-you-go, and a card on file is required. The good news:
this service is designed to be very cheap.

| What you pay for | Price (2026) | This service |
|---|---|---|
| Compute | shared-cpu-1x 256 MB ≈ **$2.19/month if running 24/7** | The machine **scales to zero** when idle (`auto_stop_machines = "stop"`, `min_machines_running = 0`) — billed per second only while it serves a download. Idle ≈ $0. |
| Egress (bandwidth) | **$0.02/GB** in Europe (Frankfurt region) | **This is the cost driver.** Every downloaded book counts: 10 GB ≈ $0.20, 50 GB ≈ $1.00, 100 GB ≈ $2.00. |
| IPv4 | $2/month for a dedicated IPv4 | Not needed — Fly.io gives a shared IPv4 + dedicated IPv6 by default. |

**Bottom line:** with scale-to-zero, a quiet catalog costs cents a month.
If downloads take off, the bill grows with egress ($0.02/GB in Europe) —
watch it in the Fly.io dashboard (billing) and set a spending alert there.
The per-IP rate limit (30 downloads/min, `PROXY_RATE_LIMIT_PER_MINUTE`)
caps how fast one client can burn bandwidth.

If the cost ever stops making sense, the fallback is simple: keep the
`tg://` links on the website (no proxy, no cost) — the proxy is an
improvement, not a dependency.

## 1. Install flyctl

```bash
# macOS
brew install flyctl
# or
curl -L https://fly.io/install.sh | sh
```

Then log in (opens the browser):

```bash
flyctl auth login
```

## 2. Create the app

From the `rlibook-download-proxy/` folder:

```bash
cd ~/rlibook-download-proxy
flyctl launch --no-deploy
```

- When it asks for an app name, keep `rlibook-download-proxy` (or pick
  your own — if you change it, update `app = "..."` in `fly.toml`).
- Region: choose `fra` (Frankfurt) when asked — closest to the readers.
- It will ask about a Postgres database / Redis — **say no to both**.
- `--no-deploy` creates the app without deploying yet (secrets first).

If `flyctl launch` tries to overwrite `fly.toml`, keep the one in this
folder (it already has the right settings).

## 3. Set the secrets

```bash
flyctl secrets set TELEGRAM_API_ID="<your api id>"
flyctl secrets set TELEGRAM_API_HASH="<your api hash>"
flyctl secrets set TELEGRAM_SESSION_STRING="<your session string>"
flyctl secrets set PROXY_SIGNING_KEY="$(openssl rand -hex 32)"
```

- `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION_STRING` are
  the same values the RliBook Telegram indexer already uses (GitHub
  Secrets). Reuse them — **never paste them in chat**.
- `PROXY_SIGNING_KEY` is a **new** random key for the download tokens.
  The command above generates one (`openssl rand -hex 32`). **Save it
  somewhere safe** — the website's token issuer (a later step) needs the
  exact same key, and Fly.io will not show it again.
- Optional tuning (only if you want to change the defaults):
  `flyctl secrets set PROXY_TOKEN_TTL_SECONDS=600 PROXY_RATE_LIMIT_PER_MINUTE=30`

## 4. Deploy

```bash
flyctl deploy
```

The first deploy builds the Docker image (a few minutes). When it finishes:

```bash
flyctl status
flyctl logs
```

## 5. Get the public URL

```bash
flyctl info
```

The URL looks like `https://rlibook-download-proxy.fly.dev`. Test it:

```bash
curl https://rlibook-download-proxy.fly.dev/health
# {"ok": true}
```

## 6. Test a real download

Make a token (using the **same** signing key you set in step 3):

```bash
export PROXY_SIGNING_KEY="<the key from step 3>"
python3 scripts/make_token.py --handle khazendar --post 12345 --format epub \
  --base-url https://rlibook-download-proxy.fly.dev
```

It prints the token and the full download URL. Open that URL in a browser
(or `curl -O "<url>"`) — the EPUB should download. Check the headers:

```bash
curl -sI "<download url>" | grep -i -E "content-type|content-disposition|content-length"
```

Expected: `content-type: application/epub+zip`,
`content-disposition: attachment; filename="....epub"`.

**First-request slowness is normal:** with scale-to-zero, the first
download after idle takes a few seconds (machine cold start + Telethon
connect). Later downloads in the same burst are fast.

## 7. After deploy — what to do

- **Stop the old Railway bot? No — this service is separate.** The bot
  stays as it is; this proxy only serves website downloads.
- **The website still needs the token issuer** (a Cloudflare Pages
  Function that holds `PROXY_SIGNING_KEY` and signs tokens for non-flagged
  books) before the "Download" button can point here. Until then, the site
  keeps its `tg://` links. That is the next step, not this deploy.
- **Watch the bill:** Fly.io dashboard → billing. Egress is the meter
  that matters ($0.02/GB in Europe).
- **Rotate the signing key** if it ever leaks: set a new
  `PROXY_SIGNING_KEY` secret on Fly.io **and** in the token issuer at the
  same time (old tokens stop working immediately).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `flyctl deploy` fails at build | Check the Docker build log (`flyctl logs`); make sure you are in the `rlibook-download-proxy/` folder. |
| `/health` returns 502 / app won't start | `flyctl logs` — usually a bad `fly.toml` or a missing secret. |
| `/dl` returns **503 "not configured"** | A secret is missing — `flyctl secrets list` (names only) and re-set the missing one. |
| `/dl` returns **403** | The token is missing, expired, or for a different book. Tokens live 10 min by default — make a fresh one. |
| `/dl` returns **404** | That post has no file in the requested format (or the post id is wrong). |
| `/dl` returns **502** | Telegram fetch failed — check `flyctl logs`; the session may need re-creating if Telegram revoked it. |
| First download is slow | Normal cold start (scale-to-zero). Nothing to fix. |
