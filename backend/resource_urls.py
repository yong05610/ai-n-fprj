"""URL helpers shared by the catalog reader and the link checker (Phase 8B).

`normalize_url` is the identity of a reference link: two links that differ only by case of the
host, a fragment, tracking parameters or a trailing slash are the same resource.
`allowed_domains` is the team-reviewed host list (backend/data/allowed_domains.json); a host is
allowed only on an exact match, so subdomains and look-alike hosts are never admitted.
"""

import json
import os
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit

_ALLOWED_DOMAINS_PATH = os.path.join(os.path.dirname(__file__), "data", "allowed_domains.json")

_TRACKING_PARAMS = frozenset({"fbclid", "gclid", "dclid", "msclkid", "mc_cid", "mc_eid", "igshid", "yclid", "ref_src"})


def is_tracking_param(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith("utm_") or lowered in _TRACKING_PARAMS


def normalize_url(url: str) -> str:
    """Lower-case scheme and host, no fragment, no tracking parameters, no trailing '/'.

    Never raises: text that is not a URL comes back stripped and lower-cased, so two such
    values still compare equal only when they are really the same text.
    """
    text = (url or "").strip()
    try:
        parts = urlsplit(text)
    except ValueError:
        return text.lower()
    if not parts.scheme or not parts.netloc:
        return text.lower()
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not is_tracking_param(k)])
    path = parts.path.rstrip("/")
    return f"{parts.scheme.lower()}://{parts.netloc.lower()}{path}" + (f"?{query}" if query else "")


@lru_cache(maxsize=1)
def allowed_domains() -> dict[str, str]:
    """host -> source_name, in file order."""
    with open(_ALLOWED_DOMAINS_PATH, "r", encoding="utf-8") as f:
        return {entry["domain"].strip().lower(): entry["source_name"] for entry in json.load(f)}
