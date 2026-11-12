# RliBook download proxy — Block 2

A small service that makes the website's **"Download" button download a book
file immediately in the browser — no Telegram, no bot.**

It fetches the file from the Telegram channel post (via the Telethon / MTProto
API) and **streams it straight to the browser**. The file is **never stored**:
nothing is written to disk, and only one chunk is held in memory at a time.

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET /health` | Liveness check → `{"ok": true}` (no credentials needed) |
| `GET /` | Service info + endpoint list |
| `GET /dl?h=<handle>&p=<post_id>&f=<format>&t=<token>` | Download one book file |
| `GET /dl/<handle>/<post_id>/<format>?t=<token>` | Same, path form |

The token can also be sent as `Authorization: Bearer <token>`.

Formats: `epub`, `pdf`, `mobi`, `azw3`, `kfx`, `txt` (the format IS the file
extension). A format button is only shown on the website when that format
actually exists for the book; the proxy also refuses (404) when the post has
no document in the requested format.

### Response

- **200** — the file, streamed. Headers: `Content-Type` (per format),
  `Content-Disposition: attachment; filename="..."` (with an RFC 5987
  `filename*` form for non-ASCII names, e.g. Arabic), `Content-Length`
  when Telegram reports the size.
- **400** — bad handle / post id / unknown format.
- **403** — missing, malformed, tampered, expired, or mismatched token.
  (One status for every token problem, so there is no oracle.)
- **404** — no book file in that format on that post.
- **429** — too many download requests from this IP (rate limit).
- **502** — Telegram fetch failed.
- **503** — proxy not configured (no signing key / no Telegram credentials).

## The token scheme (how the legal-only rule is enforced)

The proxy **only serves books the website has checked**. The check is a
short-lived HMAC-signed token:

```
token = "v1" "." payload_b64 "." signature_b64

payload = {"h": "<channel handle, lower-case, no @>",
           "p": <post id, int>,
           "f": "<format>",
           "exp": <unix expiry>}
payload_b64   = base64url(JSON(payload))           # sorted keys, no spaces
signature_b64 = base64url(HMAC-SHA256(signing_key, payload_b64))
```

Verification (in `app/tokens.py`):
1. shape is `v1.<b64>.<b64>`
2. signature matches (`hmac.compare_digest`)
3. payload decodes to a dict with `h` / `p` / `f` / `exp`
4. `h`, `p`, `f` match **exactly** the book being requested (a token cannot
   be reused for a different channel, post, or format)
5. `exp` is in the future

The signing key (`PROXY_SIGNING_KEY`) lives only in the environment — on the
proxy (Fly.io secret) and on the token issuer. It is never in the code, never
in the repo, never in the browser.

**The website issues a token only for a non-flagged book** (public-domain /
Creative Commons). A flagged / commercial book never gets a token, so the
proxy never serves it — it is refused with 403. The proxy itself does not
decide what is flagged; the token is the proof that the website already did.

### Token lifetime

Default **600 seconds (10 minutes)** — the website generates the token when
it renders the download button, and the user clicks within minutes. Change
with `PROXY_TOKEN_TTL_SECONDS`.

## Legal sources only — the rule this service enforces

- The catalog is **public-domain / Creative Commons books only**.
- **Flagged / commercial books are refused** (no token → 403).
- The proxy **never stores a book file** (streaming only, not hosting).
- The proxy never forwards or re-distributes files — it serves one file,
  to one browser, on one signed request.

## Environment variables

| Variable | Required | What it is |
|---|---|---|
| `PROXY_SIGNING_KEY` | yes | HMAC key for download tokens (long random string; generate with `openssl rand -hex 32`) |
| `TELEGRAM_API_ID` | yes | Telegram API id (my.telegram.org) |
| `TELEGRAM_API_HASH` | yes | Telegram API hash |
| `TELEGRAM_SESSION_STRING` | yes | Telethon session string (the RliBook indexer session) |
| `PROXY_TOKEN_TTL_SECONDS` | no | token lifetime, default 600 |
| `PROXY_CHUNK_SIZE` | no | stream chunk size in bytes, default 65536 |
| `PROXY_RATE_LIMIT_PER_MINUTE` | no | download requests per IP per minute, default 30 (0 = off) |
| `PORT` | no | listen port (Fly.io sets it), default 8000 |

Secrets are set with `fly secrets set ...` — never in the code, never in the
repo, never in chat.

## How the website will call it (later step — not in this service)

1. The website (Cloudflare Pages) needs a **token issuer**: a Pages Function
   (or small Worker) that holds `PROXY_SIGNING_KEY` and, for a book the
   index marks as non-flagged, returns a token for
   `(handle, post_id, format)` with a short TTL.
2. The download button's `href` becomes
   `https://<proxy>/dl?h=<handle>&p=<post_id>&f=<format>&t=<token>`.
3. The browser follows the link; the proxy verifies the token and streams
   the file. The old `tg://` links are then removed from the site.

The token issuer must check the book against the catalog's flag data before
issuing — the proxy trusts the token, so the issuer is the legal gate.

## Run locally

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
export PROXY_SIGNING_KEY="$(openssl rand -hex 32)"
uvicorn app.main:app --host 127.0.0.1 --port 8000
curl http://127.0.0.1:8000/health   # {"ok": true}
```

Make a test token (no Telegram needed for the token itself):

```bash
export PROXY_SIGNING_KEY="test-key"
python scripts/make_token.py --handle khazendar --post 12345 --format epub
```

A full download also needs the three `TELEGRAM_*` variables (real session).

## Tests

```bash
.venv/bin/python -m pytest tests/ -q
```

62 tests: token verification (valid / expired / tampered / wrong key /
mismatched book / malformed), format & MIME mapping, filename sanitisation,
rate limiter, and the endpoints with a mocked Telegram fetcher (no live
Telegram calls anywhere in the tests).

## Files

```
app/
  main.py            FastAPI app + /dl + /health
  tokens.py          HMAC token scheme (make / verify)
  formats.py         format -> MIME, safe filenames, Content-Disposition
  telegram_client.py Telethon fetcher (lazy connect, chunked streaming)
  ratelimit.py       per-IP request limiter (bandwidth protection)
  settings.py        env-var config
scripts/make_token.py  test token generator (CLI)
tests/               pytest suite (62 tests, all mocked)
Dockerfile  fly.toml  requirements.txt  requirements-dev.txt
README.md  DEPLOY_GUIDE.md
```
