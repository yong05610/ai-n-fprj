"""Pre-reviewed reference catalog (docs/phase2_prep.md Task 2.3, backend/data/rag_documents.json).

Phase 4's plan/generate only picks from this fixed, team-reviewed list by a
simple field/course substring match - it never asks the AI to invent sources.
Each entry's `category` is "<field> / <course>" (as the Phase 2 catalog defines
it); `chunks` is reserved for Phase 6's RAG index and unused here.
"""

import json
import os
import re
from functools import lru_cache


_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "rag_documents.json")

# Splits into Latin/digit runs and Korean-syllable runs, so "Python 개발" tokenizes to
# {"python", "개발"} and "JavaScript" to {"javascript"} - never a single run spanning both.
_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[가-힣]+")

# A field string shorter than this is too generic/short to mean anything on its own
# ("a", "AI") and produced false matches against unrelated catalog entries.
_MIN_MATCH_LENGTH = 3


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        return [doc for doc in json.load(f) if doc.get("verified")]


def _category_parts(doc: dict) -> tuple[str, str]:
    doc_field, _, doc_course = doc["category"].partition("/")
    return doc_field.strip().lower(), doc_course.strip().lower()


def _head_token(value: str) -> str | None:
    """The leading token of a field string - its domain-specific term.

    Every multi-word field in this catalog is authored as "<distinctive term>
    <generic suffix>" ("Python 개발", "웹 개발", "백엔드 개발", "데이터 분석"). Matching
    on *any* shared token let unrelated fields collide on the generic suffix
    alone (field="Python 개발" matching "웹 개발"/"백엔드 개발" docs just because
    they all share the word "개발"/"development"). The head token is the one
    that actually identifies the field.
    """
    tokens = _TOKEN_PATTERN.findall(value.strip().lower())
    return tokens[0] if tokens else None


def match_references(field: str, course: str) -> list[dict]:
    """Field match is mandatory - course text alone never matches across fields.

    Matching is by exact head-token equality, not substring containment: a
    plain substring check made "Java" match the "JavaScript" doc (and "UX
    디자인" match an "SQL 기초" doc via the shared word "기초"). "java" and
    "javascript" are different tokens even though one contains the other, so
    exact equality rejects it while "Python" == "Python 개발"'s head token
    "python" still matches.

    The catalog is small and unranked (10 entries, Task 2.3), so once a field
    matches, every doc under that field is returned; `course` isn't used to
    narrow further - a within-field narrowing pass can be added if the catalog
    grows enough to need it.
    """
    field_l = field.strip().lower()
    if len(field_l) < _MIN_MATCH_LENGTH:
        return []
    query_head = _head_token(field)
    if not query_head:
        return []

    matches = []
    for doc in load_catalog():
        doc_field, _ = _category_parts(doc)
        if query_head == _head_token(doc_field):
            matches.append(doc)
    return matches


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
