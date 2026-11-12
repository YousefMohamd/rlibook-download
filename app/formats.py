"""Book formats, MIME types, and safe download filenames."""
from __future__ import annotations

import re
import urllib.parse

# The only formats the catalog carries. The format IS the file extension.
FORMAT_MIME = {
    "epub": "application/epub+zip",
    "pdf": "application/pdf",
    "mobi": "application/x-mobipocket-ebook",
    "azw3": "application/vnd.amazon.ebook",
    "kfx": "application/octet-stream",  # no official MIME type for KFX
    "txt": "text/plain; charset=utf-8",
}

ALLOWED_FORMATS = frozenset(FORMAT_MIME)

# Reverse map: MIME type -> format (used when a Telegram document has no
# filename to read the extension from).
MIME_FORMAT = {
    "application/epub+zip": "epub",
    "application/pdf": "pdf",
    "application/x-mobipocket-ebook": "mobi",
    "application/vnd.amazon.ebook": "azw3",
    "text/plain": "txt",
}

MAX_FILENAME_LEN = 150

# Characters that must never appear in a download filename.
_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')


def mime_for(fmt: str) -> str | None:
    """MIME type for a format, or None for an unknown format."""
    return FORMAT_MIME.get((fmt or "").strip().lower())


def format_from_filename(filename: str | None) -> str | None:
    """Detect the format from a filename extension, or None."""
    if not filename or "." not in filename:
        return None
    ext = filename.rsplit(".", 1)[-1].strip().lower()
    return ext if ext in ALLOWED_FORMATS else None


def format_from_mime(mime_type: str | None) -> str | None:
    """Detect the format from a MIME type, or None."""
    if not mime_type:
        return None
    return MIME_FORMAT.get(mime_type.strip().lower().split(";")[0].strip())


def safe_filename(name: str | None, post_id: int, fmt: str) -> str:
    """Return a safe download filename for a book.

    - strips directories (path traversal), control chars and quote/backslash
    - collapses whitespace, strips leading/trailing dots and spaces
    - guarantees the file ends with .<fmt>
    - falls back to ``book-<post_id>.<fmt>`` when the name is unusable
    """
    fmt = (fmt or "").strip().lower()
    fallback = f"book-{int(post_id)}.{fmt}"
    if not name:
        return fallback
    # basename: drop any directory part (defeats "../" and "C:\\" tricks)
    name = name.replace("\\", "/").rsplit("/", 1)[-1]
    name = _BAD_FILENAME_CHARS.sub("", name)
    name = re.sub(r"\s+", " ", name).strip(" .")
    name = re.sub(r"\s+\.", ".", name)  # "name .epub" -> "name.epub"
    if not name:
        return fallback
    # ensure the right extension
    if "." in name:
        stem, ext = name.rsplit(".", 1)
        if ext.lower() == fmt:
            name = stem + "." + fmt
        else:
            name = name + "." + fmt
    else:
        name = name + "." + fmt
    if len(name) > MAX_FILENAME_LEN:
        stem, ext = name.rsplit(".", 1)
        name = stem[: MAX_FILENAME_LEN - len(ext) - 1].rstrip(" .") + "." + ext
    return name or fallback


def content_disposition(filename: str) -> str:
    """Content-Disposition header value for a download.

    ASCII names use the plain form; non-ASCII names (e.g. Arabic) also get
    the RFC 5987 filename* form so browsers save the real name.
    """
    ascii_name = re.sub(r'[^\x20-\x7e"]', "_", filename).replace('"', "'")
    if ascii_name == filename:
        return f'attachment; filename="{ascii_name}"'
    quoted = urllib.parse.quote(filename, safe="")
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{quoted}'
