from datetime import datetime
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, field_validator, model_validator

Weekday = Literal["none", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]
GoalStatus = Literal["active", "completed", "archived"]
TaskStatus = Literal["pending", "completed"]
DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"


# --- Common & Errors ---

class ErrorDetail(BaseModel):
    code: str = Field(..., description="오류 코드 (예: BAD_REQUEST, UNAUTHORIZED, NOT_FOUND)")
    message: str = Field(..., description="사용자 안내 오류 메시지")
    details: Optional[dict] = Field(None, description="추가 오류 세부정보")


class ErrorResponse(BaseModel):
    detail: ErrorDetail


# --- 1. Path Recommendation (FR-02 Step 1) ---

class LevelItem(BaseModel):
    order: int = Field(..., ge=1, le=20, description="같은 과정 안에서의 순서 등급 (높을수록 상위). 간격 계산·비교에 쓰지 않는다")
    name: str = Field(..., max_length=100, description="수준명 (예: Python 입문자). 화면에는 이 이름만 표시하고 번호는 표시하지 않는다")
    description: str = Field(..., max_length=2000, description="수준 상세 설명 (서술형, AI 해석용)")


class CourseItem(BaseModel):
    id: str = Field(..., description="세부 과정 고유 ID 또는 슬러그")
    title: str = Field(..., max_length=100, description="세부 과정명 (예: 기본문법, 자료구조와 알고리즘)")
    description: str = Field(..., max_length=2000, description="과정 개요")
    levels: List[LevelItem] = Field(
        ..., min_length=2, description="이 과정에 한정된 수준 체계 (최소 2개, 과정마다 다를 수 있음)"
    )


class PathRecommendationRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=100, description="학습하고 싶은 분야 (자유 입력)")
    goal: Optional[str] = Field(None, max_length=200, description="학습 목표 (자유 입력, 선택)")
    user_context: Optional[str] = Field(None, max_length=2000, description="학습자의 추가 배경 (선택)")

    @field_validator("field")
    @classmethod
    def _field_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field는 공백만으로 구성될 수 없습니다.")
        return value


class PathRecommendationResponse(BaseModel):
    field: str = Field(..., description="요청된 학습 분야")
    courses: List[CourseItem] = Field(..., min_length=1, max_length=10, description="AI가 제안한 세부 과정 목록 (과정별 수준 체계 포함)")
    suggested_roles: List[str] = Field(default_factory=list, max_length=5, description="AI가 제안한 직무/역할명 목록 (최대 5개, 선택)")


class RoleIdeasRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=100, description="학습하고 싶은 분야 (자유 입력)")

    @field_validator("field")
    @classmethod
    def _field_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("field는 공백만으로 구성될 수 없습니다.")
        return value


class RoleIdeasResponse(BaseModel):
    field: str
    suggested_roles: List[str] = Field(..., min_length=3, max_length=5, description="대표 직무·목표 예시 3~5개 (참고용, 선택 사항)")


# --- 2. Plan Generation (FR-02 Step 2) ---

class WeeklyTaskPlanItem(BaseModel):
    id: Optional[str] = Field(None, description="과제 식별자 (초안 시 임시 ID)")
    title: str = Field(..., max_length=200, description="학습 과업명")
    description: str = Field(..., max_length=2000, description="과업 세부 내용")
    estimated_minutes: int = Field(..., ge=1, le=6000, description="예상 학습 시간 (분)")
    suggested_weekday: Optional[Weekday] = Field("none", description="선택적 추천 요일 (마감일 아님)")


class AdviceItem(BaseModel):
    title: str = Field(..., max_length=200, description="조언 제목")
    content: str = Field(..., max_length=4000, description="AI 학습 조언 내용")


class ResourceReferenceItem(BaseModel):
    title: str = Field(..., description="자료명")
    category: str = Field(..., description="연결 과정명")
    url: Optional[str] = Field(None, description="출처 URL")
    is_verified: bool = Field(True, description="팀 사전 검토 여부")


