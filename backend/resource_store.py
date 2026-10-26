"""Storage of reference-material candidates and approved documents (Phase 8B, FR-08).

Two collections, neither carries a user id:
- `resource_candidates`: links waiting for review (or rejected). Never readable by clients and
  never merged into anything a learner sees.
- `learning_documents`: approved material only. Firestore rules let everyone read this collection,
  so a candidate must never be written to it: `create_document` accepts only a finished, approved
  document and refuses anything else.

All functions go through `store.get_store()`, so they work on the memory and the Firestore store.
"""

import uuid
from datetime import date
from typing import Any, Optional

import clock
from resource_urls import normalize_url
from store import get_store

CANDIDATES_COLLECTION = "resource_candidates"
DOCUMENTS_COLLECTION = "learning_documents"

CANDIDATE_STATUSES = ("pending", "approved", "rejected")
DOCUMENT_ID_PREFIX = "doc_a_"  # the file catalog uses doc_NNN, so the two never collide

_DOCUMENT_REQUIRED = ("id", "title", "category", "source_name", "url", "tags", "verified", "link_only", "approved_by", "approved_at")


def new_document_id() -> str:
    return f"{DOCUMENT_ID_PREFIX}{uuid.uuid4().hex[:8]}"


# --- candidates -----------------------------------------------------------------------------

def create_candidate(data: dict[str, Any], db=None) -> dict[str, Any]:
    if "user_id" in data:
        raise ValueError("a resource candidate never carries a user id")
    if data.get("status") not in CANDIDATE_STATUSES:
        raise ValueError("a resource candidate needs a known status")
    return (db or get_store()).create(CANDIDATES_COLLECTION, data)


def get_candidate(candidate_id: str, db=None) -> Optional[dict[str, Any]]:
    return (db or get_store()).get(CANDIDATES_COLLECTION, candidate_id)


def update_candidate(candidate_id: str, changes: dict[str, Any], db=None) -> Optional[dict[str, Any]]:
    """The updated candidate, or None when it does not exist."""
    db = db or get_store()
    if db.get(CANDIDATES_COLLECTION, candidate_id) is None:
        return None
    if "user_id" in changes:
        raise ValueError("a resource candidate never carries a user id")
    if "status" in changes and changes["status"] not in CANDIDATE_STATUSES:
        raise ValueError("a resource candidate needs a known status")
    return db.update(CANDIDATES_COLLECTION, candidate_id, changes)


def list_candidates(status: Optional[str] = None, collector_type: Optional[str] = None, db=None) -> list[dict[str, Any]]:
    """Newest first (ties: id), optionally by status and collector."""
    filters = {k: v for k, v in (("status", status), ("collector_type", collector_type)) if v}
    rows = (db or get_store()).find(CANDIDATES_COLLECTION, **filters)
    return sorted(rows, key=lambda c: (c.get("created_at", ""), c["id"]), reverse=True)


def find_candidate_by_request_id(client_request_id: str, db=None) -> Optional[dict[str, Any]]:
    rows = (db or get_store()).find(CANDIDATES_COLLECTION, client_request_id=client_request_id)
    return rows[0] if rows else None


def find_live_candidate_by_url(url: str, db=None) -> Optional[dict[str, Any]]:
    """A pending or approved candidate with the same normalized URL (rejected ones do not count)."""
    wanted = normalize_url(url)
    for candidate in (db or get_store()).find(CANDIDATES_COLLECTION):
        if candidate.get("status") != "rejected" and normalize_url(candidate.get("url", "")) == wanted:
            return candidate
    return None


def count_candidates_created_on(day: date, collector_type: Optional[str] = None, db=None) -> int:
    """Candidates created on a Asia/Seoul calendar day. Auto-rejected ones count too: the daily
    limit protects cost and load, and a rejected link already cost a check."""
    filters = {"collector_type": collector_type} if collector_type else {}
    rows = (db or get_store()).find(CANDIDATES_COLLECTION, **filters)
    return sum(1 for c in rows if c.get("created_at") and clock.date_from_utc_iso(c["created_at"]) == day)


# --- approved documents ---------------------------------------------------------------------

def create_document(doc: dict[str, Any], db=None) -> dict[str, Any]:
    """Write one approved, link-only document under its own id (writing the same id again replaces it)."""
    missing = [key for key in _DOCUMENT_REQUIRED if key not in doc]
    if missing:
        raise ValueError(f"an approved document is missing: {', '.join(missing)}")
    if doc["verified"] is not True or doc["link_only"] is not True or doc["approved_by"] != "admin":
        raise ValueError("only an approved, link-only document may be written to learning_documents")
    if not str(doc["id"]).startswith(DOCUMENT_ID_PREFIX):
        raise ValueError("an approved document id must start with its own prefix")
    if not str(doc["url"]).startswith("https://"):
        raise ValueError("an approved document needs an https url")
    data = {k: v for k, v in doc.items() if k != "id"}
    return (db or get_store()).set(DOCUMENTS_COLLECTION, doc["id"], data)


def get_document(doc_id: str, db=None) -> Optional[dict[str, Any]]:
    return (db or get_store()).get(DOCUMENTS_COLLECTION, doc_id)


def list_approved_documents(db=None) -> list[dict[str, Any]]:
    return (db or get_store()).find(DOCUMENTS_COLLECTION, verified=True)
