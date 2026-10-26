"""The steps every candidate link goes through, whichever collector produced it (Phase 8B step C).

collector -> link check -> metadata -> AI suggestion -> stored candidate (pending | auto-rejected)
admin     -> approve (a `learning_documents` entry) | reject

Rules kept here:
- Nothing a collector returns skips a step; a duplicate is dropped before any outside access.
- The AI only proposes labels. It cannot approve, reject or change a status: the schema has no such
  field and an unknown key is refused. A suggestion that breaks a rule is rejected and retried;
  after the last attempt the candidate stays `pending` without a suggestion (the admin fills it in).
- Page text is data. It reaches the AI only inside the JSON payload, next to a system prompt that
  says it is not an instruction, and it is logged nowhere (counts and codes only).
- Approval writes one document under an id derived from the candidate id, so a repeated or retried
  approval writes the same document again instead of a second one.
"""

import hashlib
import logging
import re
import statistics
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import clock
import link_checker
import resource_collectors
import resource_store
import resources_catalog
from ai_client import AIClient, AIRetryFeedback, AISchemaError, AITimeoutError, AIUnavailableError
from ai_schemas import AIResourceSuggestion
from page_metadata import clean_text
from prompts import RESOURCE_SUGGEST_SYSTEM_PROMPT
from resource_collectors import CandidateLink, CollectorError
from resource_urls import allowed_domains, normalize_url

logger = logging.getLogger("pacemate.resources")

TAG_MIN, TAG_MAX, TAG_MAX_CHARS = 3, 8, 20
TITLE_MAX, FIELD_MAX, COURSE_MAX, LEVEL_MAX, SUMMARY_MAX = 200, 40, 60, 30, 120
REJECT_REASON_MAX = 200
URL_TEXT_MAX = 2048

_MARKUP_OR_URL = re.compile(r"://|www\.|[<>]|\]\(", re.IGNORECASE)
_LEVEL_SCORE_WORDS = ("점수", "등급", "score", "point")


class CollectionRefused(Exception):
    """A collection that is not run: kind is "unknown", "disabled" or "limit"."""

    def __init__(self, kind: str, details: Optional[dict] = None) -> None:
        super().__init__(kind)
        self.kind = kind
        self.details = details or {}


class ResourceEditError(ValueError):
    def __init__(self, field_name: str, message: str) -> None:
        super().__init__(message)
        self.field = field_name


@dataclass
class CollectionOutcome:
    candidates: list[dict[str, Any]] = field(default_factory=list)
    duplicates: int = 0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


# --- limits ---------------------------------------------------------------------------------

def usage(collector_type: str, db=None) -> dict[str, Optional[int]]:
    today = clock.today()
    info: dict[str, Optional[int]] = {
        "daily_limit": resource_collectors.daily_candidate_limit(),
        "used_today": resource_store.count_candidates_created_on(today, collector_type, db),
        "daily_run_limit": None,
        "runs_today": None,
    }
    if collector_type == "ai_topic":
        info["daily_run_limit"] = resource_collectors.ai_topic_daily_runs()
        info["runs_today"] = resource_store.count_runs_created_on(today, collector_type, db)
    return info


def precheck(collector_type: str, requested: int, db=None) -> resource_collectors.Collector:
    """The collector to run, or CollectionRefused. Nothing outside is touched before this passes."""
    collector = resource_collectors.get_collector(collector_type)
    if collector is None:
        raise CollectionRefused("unknown")
    if not resource_collectors.is_enabled(collector_type):
        raise CollectionRefused("disabled")
    info = usage(collector_type, db)
    if info["used_today"] + requested > info["daily_limit"]:
        raise CollectionRefused("limit", {"limit": info["daily_limit"], "used_today": info["used_today"]})
    if info["daily_run_limit"] is not None and info["runs_today"] >= info["daily_run_limit"]:
        raise CollectionRefused("limit", {"run_limit": info["daily_run_limit"], "runs_today": info["runs_today"]})
    return collector


# --- AI suggestion --------------------------------------------------------------------------

def _has_markup_or_url(text: str) -> bool:
    return bool(_MARKUP_OR_URL.search(text))


def _same_text(a: str, b: str) -> bool:
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def _feedback(reason: str, message: str) -> AIRetryFeedback:
    return AIRetryFeedback(reason, {"validation_feedback": message}, reason=reason)


