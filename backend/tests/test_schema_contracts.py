import pytest
from pydantic import ValidationError

from schemas import (
    PathRecommendationRequest,
    PathRecommendationResponse,
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

    def test_path_recommendation_request_blank_field_fails(self):
        with pytest.raises(ValidationError):
            PathRecommendationRequest(field="   ")

    def test_path_recommendation_request_accepts_goal(self):
        req = PathRecommendationRequest(field="Python 개발", goal="백엔드 신입 취업")
        assert req.goal == "백엔드 신입 취업"

    def test_level_item_bounds(self):
        # Valid order 1 to 20
        lvl = LevelItem(order=1, name="입문자", description="기초 단계")
        assert lvl.order == 1

        lvl_top = LevelItem(order=20, name="전문가", description="고급 단계")
        assert lvl_top.order == 20

        # Invalid order < 1
        with pytest.raises(ValidationError):
            LevelItem(order=0, name="오류", description="0단계")

        # Invalid order > 20
        with pytest.raises(ValidationError):
            LevelItem(order=21, name="오류", description="21단계")

    def test_course_item_carries_its_own_levels(self):
        course = CourseItem(
            id="basic-syntax",
            title="기본문법",
            description="변수와 제어문",
            levels=[
                LevelItem(order=1, name="입문자", description="문법을 처음 접함"),
                LevelItem(order=2, name="실무 기초", description="간단한 스크립트 작성 가능"),
            ],
        )
        assert len(course.levels) == 2

        # A course must carry at least one level (no shared/global level table).
        with pytest.raises(ValidationError):
            CourseItem(id="empty", title="빈 과정", description="설명", levels=[])

    def test_path_recommendation_response_is_scoped_per_course(self):
        response = PathRecommendationResponse(
            field="Python 개발",
            courses=[
                CourseItem(
                    id="basic-syntax",
                    title="기본문법",
                    description="변수와 제어문",
                    levels=[LevelItem(order=1, name="입문자", description="기초 단계")],
                )
            ],
            suggested_roles=["백엔드 개발자", "데이터 엔지니어"],
        )
        assert response.courses[0].levels[0].name == "입문자"
        assert len(response.suggested_roles) == 2

    def test_plan_generate_request_validation(self):
        valid = PlanGenerateRequest(
            goal_id="goal_123",
            field="Python 개발",
            course="기본문법",
            current_level_order=1,
            target_level_order=4,
            weekly_hours=7,
            target_date="2026-11-30",
        )
        assert valid.current_level_order == 1
        assert valid.target_level_order == 4
        assert valid.weekly_hours == 7

        # Invalid: missing goal_id
        with pytest.raises(ValidationError):
            PlanGenerateRequest(
                goal_id="",
                field="Python 개발",
                course="기본문법",
                current_level_order=1,
                target_level_order=4,
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
        assert not hasattr(item, "week_number")

        with pytest.raises(ValidationError):
            WeeklyTaskPlanItem(
                title="잘못된 과제",
                description="시간 음수",
                estimated_minutes=0,  # ge=1 required
            )

        with pytest.raises(ValidationError):
            WeeklyTaskPlanItem(
                title="잘못된 요일",
                description="요일 리터럴 위반",
                estimated_minutes=30,
                suggested_weekday="monday",
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
        assert log.started_at is None
        assert log.ended_at is None

    def test_study_log_accepts_optional_timer_timestamps(self):
        log = StudyLogCreateRequest(
            task_id="task_123",
            study_date="2026-10-19",
            minutes=30,
            activity="타이머로 기록",
            started_at="2026-10-19T09:00:00Z",
            ended_at="2026-10-19T09:30:00Z",
        )
        assert log.started_at == "2026-10-19T09:00:00Z"
        assert log.ended_at == "2026-10-19T09:30:00Z"
