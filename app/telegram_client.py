"""Telegram fetching via Telethon (MTProto).

The fetcher connects lazily — only on the first download request — so the
service can start and answer /health without any Telegram credentials.

The Telegram session (TELEGRAM_API_ID / TELEGRAM_API_HASH /
TELEGRAM_SESSION_STRING) comes from environment variables only (Fly.io
secrets). It is never written to disk by this service: Telethon's
StringSession keeps the session in memory.

Streaming: the file is read from Telegram in chunks and yielded straight to
the HTTP response. Nothing is ever written to disk, and only one chunk is
held in memory at a time.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import AsyncIterator

from telethon.tl.types import DocumentAttributeFilename

from .formats import format_from_filename, format_from_mime


class TelegramConfigError(Exception):
    """Telegram credentials are missing or invalid."""


class TelegramFetchError(Exception):
    """Telegram answered, but the fetch failed (network, flood-wait, ...)."""


@dataclass
class DocumentInfo:
    """What the proxy needs to serve a file."""

    filename: str
    size: int | None
    mime_type: str | None
    document: object  # the Telethon Document — opaque to the app layer


class TelegramFetcher:
    """Wraps a Telethon client. One instance per process (created lazily)."""

    def __init__(self, api_id: str, api_hash: str, session_string: str):
        self._api_id = api_id
        self._api_hash = api_hash
        self._session_string = session_string
        self._client = None

    async def _client(self):
        if self._client is None:
            from telethon import TelegramClient
            from telethon.sessions import StringSession

            try:
                api_id = int(self._api_id)
            except (TypeError, ValueError):
                raise TelegramConfigError("TELEGRAM_API_ID is not a number")
            self._client = TelegramClient(
                StringSession(self._session_string), api_id, self._api_hash
            )
            await self._client.connect()
        return self._client

    async def close(self) -> None:
        if self._client is not None:
            try:
                await self._client.disconnect()
            finally:
                self._client = None

    @staticmethod
    def _document_format(doc, filename: str | None) -> str | None:
        """The book format of a Telegram document (extension first, then MIME)."""
        fmt = format_from_filename(filename)
        if fmt:
            return fmt
        return format_from_mime(getattr(doc, "mime_type", None))

    @staticmethod
    def _document_filename(doc) -> str | None:
        for attr in getattr(doc, "attributes", []) or []:
            if isinstance(attr, DocumentAttributeFilename):
                return attr.file_name
        return None

    async def get_document(
        self, handle: str, post_id: int, fmt: str
    ) -> DocumentInfo | None:
        """Find the document of format `fmt` on the given channel post.

        Returns None when the post does not exist, has no document, or has
        no document in the requested format.
        """
        client = await self._client()
        try:
            message = await client.get_messages(handle, ids=post_id)
        except Exception as exc:  # network / flood-wait / bad handle
            raise TelegramFetchError(str(exc)) from exc
        if message is None:
            return None
        doc = getattr(message, "document", None)
        if doc is None:
            return None
        filename = self._document_filename(doc)
        if self._document_format(doc, filename) != fmt:
            return None
        return DocumentInfo(
            filename=filename or f"book-{post_id}.{fmt}",
            size=getattr(doc, "size", None),
            mime_type=getattr(doc, "mime_type", None),
            document=doc,
        )

    async def iter_file(
        self, document: object, chunk_size: int = 65536
    ) -> AsyncIterator[bytes]:
        """Yield the file's bytes, chunk by chunk, straight from Telegram."""
        client = await self._client()
        async for chunk in client.iter_download(document, chunk_size=chunk_size):
            yield chunk
