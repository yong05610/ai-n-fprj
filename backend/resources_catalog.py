"""Pre-reviewed reference catalog (docs/phase2_prep.md Task 2.3, backend/data/rag_documents.json).

Phase 4's plan/generate only picks from this fixed, team-reviewed list by a
simple field/course substring match - it never asks the AI to invent sources.
Each entry's `category` is "<field> / <course>" (as the Phase 2 catalog defines
it); `chunks` is reserved for Phase 6's RAG index and unused here.
"""

import json
import os
from functools import lru_cache


_CATALOG_PATH = os.path.join(os.path.dirname(__file__), "data", "rag_documents.json")


@lru_cache(maxsize=1)
def load_catalog() -> list[dict]:
    with open(_CATALOG_PATH, "r", encoding="utf-8") as f:
        return [doc for doc in json.load(f) if doc.get("verified")]


def _category_parts(doc: dict) -> tuple[str, str]:
    doc_field, _, doc_course = doc["category"].partition("/")
    return doc_field.strip().lower(), doc_course.strip().lower()


def match_references(field: str, course: str) -> list[dict]:
    field_l, course_l = field.strip().lower(), course.strip().lower()
    matches = []
    for doc in load_catalog():
        doc_field, doc_course = _category_parts(doc)
        field_hit = bool(field_l) and (field_l in doc_field or doc_field in field_l)
        course_hit = bool(course_l) and (course_l in doc_course or doc_course in course_l)
        if field_hit or course_hit:
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
