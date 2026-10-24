"""Read-only lexical retrieval over the team-written reference chunks (Phase 6, 6.1~6.3).

Data
- backend/data/rag_documents.json: reviewed document metadata (title, source, URL). Never written.
- backend/data/rag_chunks.json: short Korean summaries per document, joined to the metadata by
  doc_id. Only chunks with `verified: true` are searchable; the PM approves chunks in
  docs/phase6_chunk_review.md before the flag is flipped. RAG_CHUNKS_PATH overrides the file
  (tests and local checks use it; the production path is the default).

Retrieval rule (no embeddings, no external calls, user input is never written to the index)
- Tokens: Latin/digit runs and Korean-syllable runs, lowercased (same splitting as
  resources_catalog). A few generic question words are ignored (STOPWORDS).
- Two tokens match when they are equal, or when one starts with the other and the shorter is at
  least MIN_PREFIX_KO (Korean) / MIN_PREFIX_LATIN (Latin) characters long, so Korean particles
  ("리스트에서" ~ "리스트") and English plurals ("functions" ~ "function") still match.
- Score of a chunk = sum over the question's distinct tokens: +KEYWORD_WEIGHT (3) if the token
  matches one of the chunk's keyword tokens, otherwise +TEXT_WEIGHT (1) if it matches a token
  in the chunk text.
- A chunk is a hit when score >= SCORE_THRESHOLD (3): one keyword hit or three plain text hits.
  The top TOP_K (3) hits by score (ties: chunk id) are returned. Below the threshold the result
  is empty, which the caller must present as "not answered from the reviewed materials".
"""

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache

from resources_catalog import load_catalog

_DEFAULT_CHUNKS_PATH = os.path.join(os.path.dirname(__file__), "data", "rag_chunks.json")

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+|[가-힣]+")
_KOREAN = re.compile(r"^[가-힣]+$")

KEYWORD_WEIGHT = 3
TEXT_WEIGHT = 1
SCORE_THRESHOLD = 3
TOP_K = 3
MIN_PREFIX_KO = 2
MIN_PREFIX_LATIN = 4

# Question words that carry no topic; they would otherwise hit unrelated chunks.
STOPWORDS = frozenset(
    {
        "어떻게", "무엇", "뭐야", "뭔가요", "알려줘", "알려", "설명", "설명해줘", "해줘", "해주세요", "질문",
        "방법", "차이", "이란", "무슨", "어떤", "왜", "언제", "어디", "있나요", "인가요", "하나요", "해야",
        "the", "what", "how", "why", "and", "for", "is", "are", "to", "of", "in", "a", "an",
    }
)


@dataclass(frozen=True)
class RetrievedChunk:
    chunk_id: str
    doc_id: str
    text: str
    score: int
    title: str
    source_name: str
    url: str | None


def tokenize(text: str) -> list[str]:
    return _TOKEN_PATTERN.findall(text.lower())


def _tokens_match(question_token: str, chunk_token: str) -> bool:
    if question_token == chunk_token:
        return True
    shorter, longer = sorted((question_token, chunk_token), key=len)
    if not longer.startswith(shorter):
        return False
    minimum = MIN_PREFIX_KO if _KOREAN.match(shorter) else MIN_PREFIX_LATIN
    return len(shorter) >= minimum


def _any_match(question_token: str, tokens: frozenset[str]) -> bool:
    return any(_tokens_match(question_token, t) for t in tokens)


@dataclass(frozen=True)
class _IndexedChunk:
    chunk_id: str
    doc_id: str
    text: str
    text_tokens: frozenset[str]
    keyword_tokens: frozenset[str]
    title: str
    source_name: str
    url: str | None


def _chunks_path() -> str:
    return os.getenv("RAG_CHUNKS_PATH") or _DEFAULT_CHUNKS_PATH


@lru_cache(maxsize=4)
def _load_index(path: str, mtime: float) -> tuple[_IndexedChunk, ...]:
    """Read-only index of verified chunks whose document is in the reviewed catalog."""
    del mtime  # part of the cache key so an edited file is re-read
    docs = {d["id"]: d for d in load_catalog() if not d.get("link_only")}  # link-only docs are never evidence
    with open(path, "r", encoding="utf-8") as f:
        entries = json.load(f)
    indexed = []
    for entry in entries:
        doc = docs.get(entry.get("doc_id"))
        if doc is None:
            continue
        for chunk in entry.get("chunks", []):
            if chunk.get("verified") is not True:
                continue
            keyword_tokens = frozenset(t for k in chunk.get("keywords", []) for t in tokenize(k))
            indexed.append(
                _IndexedChunk(
                    chunk_id=chunk["id"],
                    doc_id=doc["id"],
                    text=chunk["text"],
                    text_tokens=frozenset(tokenize(chunk["text"])),
                    keyword_tokens=keyword_tokens,
                    title=doc["title"],
                    source_name=doc["source_name"],
                    url=doc.get("url"),
                )
            )
    return tuple(indexed)


def _index() -> tuple[_IndexedChunk, ...]:
    path = _chunks_path()
    try:
        return _load_index(path, os.path.getmtime(path))
    except FileNotFoundError:
        return ()


def topic_tokens(text: str) -> set[str]:
    """The topic-bearing tokens of a question: no stopwords, at least two characters."""
    return {t for t in tokenize(text) if t not in STOPWORDS and len(t) >= 2}


def overlaps(query_tokens: set[str], text: str) -> bool:
    """True when any question token matches a token of `text` (same matching rule as search)."""
    if not query_tokens:
        return False
    text_tokens = frozenset(tokenize(text))
    return any(_any_match(q, text_tokens) for q in query_tokens)


def search(question: str) -> list[RetrievedChunk]:
    """Top chunks for a question, or [] when nothing reaches the threshold."""
    query_tokens = topic_tokens(question)
    if not query_tokens:
        return []
    scored = []
    for chunk in _index():
        score = 0
        for q in query_tokens:
            if _any_match(q, chunk.keyword_tokens):
                score += KEYWORD_WEIGHT
            elif _any_match(q, chunk.text_tokens):
                score += TEXT_WEIGHT
        if score >= SCORE_THRESHOLD:
            scored.append((score, chunk))
    scored.sort(key=lambda pair: (-pair[0], pair[1].chunk_id))
    return [
        RetrievedChunk(c.chunk_id, c.doc_id, c.text, score, c.title, c.source_name, c.url)
        for score, c in scored[:TOP_K]
    ]