class PlanGenerateRequest(BaseModel):
    # Decision (docs/phase4_dev_prompt.md "열린 결정 1"): no goal_id here. A goal is only
    # ever persisted once the user confirms (see PlanConfirmRequest below), matching PRD
    # FR-02 "사용자가 확정한 과정·수준·계획만 Firestore에 저장한다".
    field: str = Field(..., min_length=1, max_length=100, description="학습 분야")
    course: str = Field(..., min_length=1, max_length=100, description="선택한 세부 과정 (목표당 1개)")
    selected_role: Optional[str] = Field(None, max_length=100, description="1단계에서 추천받은 직무명 중 선택한 값 (선택)")
    current_level_order: int = Field(..., ge=1, le=20, description="현재 수준의 과정 내 순서 등급 (계산에 쓰지 않음)")
    current_level_name: str = Field(..., min_length=1, max_length=100)
    current_level_description: Optional[str] = Field(None, max_length=2000)
    target_level_order: int = Field(..., ge=1, le=20, description="목표 수준의 과정 내 순서 등급 (current_level_order보다 커야 함)")
    target_level_name: str = Field(..., min_length=1, max_length=100)
    target_level_description: Optional[str] = Field(None, max_length=2000)
    weekly_hours: int = Field(..., ge=1, le=100, description="주당 학습 가능 시간 (시간 단위)")
    target_date: str = Field(..., pattern=DATE_PATTERN, description="목표 완료 희망일 (YYYY-MM-DD, 오늘 이후)")
    start_date: str = Field(..., pattern=DATE_PATTERN, description="학습 시작일 (YYYY-MM-DD, 아무 요일, 오늘 이후). 계획 주간은 이 날짜가 속한 주(월~일)로 서버가 정한다")
    plan_week_start: Optional[str] = Field(
        None,
        pattern=DATE_PATTERN,
        description="선택. 주어지면 start_date가 속한 주의 월요일과 같아야 한다(다르면 400). 생략 권장",
    )

    @field_validator("field", "course")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("공백만으로 구성될 수 없습니다.")
        return value


class PlanGenerateResponse(BaseModel):
    plan_week_start: str = Field(..., description="계획 주간 시작일 (YYYY-MM-DD)")
    plan_week_end: str = Field(..., description="계획 주간 종료일 (YYYY-MM-DD)")
    total_estimated_minutes: int = Field(..., description="과업 총 예상 시간 (분)")
    tasks: List[WeeklyTaskPlanItem] = Field(..., description="주간 학습 과제 목록 (초안, 미저장)")
    advice: AdviceItem = Field(..., description="AI 학습 조언")
    references: List[ResourceReferenceItem] = Field(..., description="관련 참고자료 목록 (검토된 카탈로그에서만 선택)")
    references_notice: Optional[str] = Field(None, description="검토 자료를 찾지 못했을 때의 안내 및 검색 키워드 제안")


# --- 3. Goals CRUD ---

def _not_blank(value: Optional[str]) -> Optional[str]:
    if value is not None and not value.strip():
        raise ValueError("공백만으로 구성될 수 없습니다.")
    return value


class GoalCreateRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=100, description="학습 분야")
    course: str = Field(..., min_length=1, max_length=100, description="선택 세부 과정 (목표당 1개)")
    current_level_order: int = Field(..., ge=1, le=20, description="현재 수준의 과정 내 순서 등급")
    current_level_name: str = Field(..., min_length=1, max_length=100)
    current_level_description: Optional[str] = Field(None, max_length=2000, description="현재 수준 설명 스냅샷 (선택)")
    target_level_order: int = Field(..., ge=1, le=20, description="목표 수준의 과정 내 순서 등급 (current_level_order보다 커야 함)")
    target_level_name: str = Field(..., min_length=1, max_length=100)
    target_level_description: Optional[str] = Field(None, max_length=2000, description="목표 수준 설명 스냅샷 (선택)")
    weekly_hours: int = Field(..., ge=1, le=100)
    target_date: str = Field(..., pattern=DATE_PATTERN, description="YYYY-MM-DD (오늘 이후)")

    @field_validator("field", "course")
    @classmethod
    def _goal_fields_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("공백만으로 구성될 수 없습니다.")
        return value


