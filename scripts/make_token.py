#!/usr/bin/env python3
"""Generate a signed download token for testing the RliBook download proxy.

The token proves the website checked the book and found it NOT flagged
(public-domain / Creative Commons). In production the website generates the
token (a Cloudflare Pages Function / Worker holding PROXY_SIGNING_KEY);
this script is only for local testing.

Usage:
    python scripts/make_token.py --handle khazendar --post 12345 --format epub
    python scripts/make_token.py --handle khazendar --post 12345 --format pdf --ttl 60 --base-url https://rlibook-download-proxy.fly.dev

The signing key is read from --key or the PROXY_SIGNING_KEY environment
variable. Never paste a real key into chat or commit it anywhere.
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.tokens import DEFAULT_TTL_SECONDS, make_token  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Make a signed RliBook download token.")
    parser.add_argument("--key", default=os.environ.get("PROXY_SIGNING_KEY"),
                        help="signing key (or PROXY_SIGNING_KEY env var)")
    parser.add_argument("--handle", required=True, help="channel handle, e.g. khazendar")
    parser.add_argument("--post", type=int, required=True, help="post id in the channel")
    parser.add_argument("--format", required=True,
                        help="format: epub, pdf, mobi, azw3, kfx, txt")
    parser.add_argument("--ttl", type=int, default=DEFAULT_TTL_SECONDS,
                        help=f"token lifetime in seconds (default {DEFAULT_TTL_SECONDS})")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000",
                        help="proxy base URL, for the full download link")
    args = parser.parse_args()

    if not args.key:
        parser.error("no signing key: pass --key or set PROXY_SIGNING_KEY")

    token = make_token(args.key, args.handle, args.post, args.format, args.ttl)
    print(token)
    print()
    print(f"{args.base_url}/dl?h={args.handle}&p={args.post}&f={args.format}&t={token}")


if __name__ == "__main__":
    main()
