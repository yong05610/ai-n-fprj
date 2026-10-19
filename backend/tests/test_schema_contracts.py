import pytest
from pydantic import ValidationError

from schemas import (
    PathRecommendationRequest,
    LevelItem,
    CourseItem,
    PlanGenerateRequest,
    WeeklyTaskPlanItem,
    GoalCreateRequest,
    TaskCreateRequest,
    StudyLogCreateRequest,
    ReflectionCreateRequest,
)


class TestSchemaValidation:
    """QA Unit Tests for Phase 1 Pydantic DTO constraints."""

    def test_path_recommendation_request_valid(self):
        req = PathRecommendationRequest(field="Python 개발", user_context="비전공자 취준생")
        assert req.field == "Python 개발"
        assert req.user_context == "비전공자 취준생"

    def test_path_recommendation_request_empty_field_fails(self):
        with pytest.raises(ValidationError):
            PathRecommendationRequest(field="")

    def test_level_item_bounds(self):
        # Valid level 1 to 5
        lvl = LevelItem(level=1, name="입문자", description="기초 단계")
        assert lvl.level == 1

        lvl5 = LevelItem(level=5, name="전문가", description="고급 단계")
        assert lvl5.level == 5

        # Invalid level < 1
        with pytest.raises(ValidationError):
            LevelItem(level=0, name="오류", description="0레벨")

        # Invalid level > 5
        with pytest.raises(ValidationError):
            LevelItem(level=6, name="오류", description="6레벨")

    def test_plan_generate_request_validation(self):
        valid = PlanGenerateRequest(
            field="Python 개발",
            selected_courses=["기본문법", "자료구조"],
            current_level=1,
            target_level=4,
            weekly_hours=7,
            target_date="2026-11-30",
        )
        assert valid.current_level == 1
        assert valid.target_level == 4
        assert valid.weekly_hours == 7

        # Invalid: empty courses list
        with pytest.raises(ValidationError):
            PlanGenerateRequest(
                field="Python 개발",
                selected_courses=[],
                current_level=1,
                target_level=4,
                weekly_hours=7,
                target_date="2026-11-30",
            )

    def test_task_estimated_minutes_positive(self):
        item = WeeklyTaskPlanItem(
            title="조건문 연습",
            description="if문 실습",
            estimated_minutes=60,
            suggested_weekday="mon",
        )
        assert item.estimated_minutes == 60

        with pytest.raises(ValidationError):
            WeeklyTaskPlanItem(
                title="잘못된 과제",
                description="시간 음수",
                estimated_minutes=0,  # ge=1 required
            )

    def test_study_log_with_reflection(self):
        log = StudyLogCreateRequest(
            task_id="task_123",
            study_date="2026-10-19",
            minutes=45,
            activity="반복문 예제 풀이",
            reflection=ReflectionCreateRequest(
                content="for문과 while문의 차이를 이해했다.",
                tags=["반복문", "기초"],
            ),
        )
        assert log.minutes == 45
        assert log.reflection is not None
        assert log.reflection.content == "for문과 while문의 차이를 이해했다."
        assert "기초" in log.reflection.tags