class GoalUpdateRequest(BaseModel):
    field: Optional[str] = Field(None, min_length=1, max_length=100)
    course: Optional[str] = Field(None, min_length=1, max_length=100)
    current_level_order: Optional[int] = Field(None, ge=1, le=20)
    current_level_name: Optional[str] = Field(None, min_length=1, max_length=100)
    current_level_description: Optional[str] = Field(None, max_length=2000)
    target_level_order: Optional[int] = Field(None, ge=1, le=20)
    target_level_name: Optional[str] = Field(None, min_length=1, max_length=100)
    target_level_description: Optional[str] = Field(None, max_length=2000)
    weekly_hours: Optional[int] = Field(None, ge=1, le=100)
    target_date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    status: Optional[GoalStatus] = Field(None, description="active | completed | archived")

    @field_validator("field", "course")
    @classmethod
    def _goal_fields_not_blank(cls, value: Optional[str]) -> Optional[str]:
        return _not_blank(value)


class GoalResponse(BaseModel):
    id: str
    user_id: str
    field: str
    course: str
    current_level_order: int
    current_level_name: str
    current_level_description: Optional[str] = None
    target_level_order: int
    target_level_name: str
    target_level_description: Optional[str] = None
    weekly_hours: int
    start_date: str = Field(..., description="일정 시작일(YYYY-MM-DD). 기존 목표는 created_at의 서비스 시간대 날짜로 보정")
    target_date: str
    status: str
    created_at: str
    updated_at: str


# --- 4. Tasks CRUD ---

class TaskCreateRequest(BaseModel):
    goal_id: str = Field(..., min_length=1)
    plan_week_start: str = Field(..., pattern=DATE_PATTERN, description="YYYY-MM-DD (월요일)")
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field("", max_length=2000)
    estimated_minutes: int = Field(..., ge=1, le=6000)
    suggested_weekday: Optional[Weekday] = "none"
    order_index: Optional[int] = Field(0, ge=0)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title은 공백만으로 구성될 수 없습니다.")
        return value


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = Field(None, max_length=2000)
    estimated_minutes: Optional[int] = Field(None, ge=1, le=6000)
    suggested_weekday: Optional[Weekday] = None
    status: Optional[TaskStatus] = Field(None, description="pending | completed")
    order_index: Optional[int] = Field(None, ge=0)

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: Optional[str]) -> Optional[str]:
        return _not_blank(value)


class TaskResponse(BaseModel):
    id: str
    user_id: str
    goal_id: str
    plan_week_start: str
    title: str
    description: str
    estimated_minutes: int
    suggested_weekday: str
    status: str
    order_index: int
    created_at: str
    updated_at: str
    # Derived from study_logs at request time (Phase 5 결정 5) - never stored, so these
    # are always consistent with the current logs but cost one aggregation per request.
    record_count: int = 0
    total_minutes: int = 0


# --- 4b. Plan Confirmation (FR-02 Step 2 save; resolves "열린 결정 1") ---
# Saves the goal and its edited draft tasks in a single request, so nothing is
# persisted until the user confirms the plan (PRD FR-02).

class PlanConfirmTaskItem(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = Field("", max_length=2000)
    estimated_minutes: int = Field(..., ge=1, le=6000)
    suggested_weekday: Optional[Weekday] = "none"

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("title은 공백만으로 구성될 수 없습니다.")
        return value


class PlanConfirmRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=100)
    course: str = Field(..., min_length=1, max_length=100)
    current_level_order: int = Field(..., ge=1, le=20)
    current_level_name: str = Field(..., min_length=1, max_length=100)
    current_level_description: Optional[str] = Field(None, max_length=2000)
    target_level_order: int = Field(..., ge=1, le=20)
    target_level_name: str = Field(..., min_length=1, max_length=100)
    target_level_description: Optional[str] = Field(None, max_length=2000)
    weekly_hours: int = Field(..., ge=1, le=100)
    target_date: str = Field(..., pattern=DATE_PATTERN)
    start_date: str = Field(..., pattern=DATE_PATTERN, description="학습 시작일 (YYYY-MM-DD, 아무 요일, 오늘 이후). goals.start_date 로 저장되고 일정 겹침 검사의 시작점이다")
    plan_week_start: Optional[str] = Field(
        None,
        pattern=DATE_PATTERN,
        description="선택. 주어지면 start_date가 속한 주의 월요일과 같아야 한다(다르면 400). 서버가 start_date에서 도출한다",
    )
    tasks: List[PlanConfirmTaskItem] = Field(..., min_length=1)
    client_request_id: Optional[str] = Field(
        None,
        max_length=100,
        description="클라이언트가 만든 요청 식별자 (선택). 같은 값으로 재요청하면 중복 저장 대신 기존 결과를 반환한다",
    )

    @field_validator("field", "course")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("공백만으로 구성될 수 없습니다.")
        return value


