"""Collectors of candidate reference links (Phase 8B step C, design 3-2).

A collector only produces `CandidateLink`s (an address and a short note). It cannot reach the link
check, the metadata reader, the AI suggestion, the storage, the approval or the reading path: those
are common steps in resource_pipeline that every collector's links pass through unchanged. Adding
a collector means writing a `Collector` subclass and calling `register`; nothing else is edited.

Settings (read on every call, so a change of the environment needs no code change):
  COLLECTORS_ENABLED            comma separated collector types; empty (default) = all off
  COLLECTOR_DAILY_CANDIDATES    candidates one collector may create per Asia/Seoul day (default 20)
  COLLECTOR_AI_TOPIC_DAILY_RUNS ai_topic runs per day (default 5)
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any, Optional

from ai_client import AIClient, AIRetryFeedback
from ai_schemas import AITopicLinks
from page_metadata import clean_text
from prompts import RESOURCE_TOPIC_SYSTEM_PROMPT
from resource_urls import allowed_domains

DEFAULT_DAILY_CANDIDATES = 20
DEFAULT_AI_TOPIC_DAILY_RUNS = 5
NOTE_MAX_CHARS = 100
TOPIC_COUNT_MIN, TOPIC_COUNT_MAX = 1, 5
TOPIC_FIELD_MAX, TOPIC_COURSE_MAX = 40, 60


@dataclass(frozen=True)
class CandidateLink:
    """The only thing a collector may return."""

    url: str
    note: str = ""


@dataclass(frozen=True)
class CollectorContext:
    """What a collector may use: the AI client and the (read-only) allowed domain names."""

    ai: Optional[AIClient]
    allowed_domains: tuple[str, ...]


class CollectorError(Exception):
    """A collector failed or broke its contract; the message is a fixed phrase, never page content."""


class Collector(ABC):
    type: str
    label: str
    # True when the collector is run from /collect with a field, a course and a count (ai_topic).
    # A collector that needs something else (direct_link needs an address) has its own endpoint.
    takes_topic: bool = False

    @abstractmethod
    def collect(self, params: dict[str, Any], ctx: CollectorContext) -> list[CandidateLink]:
        """Candidate links for `params`. Must not store, check or approve anything."""


class DirectLinkCollector(Collector):
    type = "direct_link"
    label = "링크 직접 입력"

    def collect(self, params: dict[str, Any], ctx: CollectorContext) -> list[CandidateLink]:
        return [CandidateLink(url=str(params.get("url") or ""), note=clean_text(str(params.get("note") or ""), NOTE_MAX_CHARS))]


class AITopicCollector(Collector):
    """Asks the AI (one call) for links inside the allowed domain list. The addresses are only
    suggestions: they may not exist or may be outside the list, and the common link check decides."""

    type = "ai_topic"
    label = "AI 주제 제안"
    takes_topic = True

    def collect(self, params: dict[str, Any], ctx: CollectorContext) -> list[CandidateLink]:
        if ctx.ai is None:
            raise CollectorError("AI 클라이언트가 없습니다.")
        count = int(params["count"])
        payload = {
            "field": str(params["field"]),
            "course": str(params["course"]),
            "count": count,
            "allowed_domains": list(ctx.allowed_domains),
        }

        def validate(result: AITopicLinks) -> None:
            if len(result.links) > count:
                raise AIRetryFeedback(
                    "links over count", {"validation_feedback": f"links 는 {count}개 이하여야 합니다."}, reason="too_many_links"
                )

        result = ctx.ai.generate(RESOURCE_TOPIC_SYSTEM_PROMPT, payload, AITopicLinks, validate)
        return [CandidateLink(url=link.url, note=clean_text(link.note, NOTE_MAX_CHARS)) for link in result.links]


# --- registry and settings ------------------------------------------------------------------

_REGISTRY: dict[str, Collector] = {}


def register(collector: Collector) -> Collector:
    _REGISTRY[collector.type] = collector
    return collector


def unregister(collector_type: str) -> None:
    _REGISTRY.pop(collector_type, None)


def get_collector(collector_type: str) -> Optional[Collector]:
    return _REGISTRY.get(collector_type)


def registered_types() -> list[str]:
    return list(_REGISTRY)


def enabled_types() -> frozenset[str]:
    return frozenset(p.strip() for p in os.getenv("COLLECTORS_ENABLED", "").split(",") if p.strip())


def is_enabled(collector_type: str) -> bool:
    return collector_type in enabled_types() and collector_type in _REGISTRY


def _int_setting(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default
    return value if value >= 0 else default


def daily_candidate_limit() -> int:
    return _int_setting("COLLECTOR_DAILY_CANDIDATES", DEFAULT_DAILY_CANDIDATES)


def ai_topic_daily_runs() -> int:
    return _int_setting("COLLECTOR_AI_TOPIC_DAILY_RUNS", DEFAULT_AI_TOPIC_DAILY_RUNS)


def context(ai: Optional[AIClient]) -> CollectorContext:
    return CollectorContext(ai=ai, allowed_domains=tuple(allowed_domains()))


register(DirectLinkCollector())
register(AITopicCollector())
