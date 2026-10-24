"""Pre-reviewed reference catalog (docs/phase2_prep.md Task 2.3, backend/data/rag_documents.json).

Phase 4's plan/generate only picks from this fixed, team-reviewed list by a
score-based field/course tag match - it never asks the AI to invent sources.
Each entry's `category` is "<field> / <course>" (as the Phase 2 catalog defines
it); `chunks` is reserved for Phase 6's RAG index and unused here.
"""

import json
import os
import re
from functools import lru_cache
from urllib.parse import quote


_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "rag_documents.json")

# Splits into Latin/digit runs and Korean-syllable runs, so "Python 개발" tokenizes to
# {"python", "개발"} and "JavaScript" to {"javascript"} - never a single run spanning both.
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[가-힣]+")

# A Latin field string shorter than this is too generic/short to mean anything on its own
# ("a", "AI") and produced false matches against unrelated catalog entries. Korean names
# ("영어", "웹") are short but specific, and matching is by whole token, so they are allowed.
_MIN_MATCH_LENGTH = 3


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        return [doc for doc in json.load(f) if doc.get("verified")]


def _category_parts(doc: dict) -> tuple[str, str]:
    doc_field, _, doc_course = doc["category"].partition("/")
    return doc_field.strip().lower(), doc_course.strip().lower()


# Generic words carry no topic: "개발" or "입문" alone must never connect two unrelated fields.
STOPWORDS = frozenset(
    {
        "개발", "개발자", "기초", "입문", "코딩", "학습", "공부", "과정", "기본", "초급", "강의",
        "development", "developer", "basic", "basics", "beginner", "coding", "study", "course", "learn",
    }
)
MAX_REFERENCES = 5
_PARTICLE_MAX = 2  # a Korean tag matches a longer input word only when at most this many characters follow it
# Josa that may follow a generic word ("개발의", "기초를"); such a token is still the generic word.
_STOPWORD_PARTICLES = ("의", "를", "을", "은", "는", "이", "가", "에", "로", "와", "과", "도", "에서", "으로")
# Two-letter Latin fields are blocked as too generic ("a", "go"), except these well-known terms,
# which only ever match as a whole token.
SHORT_LATIN_ALLOWED = frozenset({"ai", "ui", "ux", "db", "qa"})


def _is_stopword(token: str) -> bool:
    if token in STOPWORDS:
        return True
    return any(token == word + particle for word in STOPWORDS if not word.isascii() for particle in _STOPWORD_PARTICLES)


def _topic_tokens(text: str) -> set[str]:
    return {t for t in _TOKEN_PATTERN.findall(text.lower()) if not _is_stopword(t)}


def _token_matches(query: str, target: str) -> bool:
    """Exact equality; for Korean also "target + a short particle" ("영어를" ~ "영어").

    Latin tokens are never matched by prefix, so "java" never matches "javascript"; the Korean
    form follows the same rule ("자바" does not match "자바스크립트": four characters follow it).
    """
    if query == target:
        return True
    if not target.isascii() and len(target) >= 2 and query.startswith(target):
        return len(query) - len(target) <= _PARTICLE_MAX
    return False


def _count_hits(query_tokens: set[str], target_tokens: set[str]) -> int:
    return sum(1 for q in query_tokens if any(_token_matches(q, t) for t in target_tokens))


def _first_tag_hit(query_tokens: set[str], tags: list[str]) -> int:
    """Position of the first tag that matches the input (earlier tags are a document's main topics)."""
    for i, tag in enumerate(tags):
        if _count_hits(query_tokens, _topic_tokens(tag)):
            return i
    return len(tags)