class PlanConfirmResponse(BaseModel):
    goal: GoalResponse
    tasks: List[TaskResponse]


# --- 5. Study Logs & Reflections CRUD ---

def _dedupe_tags(tags: Optional[List[str]]) -> List[str]:
    seen: List[str] = []
    for tag in tags or []:
        tag = tag.strip()
        if not tag or len(tag) > 30 or tag in seen:
            continue
        seen.append(tag)
    return seen


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


class ReflectionCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=500, description="한 줄 회고")
    tags: Optional[List[str]] = Field(default_factory=list, max_length=10, description="회고 태그 목록 (중복·공백·30자 초과는 정리됨)")

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("content는 공백만으로 구성될 수 없습니다.")
        return value

    @field_validator("tags")
    @classmethod
    def _clean_tags(cls, value: Optional[List[str]]) -> List[str]:
        return _dedupe_tags(value)


class ReflectionResponse(BaseModel):
    id: str
    study_log_id: str
    content: str
    tags: List[str]
    created_at: str
    updated_at: str


def _validate_timer_pair(started_at: Optional[str], ended_at: Optional[str]) -> None:
    if (started_at is None) != (ended_at is None):
        raise ValueError("started_at과 ended_at은 둘 다 있거나 둘 다 없어야 합니다.")
    if started_at and ended_at:
        try:
            start, end = _parse_iso(started_at), _parse_iso(ended_at)
        except ValueError:
            raise ValueError("started_at/ended_at은 올바른 ISO 8601 형식이어야 합니다.")
        if start >= end:
            raise ValueError("started_at은 ended_at보다 빨라야 합니다.")


class StudyLogCreateRequest(BaseModel):
    task_id: str = Field(..., min_length=1, description="goal_id는 서버가 이 과제로부터 도출한다 (요청에 없음)")
    study_date: str = Field(..., pattern=DATE_PATTERN, description="YYYY-MM-DD (서비스 시간대 기준 오늘 이전·당일만)")
    minutes: int = Field(..., ge=1, le=1440, description="학습 시간 (분), 사용자가 보정한 값을 그대로 저장")
    activity: str = Field(..., max_length=2000, description="실행 내용")
    started_at: Optional[str] = Field(None, description="타이머 시작 시각 (ISO 8601, 선택)")
    ended_at: Optional[str] = Field(None, description="타이머 종료 시각 (ISO 8601, 선택)")
    reflection: Optional[ReflectionCreateRequest] = Field(None, description="동반 작성할 회고 (선택)")
    client_request_id: Optional[str] = Field(None, max_length=100, description="멱등 재시도 키 (선택)")

    @field_validator("activity")
    @classmethod
    def _activity_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("activity는 공백만으로 구성될 수 없습니다.")
        return value

    @model_validator(mode="after")
    def _check_timer_pair(self) -> "StudyLogCreateRequest":
        _validate_timer_pair(self.started_at, self.ended_at)
        return self