def validate_suggestion(suggestion: AIResourceSuggestion, admin_field: str = "", admin_course: str = "") -> None:
    """Rules the server enforces on the AI's proposal; a violation is rejected, never patched."""
    if "/" in suggestion.field or "/" in suggestion.course:
        # the document category is "field / course" and is split at the first "/"
        raise _feedback("slash_in_field_or_course", "field 와 course 에는 '/' 를 쓰지 마세요.")
    texts = [suggestion.field, suggestion.course, suggestion.level_label, suggestion.summary, *suggestion.tags]
    if any(_has_markup_or_url(t) for t in texts):
        raise _feedback("url_or_markup", "어떤 값에도 URL 이나 HTML 태그를 쓰지 마세요.")
    if admin_field.strip() and not _same_text(suggestion.field, admin_field):
        raise _feedback("admin_field_changed", "field 는 admin_field 값을 그대로 써야 합니다.")
    if admin_course.strip() and not _same_text(suggestion.course, admin_course):
        raise _feedback("admin_course_changed", "course 는 admin_course 값을 그대로 써야 합니다.")
    label = suggestion.level_label.strip()
    if not label or any(ch.isdigit() for ch in label) or any(w in label.lower() for w in _LEVEL_SCORE_WORDS):
        raise _feedback("level_label", "level_label 은 숫자·점수·등급 표현 없이 서술형으로 쓰세요.")
    tags = [t.strip() for t in suggestion.tags]
    if any(not t or len(t) > TAG_MAX_CHARS for t in tags) or len({t.lower() for t in tags}) != len(tags):
        raise _feedback("tags", "tags 는 비어 있지 않고 20자 이하이며 서로 달라야 합니다.")
    if not suggestion.field.strip() or not suggestion.course.strip() or not suggestion.summary.strip():
        raise _feedback("empty", "field, course, summary 는 비어 있으면 안 됩니다.")


def _log_reject(error: Exception, attempt: int) -> None:
    category = error.reason if isinstance(error, AIRetryFeedback) else type(error).__name__
    logger.info("resource suggestion attempt rejected (attempt=%d, category=%s)", attempt, category)


def suggest(
    ai: Optional[AIClient], domain: str, title: str, description: str, admin_field: str, admin_course: str
) -> tuple[Optional[dict[str, Any]], str]:
    """(suggestion or None, "ok" | "failed" | "skipped"). The AI sees these five values and nothing else."""
    if ai is None:
        return None, "skipped"
    payload = {
        "domain": domain,
        "title": title,
        "description": description,
        "admin_field": admin_field,
        "admin_course": admin_course,
    }
    try:
        result = ai.generate(
            RESOURCE_SUGGEST_SYSTEM_PROMPT,
            payload,
            AIResourceSuggestion,
            lambda s: validate_suggestion(s, admin_field, admin_course),
            on_reject=_log_reject,
        )
    except (AIUnavailableError, AITimeoutError, AISchemaError):
        logger.info("resource suggestion failed (the candidate stays pending without one)")
        return None, "failed"
    return {
        "field": result.field.strip(),
        "course": result.course.strip(),
        "level_label": result.level_label.strip(),
        "tags": [t.strip() for t in result.tags],
        "summary": result.summary.strip(),
        "is_learning_resource": result.is_learning_resource,
    }, "ok"


# --- collecting -----------------------------------------------------------------------------

def _new_candidate(link: CandidateLink, collector_type: str, run_id: str, admin_field: str, admin_course: str, request_id: Optional[str], now: str) -> dict[str, Any]:
    return {
        "url": clean_text(link.url, URL_TEXT_MAX),
        "source_domain": "",
        "collector_type": collector_type,
        "collector_run_id": run_id,
        "collector_note": link.note,
        "title": "",
        "description": "",
        "ai_suggestion": None,
        "ai_status": "none",
        "check_results": {},
        "status": "pending",
        "reviewed_by": None,
        "reviewed_at": None,
        "reject_reason": None,
        "approved_document_id": None,
        "admin_field": admin_field,
        "admin_course": admin_course,
        "client_request_id": request_id,
        "created_at": now,
        "updated_at": now,
    }


