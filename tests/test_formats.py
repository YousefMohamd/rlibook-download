"""Format / MIME / filename tests."""
from __future__ import annotations

import pytest

from app.formats import (
    ALLOWED_FORMATS,
    content_disposition,
    format_from_filename,
    format_from_mime,
    mime_for,
    safe_filename,
)


def test_all_formats_have_mime():
    assert ALLOWED_FORMATS == {"epub", "pdf", "mobi", "azw3", "kfx", "txt"}
    assert mime_for("epub") == "application/epub+zip"
    assert mime_for("pdf") == "application/pdf"
    assert mime_for("mobi") == "application/x-mobipocket-ebook"
    assert mime_for("azw3") == "application/vnd.amazon.ebook"
    assert mime_for("kfx") == "application/octet-stream"
    assert mime_for("txt") == "text/plain; charset=utf-8"


def test_mime_unknown_and_case():
    assert mime_for("docx") is None
    assert mime_for("") is None
    assert mime_for("EPUB") == "application/epub+zip"


def test_format_from_filename():
    assert format_from_filename("book.epub") == "epub"
    assert format_from_filename("BOOK.PDF") == "pdf"
    assert format_from_filename("no-extension") is None
    assert format_from_filename("book.docx") is None
    assert format_from_filename(None) is None


def test_format_from_mime():
    assert format_from_mime("application/pdf") == "pdf"
    assert format_from_mime("application/epub+zip") == "epub"
    assert format_from_mime("text/plain; charset=utf-8") == "txt"
    assert format_from_mime("application/octet-stream") is None
    assert format_from_mime(None) is None


@pytest.mark.parametrize(
    "name,post_id,fmt,expected",
    [
        ("My Book.epub", 1, "epub", "My Book.epub"),
        ("My Book - Author.epub", 42, "epub", "My Book - Author.epub"),
        ("../../etc/passwd.epub", 1, "epub", "passwd.epub"),
        ("..\\..\\secret.pdf", 2, "pdf", "secret.pdf"),
        ("a/b/c/book.mobi", 3, "mobi", "book.mobi"),
        ('we"ird.epub', 1, "epub", "weird.epub"),
        ("with:colon.epub", 1, "epub", "withcolon.epub"),
        ("  spaced  name  .epub", 1, "epub", "spaced name.epub"),
        ("book.pdf", 5, "epub", "book.pdf.epub"),  # wrong ext kept, right one added
        ("book", 6, "txt", "book.txt"),  # missing ext added
        ("", 7, "epub", "book-7.epub"),  # empty -> fallback
        (None, 8, "pdf", "book-8.pdf"),  # None -> fallback
        ("...", 9, "epub", "book-9.epub"),  # only dots -> fallback
    ],
)
def test_safe_filename(name, post_id, fmt, expected):
    assert safe_filename(name, post_id, fmt) == expected


def test_safe_filename_long_name_truncated():
    name = "A" * 300 + ".epub"
    out = safe_filename(name, 1, "epub")
    assert out.endswith(".epub")
    assert len(out) <= 150
    assert "/" not in out and "\\" not in out


def test_content_disposition_ascii():
    assert content_disposition("My Book.epub") == 'attachment; filename="My Book.epub"'


def test_content_disposition_arabic():
    header = content_disposition("القراءة المثمرة.epub")
    assert "filename*=UTF-8''" in header
    assert "%D8%A7" in header  # percent-encoded Arabic
    assert 'filename="' in header  # ASCII fallback present too


def test_content_disposition_no_path_chars():
    header = content_disposition("book.epub")
    assert "/" not in header.split("filename=", 1)[1].replace("UTF-8''", "")