class StudyLogUpdateRequest(BaseModel):
    study_date: Optional[str] = Field(None, pattern=DATE_PATTERN)
    minutes: Optional[int] = Field(None, ge=1, le=1440)
    activity: Optional[str] = Field(None, max_length=2000)
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    reflection: Optional[ReflectionCreateRequest] = Field(None, description="회고 생성/수정 (내용 교체)")
    delete_reflection: bool = Field(
        False, description="true면 회고만 삭제한다. reflection 과 함께 보낼 수 없다 (열린 결정 4)"
    )
    client_request_id: Optional[str] = Field(None, max_length=100)

    @field_validator("activity")
    @classmethod
    def _activity_not_blank(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and not value.strip():
            raise ValueError("activity는 공백만으로 구성될 수 없습니다.")
        return value

    @model_validator(mode="after")
    def _check_timer_pair_and_reflection_conflict(self) -> "StudyLogUpdateRequest":
        _validate_timer_pair(self.started_at, self.ended_at)
        if self.delete_reflection and self.reflection is not None:
            raise ValueError("reflection과 delete_reflection을 동시에 보낼 수 없습니다.")
        return self


class StudyLogResponse(BaseModel):
    id: str
    user_id: str
    task_id: str
    goal_id: Optional[str]
    study_date: str
    minutes: int
    activity: str
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    reflection: Optional[ReflectionResponse] = None
    created_at: str
    updated_at: str


# --- 5b. Timer (server-authoritative, one active timer per user; 열린 결정 1) ---

class TimerStartRequest(BaseModel):
    task_id: str = Field(..., min_length=1)
    client_request_id: Optional[str] = Field(None, max_length=100)


class ActiveTimerResponse(BaseModel):
    active: bool
    task_id: Optional[str] = None
    goal_id: Optional[str] = None
    started_at: Optional[str] = None


class TimerFinishRequest(BaseModel):
    activity: str = Field(..., max_length=2000)
    minutes: Optional[int] = Field(
        None, ge=1, le=1440, description="생략하면 서버가 started_at/ended_at(서버 시각)으로 계산한다"
    )
    reflection: Optional[ReflectionCreateRequest] = None
    client_request_id: Optional[str] = Field(None, max_length=100)

    @field_validator("activity")
    @classmethod
    def _activity_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("activity는 공백만으로 구성될 수 없습니다.")
        return value


class TimerCancelRequest(BaseModel):
    client_request_id: Optional[str] = Field(None, max_length=100)


# --- 6. Summaries (Dashboard & Tutor Data Summary) ---

class RecentReflectionItem(BaseModel):
    id: str
    study_date: str
    task_title: str
    content: str
    tags: List[str]


class LearningDataSummaryResponse(BaseModel):
    user_id: str
    learning_summary: str = Field(..., description="목표·과정·수준 요약 텍스트")
    active_field: Optional[str] = None
    active_course: Optional[str] = None
    recent_reflections: List[RecentReflectionItem] = Field(..., max_length=5, description="최근 회고 최대 5건")


class TodayTaskItem(BaseModel):
    id: str
    title: str
    estimated_minutes: int
    suggested_weekday: str
    is_completed: bool
    record_count: int


class DailyHitItem(BaseModel):
    day: str = Field(..., description="월, 화, 수, 목, 금, 토, 일")
    date: str = Field(..., description="YYYY-MM-DD")
    has_activity: bool
    is_today: bool


class AIInsightSummary(BaseModel):
    text: str = Field(..., description="기록 기반 짧은 인사이트 제안")
    notice: str = Field("내 실행 기록과 회고 기반 · AI 생성 안내", description="AI 생성 고지 문구")
    is_insufficient: bool = Field(False, description="기록이 부족하여 기본 안내인 경우 true")


class GoalOverviewItem(BaseModel):
    goal_id: str
    course: str
    start_date: str
    target_date: str
    completed_task_count: int
    total_task_count: int
    progress_percentage: int


class DashboardSummaryResponse(BaseModel):
    active_goal_title: str
    level_progress_text: str
    completed_task_count: int
    total_task_count: int
    progress_percentage: int
    weekly_study_minutes: int
    weekly_target_minutes: int
    total_study_log_count: int
    today_tasks: List[TodayTaskItem]
    all_tasks_completed_this_week: bool = Field(
        False, description="이번 주 계획 과제가 1개 이상이고 전부 완료된 경우 true (P5-4)"
    )
    weekly_hits: List[DailyHitItem]
    insight: AIInsightSummary
    goals_overview: List[GoalOverviewItem] = Field(
        default_factory=list, description="진행 중(active)인 모든 학습의 종합 현황 (Phase 5B). 위 필드는 최근 학습(active_goal_id) 기준"
    )


class AnalyticsGoalItem(BaseModel):
    goal_id: str
    course: str
    start_date: str
    target_date: str
    completed_task_count: int
    total_task_count: int
    progress_percentage: int
    weekly_minutes_by_day: List[int] = Field(..., min_length=7, max_length=7, description="이번 주 월~일 학습 분")


class AnalyticsOverviewResponse(BaseModel):
    week_start: str = Field(..., description="이번 주 월요일 (Asia/Seoul)")
    week_end: str = Field(..., description="이번 주 일요일")
    goals: List[AnalyticsGoalItem]


# --- 7. Conversations (AI Tutor) ---

class SourceItem(BaseModel):
    doc_id: str
    title: str
    source_name: str
    url: Optional[str] = None


class MessageItem(BaseModel):
    role: str = Field(..., description="user 또는 assistant")
    content: str = Field(..., description="메시지 내용")
    timestamp: str = Field(..., description="ISO 8601 UTC")
    sources: List[SourceItem] = Field(
        default_factory=list,
        description="assistant 메시지에서 답변에 실제 쓴 참고자료. 서버가 검색된 자료에서 만들며 AI 가 만들지 않는다",
    )


class ConversationListItem(BaseModel):
    id: str
    title: str
    created_at: str
    updated_at: str


class ConversationDetailResponse(BaseModel):
    id: str
    user_id: str
    title: str
    messages: List[MessageItem]
    created_at: str
    updated_at: str


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field("새 대화", max_length=100, description="세션 제목 (생략하면 '새 대화', 첫 질문으로 자동 설정)")
    client_request_id: Optional[str] = Field(
        None, max_length=100, description="같은 값으로 재요청하면 새 대화를 또 만들지 않고 기존 대화를 돌려준다"
    )


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=1000, description="사용자 질문 내용 (1~1000자)")
    client_request_id: str = Field(
        ..., min_length=1, max_length=100, description="멱등 키. 같은 값으로 재요청하면 중복 저장 없이 기존 결과를 돌려준다"
    )

    @field_validator("content")
    @classmethod
    def _content_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("질문은 공백만으로 구성될 수 없습니다.")
        return value