def process_link(
    db,
    ai: Optional[AIClient],
    link: CandidateLink,
    collector_type: str,
    run_id: str,
    admin_field: str = "",
    admin_course: str = "",
    request_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """One link through the common steps. Returns the stored candidate, or None for a duplicate
    (a duplicate is reported to the caller and not stored)."""
    result = link_checker.check_link(link.url, resolver=link_checker.resolve_host, fetcher=link_checker.fetch_head)
    if result.code == link_checker.DUPLICATE:
        return None
    now = now_iso()
    candidate = _new_candidate(link, collector_type, run_id, admin_field, admin_course, request_id, now)
    candidate["check_results"] = dict(result.checks)
    candidate["source_domain"] = result.domain or ""
    if result.link:
        candidate["url"] = result.link
    if not result.ok:
        candidate.update(status="rejected", reviewed_by="system", reviewed_at=now, reject_reason=f"auto:{result.code}")
        return resource_store.create_candidate(candidate, db)
    candidate["title"] = result.metadata.title
    candidate["description"] = result.metadata.description
    candidate["ai_suggestion"], candidate["ai_status"] = suggest(
        ai, result.domain, result.metadata.title, result.metadata.description, admin_field, admin_course
    )
    return resource_store.create_candidate(candidate, db)


def run_collection(
    db,
    ai: Optional[AIClient],
    collector_type: str,
    params: dict[str, Any],
    admin_field: str = "",
    admin_course: str = "",
    request_id: Optional[str] = None,
    requested: int = 1,
) -> CollectionOutcome:
    """Refusal checks, the collector, then every returned link through `process_link`."""
    collector = precheck(collector_type, requested, db)
    links = collector.collect(params, resource_collectors.context(ai))
    if not isinstance(links, list) or not all(isinstance(item, CandidateLink) for item in links):
        raise CollectorError("수집기는 CandidateLink 목록만 돌려줄 수 있습니다.")
    run_id = uuid.uuid4().hex
    outcome = CollectionOutcome()
    seen: set[str] = set()
    for link in links[:requested]:
        identity = normalize_url(link.url)
        if identity in seen:  # the same address twice in one run
            outcome.duplicates += 1
            continue
        seen.add(identity)
        candidate = process_link(db, ai, link, collector_type, run_id, admin_field, admin_course, request_id)
        if candidate is None:
            outcome.duplicates += 1
        else:
            outcome.candidates.append(candidate)
    logger.info(
        "collection finished (collector=%s, links=%d, stored=%d, duplicates=%d)",
        collector_type, len(links), len(outcome.candidates), outcome.duplicates,
    )
    return outcome


# --- approval and rejection -----------------------------------------------------------------

def _clean_edit(name: str, value: Any, limit: int, required: bool = True, allow_slash: bool = True) -> str:
    if not isinstance(value, str):
        raise ResourceEditError(name, f"{name} 값이 올바르지 않습니다.")
    text = " ".join(value.split())
    if required and not text:
        raise ResourceEditError(name, f"{name} 은(는) 비어 있으면 안 됩니다.")
    if len(text) > limit:
        raise ResourceEditError(name, f"{name} 은(는) {limit}자 이하여야 합니다.")
    if _has_markup_or_url(text):
        raise ResourceEditError(name, f"{name} 에는 URL 이나 HTML 태그를 쓸 수 없습니다.")
    if not allow_slash and "/" in text:
        raise ResourceEditError(name, f"{name} 에는 '/' 를 쓸 수 없습니다. (분야 / 과정 표기를 나누는 글자입니다)")
    return text


def _clean_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ResourceEditError("tags", "tags 값이 올바르지 않습니다.")
    tags = [_clean_edit("tags", tag, TAG_MAX_CHARS) for tag in value]
    if not TAG_MIN <= len(tags) <= TAG_MAX:
        raise ResourceEditError("tags", f"tags 는 {TAG_MIN}개 이상 {TAG_MAX}개 이하여야 합니다.")
    if len({t.lower() for t in tags}) != len(tags):
        raise ResourceEditError("tags", "tags 에 같은 값이 있습니다.")
    return tags


def build_document_fields(candidate: dict[str, Any], edits: Optional[dict[str, Any]]) -> dict[str, Any]:
    """The reviewed values: an edit wins over the AI suggestion, which wins over the admin's own hint
    (field, course) or the page metadata (title). Anything missing or invalid is a ResourceEditError."""
    edits = edits or {}
    suggestion = candidate.get("ai_suggestion") or {}
    defaults = {
        "title": candidate.get("title", ""),
        "field": suggestion.get("field") or candidate.get("admin_field", ""),
        "course": suggestion.get("course") or candidate.get("admin_course", ""),
        "level_label": suggestion.get("level_label", ""),
        "tags": suggestion.get("tags", []),
        "summary": suggestion.get("summary", ""),
    }
    values = {**defaults, **{k: v for k, v in edits.items() if v is not None}}
    return {
        "title": _clean_edit("title", values["title"], TITLE_MAX),
        "field": _clean_edit("field", values["field"], FIELD_MAX, allow_slash=False),
        "course": _clean_edit("course", values["course"], COURSE_MAX, allow_slash=False),
        "level_label": _clean_edit("level_label", values["level_label"], LEVEL_MAX, required=False),
        "tags": _clean_tags(values["tags"]),
        "summary": _clean_edit("summary", values["summary"], SUMMARY_MAX, required=False),
    }


def document_id_for(candidate: dict[str, Any], db=None) -> str:
    """The same candidate always gets the same document id (a repeated approval overwrites its own
    document). In the very unlikely case that the id belongs to a different link, the next slice of
    the digest is used."""
    digest = hashlib.sha256(candidate["id"].encode("utf-8")).hexdigest()
    for start in range(0, len(digest) - 7, 8):
        doc_id = f"{resource_store.DOCUMENT_ID_PREFIX}{digest[start:start + 8]}"
        existing = resource_store.get_document(doc_id, db)
        if existing is None or normalize_url(existing.get("url", "")) == normalize_url(candidate["url"]):
            return doc_id
    raise RuntimeError("no free document id")


def approve_candidate(db, candidate: dict[str, Any], edits: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Write the approved document, then mark the candidate approved.

    The two writes are not one transaction (the store interface has none). The order makes a failure
    between them safe to retry: the document id is derived from the candidate id, so approving again
    writes the same document (never a second one), and only after the document exists is the candidate
    marked approved. If the second write fails the candidate is still `pending`, the document is an
    entry the admin did approve, and the retry completes the pair."""
    fields = build_document_fields(candidate, edits)
    now = now_iso()
    doc_id = document_id_for(candidate, db)
    domains = allowed_domains()
    resource_store.create_document(
        {
            "id": doc_id,
            "title": fields["title"],
            "category": f"{fields['field']} / {fields['course']}",
            "source_name": domains.get(candidate["source_domain"], candidate["source_domain"]),
            "url": candidate["url"],
            "tags": fields["tags"],
            "summary": fields["summary"],
            "level_label": fields["level_label"],
            "license": "링크만 제공",
            "link_only": True,
            "verified": True,
            "chunks": [],
            "verified_at": clock.today().isoformat(),
            "approved_by": "admin",
            "approved_at": now,
        },
        db,
    )
    updated = resource_store.update_candidate(
        candidate["id"],
        {"status": "approved", "reviewed_by": "admin", "reviewed_at": now, "approved_document_id": doc_id, "updated_at": now},
        db,
    )
    resources_catalog.invalidate_approved_cache()
    return updated


def clean_reject_reason(value: Optional[str]) -> str:
    text = " ".join((value or "").split())
    if not text:
        raise ResourceEditError("reject_reason", "반려 사유를 입력해 주세요.")
    if len(text) > REJECT_REASON_MAX:
        raise ResourceEditError("reject_reason", f"반려 사유는 {REJECT_REASON_MAX}자 이하여야 합니다.")
    return text


def reject_candidate(db, candidate: dict[str, Any], reason: str) -> dict[str, Any]:
    now = now_iso()
    return resource_store.update_candidate(
        candidate["id"],
        {"status": "rejected", "reviewed_by": "admin", "reviewed_at": now, "reject_reason": reason, "updated_at": now},
        db,
    )


# --- statistics -----------------------------------------------------------------------------

def _seconds_between(start: str, end: str) -> Optional[float]:
    try:
        return (datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds()
    except (ValueError, AttributeError):
        return None


def _tally(rows: list[dict[str, Any]]) -> dict[str, Any]:
    approved = [c for c in rows if c["status"] == "approved"]
    admin_rejected = [c for c in rows if c["status"] == "rejected" and c.get("reviewed_by") == "admin"]
    auto_rejected = [c for c in rows if c["status"] == "rejected" and c.get("reviewed_by") == "system"]
    reasons: dict[str, int] = {}
    for c in auto_rejected:
        code = str(c.get("reject_reason") or "auto:unknown").removeprefix("auto:")
        reasons[code] = reasons.get(code, 0) + 1
    waits = [w for w in (_seconds_between(c.get("created_at", ""), c.get("reviewed_at", "")) for c in approved) if w is not None]
    decided = len(approved) + len(admin_rejected) + len(auto_rejected)
    reviewed = len(approved) + len(admin_rejected)
    return {
        "total": len(rows),
        "pending": sum(1 for c in rows if c["status"] == "pending"),
        "approved": len(approved),
        "rejected_by_admin": len(admin_rejected),
        "auto_rejected": len(auto_rejected),
        "auto_rejected_reasons": dict(sorted(reasons.items())),
        "approval_rate": round(len(approved) / decided, 3) if decided else None,
        "reviewed_approval_rate": round(len(approved) / reviewed, 3) if reviewed else None,
        "median_seconds_to_approve": round(statistics.median(waits), 1) if waits else None,
    }


def collect_stats(db=None) -> dict[str, Any]:
    rows = resource_store.list_candidates(db=db)
    types = list(resource_collectors.registered_types())
    types += sorted({c["collector_type"] for c in rows} - set(types))
    per_collector = []
    for collector_type in types:
        collector = resource_collectors.get_collector(collector_type)
        entry = _tally([c for c in rows if c["collector_type"] == collector_type])
        per_collector.append({"collector_type": collector_type, "label": collector.label if collector else collector_type, **entry})
    return {"overall": _tally(rows), "collectors": per_collector}
