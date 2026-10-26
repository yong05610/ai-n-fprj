"""Title and description of a web page, and nothing else (Phase 8B, design 3-4).

Only `<title>`, `meta name=description`, `og:title` and `og:description` are read, from the first
bytes of the page. The page body is never kept. The result is plain text: markup that appears in
a title is stored as the characters it is made of and is never executed or converted; the admin
screen shows it through React's escaping.
"""

import codecs
import html
import re
import unicodedata
from dataclasses import dataclass
from html.parser import HTMLParser

TITLE_MAX_CHARS = 200
DESCRIPTION_MAX_CHARS = 500

_TITLE = re.compile(r"<title\b[^>]*>(.*?)(?:</title\s*>|\Z)", re.IGNORECASE | re.DOTALL)
_META_CHARSET = re.compile(rb"""<meta[^>]+charset\s*=\s*["']?\s*([A-Za-z0-9_\-:.]+)""", re.IGNORECASE)
_HEADER_CHARSET = re.compile(r"charset\s*=\s*[\"']?\s*([A-Za-z0-9_\-:.]+)", re.IGNORECASE)
_SNIFF_BYTES = 4096


@dataclass(frozen=True)
class PageMetadata:
    title: str
    description: str


def clean_text(value: str, limit: int) -> str:
    """Control and invisible-format characters removed, whitespace collapsed, cut to `limit`."""
    chars = []
    for ch in value:
        category = unicodedata.category(ch)
        if category in ("Zl", "Zp") or ch in "\t\r\n":
            chars.append(" ")
        elif category in ("Cc", "Cf", "Cs", "Co", "Cn"):
            continue  # controls, bidi overrides, zero-width marks, unassigned: nothing to show
        else:
            chars.append(ch)
    return " ".join("".join(chars).split())[:limit].strip()


def _charset(content_type: str, body: bytes) -> str:
    candidates = []
    match = _HEADER_CHARSET.search(content_type or "")
    if match:
        candidates.append(match.group(1))
    meta = _META_CHARSET.search(body[:_SNIFF_BYTES])
    if meta:
        candidates.append(meta.group(1).decode("ascii", "ignore"))
    for name in candidates + ["utf-8"]:
        try:
            return codecs.lookup(name).name
        except LookupError:
            continue
    return "utf-8"


class _MetaParser(HTMLParser):
    """Collects the first description / og values from `<meta>` tags before the body starts."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self._done = False

    def handle_starttag(self, tag, attrs):
        if self._done:
            return
        if tag == "body":
            self._done = True
            return
        if tag != "meta":
            return
        attributes = {k.lower(): (v or "") for k, v in attrs}
        key = (attributes.get("name") or attributes.get("property") or "").strip().lower()
        if key in ("description", "og:title", "og:description") and key not in self.values:
            self.values[key] = attributes.get("content", "")


def extract_metadata(body: bytes, content_type: str = "") -> PageMetadata:
    """Title (`<title>`, else og:title) and description (meta description, else og:description)."""
    text = body.decode(_charset(content_type, body), errors="replace")
    parser = _MetaParser()
    try:
        parser.feed(text)
        parser.close()
    except Exception:  # a broken page yields less metadata, never an error
        pass
    title_match = _TITLE.search(text)
    raw_title = html.unescape(title_match.group(1)) if title_match else ""  # <title> holds text, not tags
    title = clean_text(raw_title, TITLE_MAX_CHARS) or clean_text(parser.values.get("og:title", ""), TITLE_MAX_CHARS)
    description = clean_text(parser.values.get("description", ""), DESCRIPTION_MAX_CHARS) or clean_text(
        parser.values.get("og:description", ""), DESCRIPTION_MAX_CHARS
    )
    return PageMetadata(title=title, description=description)

