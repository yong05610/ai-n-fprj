"""Internal schemas the AI's JSON output must satisfy (Phase 4).

These are deliberately separate from schemas.py's public API DTOs: the AI never
invents IDs, slugs, or references - the server fills those in after parsing.
"""

from typing import List, Optional

from pydantic import BaseModel, Field

from schemas import LevelItem, Weekday


class AICourseItem(BaseModel):
    title: str = Field(..., max_length=100, description="세부 과정명")
    description: str = Field(..., max_length=2000, description="과정 개요")
    levels: List[LevelItem] = Field(..., min_length=2, description="이 과정에 한정된 수준 체계 (최소 2개)")


class AIPathRecommendation(BaseModel):
    courses: List[AICourseItem] = Field(..., min_length=1, max_length=10)
    suggested_roles: List[str] = Field(default_factory=list, max_length=5)


class AIRoleIdeas(BaseModel):
    suggested_roles: List[str] = Field(..., min_length=3, max_length=5)


class AIWeeklyTask(BaseModel):
    """One task of the whole-course plan. The weekday and the week are never the AI's: the server
    places the tasks on the timeline (schedule.py)."""

    title: str = Field(..., min_length=1, max_length=200, description="학습 과업명")
    description: str = Field(..., min_length=1, max_length=2000, description="과업 세부 내용")
    estimated_minutes: int = Field(..., ge=10, le=6000, description="예상 학습 시간 (분)")


class AIPlanDraft(BaseModel):
    # The 3~60 count is checked by main._validate_ai_plan so a violation reaches the model as feedback.
    tasks: List[AIWeeklyTask] = Field(..., min_length=1, max_length=200)
    advice_title: str = Field(..., min_length=1, max_length=200)
    advice_content: str = Field(..., min_length=1, max_length=4000)


class AITutorAnswer(BaseModel):
    """One structured tutor reply: relevance filter, answer and the reference ids it used.

    `used_source_ids` are doc ids taken from the `reference_chunks` the server sent; the server
    builds the visible source list (title, URL) itself and rejects ids it did not send.
    `search_keywords` are follow-up search words for an answer without sources (count, length and
    "no URL" are checked by tutor.validate_tutor_answer so a violation can be fed back to the model).
    """

    relevant: bool
    answer: str = ""
    used_source_ids: List[str] = Field(default_factory=list, max_length=10)
    search_keywords: List[str] = Field(default_factory=list, max_length=20)


class AIInsight(BaseModel):
    """One learning insight (Phase 6B): progress summary, repeated difficulty, next action.

    The server rejects empty required parts, over-long text and wording that treats a suggested
    weekday as a deadline (see main._validate_ai_insight); nothing is patched silently.
    """

    summary: str = Field(..., min_length=1, max_length=300)
    difficulty: str = Field("", max_length=300)
    next_action: str = Field(..., min_length=1, max_length=300)


class AIInsightBasic(BaseModel):
    """Insight asked for with fewer than two reflections: summary and next_action only.

    `difficulty` is never requested in this case. The field exists only so that a stray value
    from the model still reaches the server's safety net (main._validate_ai_insight rejects it)
    instead of being dropped silently; the stored difficulty is always "" for this schema.
    """

    summary: str = Field(..., min_length=1, max_length=300)
    next_action: str = Field(..., min_length=1, max_length=300)
    difficulty: str = Field("", max_length=300)
