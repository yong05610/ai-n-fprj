"""Server-side number rules for AI learning insights (Phase 6B fix).

The model must not add up or convert times itself. The server computes every total and label,
sends them in the payload, and afterwards checks that each time or count the model wrote in its
text is one of the values the server provided; anything else is rejected and retried.

What is checked (regular expressions below, ASCII digits only):
- durations: "N시간 M분" (= N*60+M minutes), "N시간" (= N*60), "N분" - each becomes a number of minutes
- counts: "N건", "N회", "N번" (not the ordinal "N번째")
What is not checked: dates and weekdays ("10월 23일", "3일 동안"), and numbers written as Korean
words ("세 시간"); those are out of scope for this rule.

Allowed minute values: the window total, this week's minutes, the weekly target, each single
record's minutes (and 0). Allowed counts: the number of records in the window, the number of
reflections used, completed and total tasks, and the number of records per task.
"""

import re
from dataclasses import dataclass, field

# "1시간 53분" first (so its "53분" is not read again on its own), then "2시간", then "45분".
_DURATION = re.compile(r"(\d+)\s*시간(?:\s*(\d+)\s*분)?|(\d+)\s*분")
_COUNT = re.compile(r"(\d+)\s*(건|회|번)(?!째)")


def format_minutes(minutes: int) -> str:
    """The one display rule for durations: 0 -> "0분", 59 -> "59분", 60 -> "1시간",
    61 -> "1시간 1분", 113 -> "1시간 53분", 120 -> "2시간"."""
    if minutes < 60:
        return f"{minutes}분"
    hours, rest = divmod(minutes, 60)
    return f"{hours}시간" if rest == 0 else f"{hours}시간 {rest}분"


@dataclass(frozen=True)
class QuantityFacts:
    minutes: frozenset[int] = field(default_factory=frozenset)
    counts: frozenset[int] = field(default_factory=frozenset)


def build_facts(
    record_minutes: list[int],
    record_count_by_task: list[int],
    window_total_minutes: int,
    this_week_minutes: int,
    weekly_target_minutes: int,
    window_record_count: int,
    reflection_count: int,
    completed_tasks: int,
    total_tasks: int,
) -> QuantityFacts:
    return QuantityFacts(
        minutes=frozenset({0, window_total_minutes, this_week_minutes, weekly_target_minutes, *record_minutes}),
        counts=frozenset(
            {window_record_count, reflection_count, completed_tasks, total_tasks, *record_count_by_task}
        ),
    )


def find_unsupported_quantities(texts: list[str], facts: QuantityFacts) -> list[str]:
    """The time and count expressions in `texts` that the server did not provide (as written)."""
    unsupported: list[str] = []
    for text in texts:
        for match in _DURATION.finditer(text):
            if match.group(3) is not None:
                minutes = int(match.group(3))
            else:
                minutes = int(match.group(1)) * 60 + (int(match.group(2)) if match.group(2) else 0)
            if minutes not in facts.minutes:
                unsupported.append(match.group(0).strip())
        for match in _COUNT.finditer(text):
            if int(match.group(1)) not in facts.counts:
                unsupported.append(match.group(0).strip())
    return unsupported
