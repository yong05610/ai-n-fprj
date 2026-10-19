from typing import Optional, List
from pydantic import BaseModel, Field


# --- Common & Errors ---

class ErrorDetail(BaseModel):
    code: str = Field(..., description="오류 코드 (예: BAD_REQUEST, UNAUTHORIZED, NOT_FOUND)")
    message: str = Field(..., description="사용자 안내 오류 메시지")
    details: Optional[dict] = Field(None, description="추가 오류 세부정보")


class ErrorResponse(BaseModel):
    detail: ErrorDetail


# --- 1. Path Recommendation (FR-02 Step 1) ---

class LevelItem(BaseModel):
    level: int = Field(..., ge=1, le=5, description="수준 단계 (1~5)")
    name: str = Field(..., description="수준명 (예: Python 입문자)")
    description: str = Field(..., description="수준 상세 설명")


class CourseItem(BaseModel):
    id: str = Field(..., description="세부 과정 고유 ID 또는 슬러그")
    title: str = Field(..., description="세부 과정명 (예: 기본문법, 자료구조와 알고리즘)")
    description: str = Field(..., description="과정 개요")


class PathRecommendationRequest(BaseModel):
    field: str = Field(..., min_length=1, max_length=100, description="학습하고 싶은 분야 (자유 입력)")
    user_context: Optional[str] = Field(None, description="학습자의 추가 배경 또는 목표")


class PathRecommendationResponse(BaseModel):
    field: str = Field(..., description="요청된 학습 분야")
    courses: List[CourseItem] = Field(..., description="AI가 제안한 세부 과정 목록")
    levels: List[LevelItem] = Field(..., description="AI가 제안한 분야별 1~5단계 수준 체계")


# --- 2. Plan Generation (FR-02 Step 2) ---

class WeeklyTaskPlanItem(BaseModel):
    id: Optional[str] = Field(None, description="과제 식별자 (초안 시 임시 ID)")
    week_number: int = Field(1, description="주차 번호 (기본 1주차)")
    title: str = Field(..., description="학습 과업명")
    description: str = Field(..., description="과업 세부 내용")
    estimated_minutes: int = Field(..., ge=1, description="예상 학습 시간 (분)")
    suggested_weekday: Optional[str] = Field("none", description="선택적 추천 요일 (none, mon, tue, wed, thu, fri, sat, sun)")


class AdviceItem(BaseModel):
    title: str = Field(..., description="조언 제목")
    content: str = Field(..., description="AI 학습 조언 내용")


class ResourceReferenceItem(BaseModel):
    title: str = Field(..., description="자료명")
    category: str = Field(..., description="연결 과정명")
    url: Optional[str] = Field(None, description="출처 URL")
    is_verified: bool = Field(True, description="팀 사전 검토 여부")


class PlanGenerateRequest(BaseModel):
    field: str = Field(..., description="학습 분야")
    selected_courses: List[str] = Field(..., min_length=1, description="선택한 세부 과정 목록")
    current_level: int = Field(..., ge=1, le=5, description="현재 수준 번호")
    target_level: int = Field(..., ge=1, le=5, description="목표 수준 번호 (current_level 이상)")
    weekly_hours: int = Field(..., ge=1, le=100, description="주당 학습 가능 시간 (시간 단위)")
    target_date: str = Field(..., description="목표 완료 희망일 (YYYY-MM-DD)")
    plan_week_start: Optional[str] = Field(None, description="계획 주간 시작일 (YYYY-MM-DD, 기본 이번 주 월요일)")


class PlanGenerateResponse(BaseModel):
    plan_week_start: str = Field(..., description="계획 주간 시작일 (YYYY-MM-DD)")
    plan_week_end: str = Field(..., description="계획 주간 종료일 (YYYY-MM-DD)")
    total_estimated_minutes: int = Field(..., description="과업 총 예상 시간 (분)")
    tasks: List[WeeklyTaskPlanItem] = Field(..., description="주간 학습 과제 목록")
    advice: AdviceItem = Field(..., description="AI 학습 조언")
    references: List[ResourceReferenceItem] = Field(..., description="관련 참고자료 목록")


# --- 3. Goals CRUD ---