def _rank(query_tokens: set[str], gate_tokens: set[str], require_tag: bool) -> list[tuple[int, int, str, dict]]:
    """Scored candidates: (score, first matching tag position, id, doc), best first."""
    ranked = []
    for doc in load_catalog():
        tags = doc.get("tags", [])
        tag_tokens = {t for tag in tags for t in _topic_tokens(tag)}
        category_tokens = _topic_tokens(doc["category"])
        if require_tag:
            if not _count_hits(gate_tokens, tag_tokens):
                continue
        elif not _count_hits(gate_tokens, tag_tokens | category_tokens):
            continue
        score = _count_hits(query_tokens, tag_tokens) + _count_hits(query_tokens, category_tokens)
        ranked.append((score, _first_tag_hit(query_tokens, tags), doc["id"], doc))
    ranked.sort(key=lambda r: (-r[0], r[1], r[2]))
    return ranked


def match_references(field: str, course: str) -> list[dict]:
    """Reviewed documents that fit a learning's field and course (precision over recall).

    1. A document is a candidate when at least one token of the *field* matches its tags or its
       category. Score = (input tokens, field and course together, equal to a token of its `tags`)
       + (input tokens equal to a token of its category "<field> / <course>"). Course text alone
       never pulls in a document while the field matches something.
    2. Only when the field matches nothing at all (free-text fields such as "VIBE CODING"), the
       *course* tokens are scored on their own - and a document then needs a domain term (a tag)
       to match exactly, so generic words never connect anything.
    Generic words are ignored, no substring matching is used, and the best MAX_REFERENCES documents
    (ties: earlier matching tag, then id) are returned. A Latin field shorter than _MIN_MATCH_LENGTH
    ("a", "go") is too generic to mean anything unless it is in SHORT_LATIN_ALLOWED ("AI", "UX").
    """
    stripped = field.strip().lower()
    field_blocked = len(stripped) < _MIN_MATCH_LENGTH and stripped.isascii() and stripped not in SHORT_LATIN_ALLOWED
    field_tokens = set() if field_blocked else _topic_tokens(field)
    course_tokens = _topic_tokens(course)

    ranked = _rank(field_tokens | course_tokens, field_tokens, require_tag=False) if field_tokens else []
    if not ranked and course_tokens:
        ranked = _rank(course_tokens, course_tokens, require_tag=True)
    return [doc for _, _, _, doc in ranked[:MAX_REFERENCES]]


SEARCH_QUERY_MAX_CHARS = 200
SEARCH_LINK_LABEL_SUFFIX = "(검토 전 외부 링크)"


def search_links(field: str, course: str, extra_terms: list[str] | None = None) -> list[dict]:
    """Search-engine links built only from the learning's own words and a fixed server template.

    Nothing here comes from AI output or from a client-sent URL; the query is percent-encoded, so
    spaces, `&`, `#` and quotes cannot break out of the `q` parameter. At most three links.
    """
    terms = [t.strip() for t in [course, field, *(extra_terms or [])] if t and t.strip()]
    query = " ".join(terms)[:SEARCH_QUERY_MAX_CHARS].strip()
    if not query:
        return []
    google = quote(query, safe="")
    docs_query = quote(f"{query} 공식 문서"[:SEARCH_QUERY_MAX_CHARS], safe="")
    youtube = quote(query, safe="")
    return [
        {"label": f"구글에서 검색 {SEARCH_LINK_LABEL_SUFFIX}", "url": f"https://www.google.com/search?q={google}"},
        {"label": f"공식 문서 검색 {SEARCH_LINK_LABEL_SUFFIX}", "url": f"https://www.google.com/search?q={docs_query}"},
        {"label": f"유튜브에서 검색 {SEARCH_LINK_LABEL_SUFFIX}", "url": f"https://www.youtube.com/results?search_query={youtube}"},
    ]


def no_match_notice(field: str) -> str:
    return (
        "이 분야와 관련된 사전 검토 자료를 찾지 못했습니다.\n\n"
        "아래 키워드로 직접 검색해 보시면 도움이 될 수 있습니다:\n"
        f'  · "{field} 입문 tutorial"\n'
        f'  · "{field} 공식 문서"\n'
        f'  · "{field} 한국어 강의"\n\n'
        "아래 계획은 등록 자료 없이 AI가 생성한 일반 계획입니다.\n"
        "정확성을 직접 확인해 주세요."
    )
