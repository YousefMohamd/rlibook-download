"""RliBook download proxy — streams a book file from a Telegram channel post
to the browser on demand. The file is NEVER stored (streaming only).

Safety: every download needs a short-lived HMAC-signed token (see tokens.py).
The token is issued by the website for non-flagged (public-domain / CC) books
only. Without a valid token the proxy refuses (HTTP 403).
"""