class GoalCreateRequest(BaseModel):
    field: str = Field(..., description="학습 분야")
    course: str = Field(..., description="선택 세부 과정")
    current_level_num: int = Field(..., ge=1, le=5)
    current_level_name: str = Field(...)
    target_level_num: int = Field(..., ge=1, le=5)
    target_level_name: str = Field(...)
    weekly_hours: int = Field(..., ge=1)
    target_date: str = Field(..., description="YYYY-MM-DD")


class GoalUpdateRequest(BaseModel):
    field: Optional[str] = None
    course: Optional[str] = None
    current_level_num: Optional[int] = None
    current_level_name: Optional[str] = None
    target_level_num: Optional[int] = None
    target_level_name: Optional[str] = None
    weekly_hours: Optional[int] = None
    target_date: Optional[str] = None
    status: Optional[str] = Field(None, description="active | completed | archived")


class GoalResponse(BaseModel):
    id: str
    user_id: str
    field: str
    course: str
    current_level_num: int
    current_level_name: str
    target_level_num: int
    target_level_name: str
    weekly_hours: int
    target_date: str
    status: str
    created_at: str
    updated_at: str


# --- 4. Tasks CRUD ---

class TaskCreateRequest(BaseModel):
    goal_id: str
    plan_week_start: str = Field(..., description="YYYY-MM-DD")
    title: str
    description: Optional[str] = ""
    estimated_minutes: int = Field(..., ge=1)
    suggested_weekday: Optional[str] = "none"
    order_index: Optional[int] = 0


class TaskUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    estimated_minutes: Optional[int] = None
    suggested_weekday: Optional[str] = None
    status: Optional[str] = Field(None, description="pending | completed")
    order_index: Optional[int] = None


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


# --- 5. Study Logs & Reflections CRUD ---

class ReflectionCreateRequest(BaseModel):
    content: str = Field(..., min_length=1, description="한 줄 회고")
    tags: Optional[List[str]] = Field(default_factory=list, description="회고 태그 목록")


class ReflectionResponse(BaseModel):
    id: str
    study_log_id: str
    content: str
    tags: List[str]
    created_at: str
    updated_at: str


class StudyLogCreateRequest(BaseModel):
    task_id: str
    goal_id: Optional[str] = None
    study_date: str = Field(..., description="YYYY-MM-DD")
    minutes: int = Field(..., ge=1, description="학습 시간 (분)")
    activity: str = Field(..., description="실행 내용")
    reflection: Optional[ReflectionCreateRequest] = Field(None, description="동반 작성할 회고")


class StudyLogUpdateRequest(BaseModel):
    study_date: Optional[str] = None
    minutes: Optional[int] = None
    activity: Optional[str] = None
    reflection: Optional[ReflectionCreateRequest] = None


class StudyLogResponse(BaseModel):
    id: str
    user_id: str
    task_id: str
    goal_id: Optional[str]
    study_date: str
    minutes: int
    activity: str
    reflection: Optional[ReflectionResponse] = None
    created_at: str
    updated_at: str


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
    weekly_hits: List[DailyHitItem]
    insight: AIInsightSummary


# --- 7. Conversations (AI Tutor) ---

class MessageItem(BaseModel):
    role: str = Field(..., description="user 또는 assistant")
    content: str = Field(..., description="메시지 내용")
    timestamp: str = Field(..., description="ISO 8601 UTC")


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
    title: Optional[str] = Field("새 학습 대화", description="세션 제목")


class SendMessageRequest(BaseModel):
    content: str = Field(..., min_length=1, description="사용자 질문 내용")


class SendMessageResponse(BaseModel):
    user_message: MessageItem
    assistant_message: MessageItem
    sources_used: List[str] = Field(default_factory=list, description="답변에 활용된 참고자료명")
    reflections_used: List[str] = Field(default_factory=list, description="답변에 활용된 본인 회고 요약")
    is_fallback: bool = Field(False, description="자료 미검색 일반 답변 여부")


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

class UserProfileResponse(BaseModel):
    uid: str
    role: str = "learner"
    active_goal_id: Optional[str] = None
    created_at: str


class ProfileUpdateRequest(BaseModel):
    active_goal_id: Optional[str] = None


class DataDeleteResponse(BaseModel):
    status: str = "deleted"
    message: str = "사용자의 모든 학습 데이터 및 동의 기록이 성공적으로 삭제되었습니다."
