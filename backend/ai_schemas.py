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
    levels: List[LevelItem] = Field(..., min_length=1, description="이 과정에 한정된 수준 체계")


class AIPathRecommendation(BaseModel):
    courses: List[AICourseItem] = Field(..., min_length=1, max_length=10)
    suggested_roles: List[str] = Field(default_factory=list, max_length=5)


class AIWeeklyTask(BaseModel):
    title: str = Field(..., min_length=1, max_length=200, description="학습 과업명")
    description: str = Field(..., min_length=1, max_length=2000, description="과업 세부 내용")
    estimated_minutes: int = Field(..., ge=1, le=6000, description="예상 학습 시간 (분)")
    suggested_weekday: Optional[Weekday] = Field("none", description="선택적 추천 요일")


class AIPlanDraft(BaseModel):
    tasks: List[AIWeeklyTask] = Field(..., min_length=1)
    advice_title: str = Field(..., min_length=1, max_length=200)
    advice_content: str = Field(..., min_length=1, max_length=4000)
