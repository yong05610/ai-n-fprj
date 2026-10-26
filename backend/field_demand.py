"""Demand per learning field for the admin screen (Phase 8B step E; off by default).

Computed on every request from the goals, stored nowhere, logged nowhere. A field is reported only
when at least `FIELD_STATS_MIN_USERS` different users have a learning in it (default 3, never
below 2), so no single learner can be picked out of the numbers. The answer holds the field name,
a user count and a count of linked reference documents - no UID, no goal content, no free text.
"""

import os
from collections import Counter
from typing import Any, Callable

DEFAULT_MIN_USERS = 3
MIN_USERS_FLOOR = 2
_TRUE_VALUES = frozenset({"true", "1", "yes", "on"})


def enabled() -> bool:
    """FIELD_STATS_ENABLED, read on every call. Anything but a true value (default) means off."""
    return os.getenv("FIELD_STATS_ENABLED", "").strip().lower() in _TRUE_VALUES


def min_users() -> int:
    try:
        value = int(os.getenv("FIELD_STATS_MIN_USERS", "").strip() or DEFAULT_MIN_USERS)
    except ValueError:
        return DEFAULT_MIN_USERS
    return max(MIN_USERS_FLOOR, value)


def normalize_field(value: Any) -> str:
    """Lower case, trimmed, runs of whitespace collapsed: "Python  개발 " and "python 개발" are one field."""
    return " ".join(str(value or "").lower().split())


def compute(goals: list[dict[str, Any]], match_count: Callable[[str], int], minimum: int) -> list[dict[str, Any]]:
    """One pass over `goals` (every user's goals read in a single query). `match_count(field)` is the number
    of reference documents the plan screen would link for that field."""
    users: dict[str, set[str]] = {}
    spellings: dict[str, Counter] = {}
    for goal in goals:
        key = normalize_field(goal.get("field"))
        user = goal.get("user_id")
        if not key or not user:
            continue
        users.setdefault(key, set()).add(user)
        spellings.setdefault(key, Counter())[" ".join(str(goal["field"]).split())] += 1
    rows = []
    for key, who in users.items():
        if len(who) < minimum:
            continue  # too few people: the field is left out of the answer altogether
        shown = sorted(spellings[key].items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        rows.append({"field": shown, "user_count": len(who), "linked_document_count": match_count(shown)})
    rows.sort(key=lambda r: (-r["user_count"], r["field"].lower()))
    return rows