class SendMessageResponse(BaseModel):
    user_message: MessageItem
    assistant_message: MessageItem
    conversation_title: str = Field(..., description="저장 후의 대화 제목 (첫 질문이면 방금 정해진 제목)")
    refused: bool = Field(False, description="학습과 무관한 질문이라 서버의 고정 문구로 거절한 경우 true")


# --- 8. Resources ---

class ResourceItem(BaseModel):
    id: str
    title: str
    category: str
    source_name: str
    url: Optional[str]
    created_at: str


class ResourceListResponse(BaseModel):
    items: List[ResourceItem]
    total: int


# --- 9. User Profile & Data Deletion ---

class ConsentCreateRequest(BaseModel):
    terms_version: str = Field(..., description="동의한 안내 문구 버전 (예: v1.0)")
    privacy_agreed: bool = Field(..., description="개인정보·익명 UID 안내 동의")
    ai_use_agreed: bool = Field(..., description="AI 생성 결과 활용 및 기록 이용 동의")


class ConsentResponse(BaseModel):
    id: str
    user_id: str
    terms_version: str
    privacy_agreed: bool
    ai_use_agreed: bool
    consented_at: str


class UserProfileResponse(BaseModel):
    uid: str
    role: str = "learner"
    active_goal_id: Optional[str] = None
    consent_version: Optional[str] = None
    created_at: str


class ProfileUpdateRequest(BaseModel):
    active_goal_id: Optional[str] = None


class DataDeleteResponse(BaseModel):
    status: str = "deleted"
    message: str = "사용자의 모든 학습 데이터 및 동의 기록이 성공적으로 삭제되었습니다."
