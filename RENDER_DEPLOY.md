# Deploy guide — RliBook download proxy on Render (free, no card)

The proxy is the Block 2 service: it streams one book file from Telegram
to whoever holds a short-lived HMAC token, and nothing is stored on disk.
The website's send button (`/api/send-to-kindle?lib=tg`) fetches from it
and emails the book. **Render is the chosen host because it has a free
plan with no card.** The old Fly.io guide (`DEPLOY_GUIDE.md`) stays in
this folder as the fallback — Fly.io now needs a card.

## Cost — read this first

| Render free plan | This service |
|---|---|
| $0/month, no card | 750 free instance-hours/month — this service runs 24/7 inside that |
| Free instances **sleep after 15 minutes with no traffic** and wake on the next request | First download after idle takes a few seconds longer (wake + Telegram connect). Later downloads in the same burst are fast. |
| 100 GB/month free egress | Every downloaded book counts. A quiet catalog stays far under this. |
| No persistent disk | Not needed — the proxy stores nothing. |

If downloads ever outgrow the free plan, upgrade the same service to
Starter ($7/month) in the dashboard — no redeploy, no code change.

## What you need before you start (all USER steps)

1. A Render account (free): https://render.com — sign up with GitHub
   or email. No card is asked for on the free plan.
2. The proxy source in a Git repo Render can read. This folder
   (`rlibook-download-proxy-render/`) is the Render-ready copy of the
   verified `rlibook-download-proxy-v1.zip` (tests 62/62) plus
   `render.yaml` in this folder. Push it to GitHub first (any repo
   name, e.g. `rlibook-download-proxy`), or deploy from a local folder
   with the Render CLI — the dashboard Blueprint flow below assumes a
   GitHub repo.
3. Four secret values (never paste them in chat, never put them in a
   file — you type them into the Render dashboard only):
   - `TELEGRAM_API_ID` / `TELEGRAM_API_HASH` / `TELEGRAM_SESSION_STRING`
     — the SAME values the RliBook Telegram indexer already uses
     (GitHub Secrets). Reuse them.
   - `PROXY_SIGNING_KEY` — a NEW random key for the download tokens.
     Generate it with `openssl rand -hex 32` on your Mac. **Save it
     somewhere safe** — the website's token issuer (already built,
     `functions/api/dl-token.js`) and the send endpoint
     (`functions/api/send-to-kindle.js`) need the EXACT same key as a
     Pages secret (`PROXY_SIGNING_KEY`), and Render will not show it
     again after you save it.

## Deploy — exact steps

### Option A — Blueprint (recommended, one click after the repo exists)

1. Push this folder to GitHub.
2. Render dashboard → **New +** → **Blueprint** → connect the repo.
3. Render reads `render.yaml`, shows one Web Service
   (`rlibook-download-proxy`, Docker, free, Frankfurt, health check
   `/health`). Click **Apply**.
4. Render asks for the four secrets listed above (they are
   `sync: false` in `render.yaml`). Fill them in and save.
5. Render builds the Docker image (a few minutes on first deploy) and
   starts the service. Watch **Logs** until you see Uvicorn listening.

### Option B — manual Web Service (no Blueprint)

1. Render dashboard → **New +** → **Web Service** → **Build and deploy
   from a Git repository** → pick the repo.
2. Settings:
   - **Name:** `rlibook-download-proxy`
   - **Region:** Frankfurt
   - **Branch:** the branch you pushed (e.g. `main`)
   - **Root Directory:** the folder containing the `Dockerfile`
     (leave blank if the repo root IS this folder)
   - **Runtime:** Docker
   - **Dockerfile Path:** `./Dockerfile`
   - **Instance Type:** Free
3. **Environment variables** → add the four secrets above, plus:
   - `PROXY_TOKEN_TTL_SECONDS` = `600`
   - `PROXY_RATE_LIMIT_PER_MINUTE` = `30`
   (Render sets `PORT` itself — do not set it. The Dockerfile already
   listens on `${PORT:-8000}`.)
4. **Health Check Path:** `/health`
5. Click **Create Web Service**. First build takes a few minutes.

## After deploy — verify (USER steps)

1. Get the public URL from the dashboard — it looks like
   `https://rlibook-download-proxy.onrender.com`.
2. Health check (browser or terminal):
   `curl https://rlibook-download-proxy.onrender.com/health`
   Expected: `{"ok": true}`
3. Test a real download — make a token with the SAME signing key you
   set in Render:
   ```bash
   export PROXY_SIGNING_KEY="<the key from the deploy step>"
   python3 scripts/make_token.py --handle khazendar --post 12345 --format epub \
     --base-url https://rlibook-download-proxy.onrender.com
   ```
   It prints the token and the full download URL. Open that URL — the
   EPUB should download. Expected headers:
   `content-type: application/epub+zip`,
   `content-disposition: attachment; filename="....epub"`.
   (First request after idle is slow — the free instance was asleep.
   That is normal.)
4. **Tell Muse the public URL.** Muse then sets it as `PROXY_BASE_URL`
   in the Cloudflare Pages project (dashboard setting, not code) and
   sets the same `PROXY_SIGNING_KEY` as a Pages secret — that is what
   switches the website's Telegram send button from the honest
   "not configured" page to a real download. Nothing in the code needs
   to change for that step.

## Notes

- The Dockerfile is unchanged from the verified zip (Python 3.12-slim,
  `uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}`).
  It was verified by extracting the zip cleanly and running its test
  suite (62/62 pass). The image itself could NOT be built in this
  workspace (no Docker here) — the first Render build is the real
  build test; if it fails, the error is in Render's **Logs** tab.
- `fly.toml` in this folder is the old Fly.io config. It is inert on
  Render and kept only so the Fly fallback still works.
- Rotate the signing key if it ever leaks: set a new
  `PROXY_SIGNING_KEY` in Render AND in the Pages project at the same
  time (both sides must match, or downloads fail with 403).
