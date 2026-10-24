"""Pure helpers for the AI tutor (Phase 6): fixed texts, title rule, answer validation, sources.

Nothing here logs or stores user text. The endpoints live in main.py.
"""

import re
from typing import Iterable

from ai_client import AIRetryFeedback
from ai_schemas import AITutorAnswer
from rag import RetrievedChunk
from resources_catalog import match_references, search_links

DEFAULT_TITLE = "새 대화"
TITLE_MAX_CHARS = 30
HISTORY_LIMIT = 10  # previous messages sent as context
MAX_MESSAGES_PER_CONVERSATION = 200
CONVERSATION_LIST_LIMIT = 50
ANSWER_MIN_CHARS = 1
ANSWER_MAX_CHARS = 2000
KEYWORDS_MAX_COUNT = 3
KEYWORD_MIN_CHARS = 1
KEYWORD_MAX_CHARS = 30
RELATED_LINKS_LIMIT = 2
_URL_MARKERS = ("http", "://", "www.")

# Fixed text stored instead of whatever the model wrote when the question is not about learning.
REFUSAL_TEXT = (
    "학습과 관련된 질문에만 답할 수 있어요. 진행 중인 학습이나 학습 방법·요령에 관한 질문으로 다시 물어봐 주세요. "
    "학습과 관련 있는 질문인데 답하지 못했다면, 어떤 학습이나 주제에 관한 질문인지 덧붙여서 다시 질문해 주세요."
)

# Appended by the server (not the model) when no reviewed material backs the answer.
NO_SOURCE_NOTE = "※ 참고한 등록 자료가 없어요. 일반적인 학습 조언이에요."


def make_title(question: str) -> str:
    """Title of a conversation = the first 30 characters of its first question."""
    collapsed = re.sub(r"\s+", " ", question).strip()
    return collapsed[:TITLE_MAX_CHARS] or DEFAULT_TITLE

def validate_tutor_answer(parsed: AITutorAnswer, retrieved: Iterable[RetrievedChunk]) -> None:
    """Server-side rules for the model output; a violation is rejected and retried, never patched."""
    if not parsed.relevant:
        return  # the answer text is discarded and replaced by REFUSAL_TEXT
    allowed = {c.doc_id for c in retrieved}
    answer = parsed.answer.strip()
    problem = None
    if not (ANSWER_MIN_CHARS <= len(answer) <= ANSWER_MAX_CHARS):
        problem = f"answer 는 {ANSWER_MIN_CHARS}~{ANSWER_MAX_CHARS}자여야 합니다."
    elif any(sid not in allowed for sid in parsed.used_source_ids):
        problem = "used_source_ids 에는 reference_chunks 로 전달된 source_id 만 쓸 수 있습니다. reference_chunks 가 비어 있으면 빈 목록이어야 합니다."
    else:
        problem = _keyword_problem(parsed.search_keywords)
    if problem:
        raise AIRetryFeedback(problem, feedback={"validation_error": problem})


def _keyword_problem(keywords: Iterable[str]) -> str | None:
    keywords = list(keywords)
    if len(keywords) > KEYWORDS_MAX_COUNT:
        return f"search_keywords 는 최대 {KEYWORDS_MAX_COUNT}개여야 합니다."
    for keyword in keywords:
        text = keyword.strip()
        if not (KEYWORD_MIN_CHARS <= len(text) <= KEYWORD_MAX_CHARS):
            return f"search_keywords 의 각 항목은 {KEYWORD_MIN_CHARS}~{KEYWORD_MAX_CHARS}자여야 합니다."
        if any(marker in text.lower() for marker in _URL_MARKERS):
            return "search_keywords 에는 URL 이나 주소를 쓸 수 없습니다. 검색어만 적습니다."
    return None


def keywords_for(parsed: AITutorAnswer, has_sources: bool) -> list[str]:
    """Follow-up keywords to keep: only for a relevant answer that has no source (deduplicated)."""
    if not parsed.relevant or has_sources:
        return []
    keywords: list[str] = []
    for keyword in parsed.search_keywords:
        text = re.sub(r"\s+", " ", keyword).strip()
        if text and text.lower() not in (k.lower() for k in keywords):
            keywords.append(text)
    return keywords


def keywords_line(keywords: list[str]) -> str:
    return f"더 찾아볼 키워드: {', '.join(keywords)}"


def related_links_for(field: str | None, course: str | None, sources: Iterable[dict]) -> list[dict]:
    """Reviewed link materials matching the current learning (at most 2, not already a source)."""
    if not field:
        return []
    used = {s["doc_id"] for s in sources}
    links = [
        {"title": d["title"], "source_name": d.get("source_name"), "url": d["url"]}
        for d in match_references(field, course or "")
        if d["id"] not in used and d.get("url")
    ]
    return links[:RELATED_LINKS_LIMIT]


def decorate(message: dict, field: str | None, course: str | None) -> dict:
    """A copy of an assistant message with the links the server builds at response time.

    Stored: `search_keywords` only. Built here (never stored): `search_links` from the stored
    keywords and `related_links` for an answer that has sources.
    """
    out = {**message, "search_keywords": list(message.get("search_keywords", []))}
    out["search_links"], out["related_links"] = [], []
    if message.get("role") != "assistant" or message.get("refused"):
        return out
    if out["search_keywords"]:
        out["search_links"] = search_links(field or "", "", out["search_keywords"])
    elif message.get("sources"):
        out["related_links"] = related_links_for(field, course, message["sources"])
    return out


def sources_for(used_ids: Iterable[str], retrieved: Iterable[RetrievedChunk]) -> list[dict]:
    """The visible source list, built from the server's own search result (never from model text)."""
    by_doc: dict[str, RetrievedChunk] = {}
    for chunk in retrieved:
        by_doc.setdefault(chunk.doc_id, chunk)
    sources, seen = [], set()
    for sid in used_ids:
        chunk = by_doc.get(sid)
        if chunk is None or sid in seen:
            continue
        seen.add(sid)
        sources.append(
            {"doc_id": chunk.doc_id, "title": chunk.title, "source_name": chunk.source_name, "url": chunk.url}
        )
    return sources
