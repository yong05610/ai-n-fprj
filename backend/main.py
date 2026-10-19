import os
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from schemas import (
    ErrorResponse,
    PathRecommendationRequest,
    PathRecommendationResponse,
    PlanGenerateRequest,
    PlanGenerateResponse,
    GoalCreateRequest,
    GoalUpdateRequest,
    GoalResponse,
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskResponse,
    StudyLogCreateRequest,
    StudyLogUpdateRequest,
    StudyLogResponse,
    LearningDataSummaryResponse,
    DashboardSummaryResponse,
    ConversationCreateRequest,
    ConversationListItem,
    ConversationDetailResponse,
    SendMessageRequest,
    SendMessageResponse,
    ResourceListResponse,
    UserProfileResponse,
    ProfileUpdateRequest,
    DataDeleteResponse,
)

security = HTTPBearer(auto_error=False)


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="PaceMate API",
    version="0.1.0",
    description="PaceMate MVP backend API — Phase 1 Schema & Contracts",
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 요청"},
        401: {"model": ErrorResponse, "description": "인증 실패 (토큰 누락 또는 유효하지 않음)"},
        403: {"model": ErrorResponse, "description": "권한 없음 (타 UID 자원 접근)"},
        404: {"model": ErrorResponse, "description": "자원을 찾을 수 없음"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins(),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.get("/health", tags=["health"], summary="서비스 헬스체크")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "pacemate-api"}


# --- Phase 1 API Skeletons (OpenAPI DTO Documentation) ---
# NOTE: 핸들러 내부 로직은 Phase 1 범위에 따라 501 Not Implemented를 반환하며 실제 동작을 가장하지 않습니다.

def _not_implemented():
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Phase 1 schema skeleton - business logic will be implemented in future phases.",
    )


# 1. Path Recommendation
@app.post(
    "/api/path/recommend",
    response_model=PathRecommendationResponse,
    tags=["path"],
    summary="1단계: 분야 입력 기반 세부 과정 및 수준 체계 추천",
)
async def recommend_path(
    payload: PathRecommendationRequest,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


# 2. Plan Generation
@app.post(
    "/api/plan/generate",
    response_model=PlanGenerateResponse,
    tags=["plan"],
    summary="2단계: 주간 학습 과업·조언·참고자료 생성",
)
async def generate_plan(
    payload: PlanGenerateRequest,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


# 3. Goals CRUD
@app.get("/api/goals", response_model=List[GoalResponse], tags=["goals"], summary="사용자의 학습 목표 목록 조회")
async def list_goals(token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.post("/api/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED, tags=["goals"], summary="학습 목표 저장")
async def create_goal(payload: GoalCreateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.get("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 상세 조회")
async def get_goal(goal_id: str, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.patch("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 수정")
async def update_goal(goal_id: str, payload: GoalUpdateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.delete("/api/goals/{goal_id}", tags=["goals"], summary="목표 삭제")
async def delete_goal(goal_id: str, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


# 4. Tasks CRUD
@app.get("/api/tasks", response_model=List[TaskResponse], tags=["tasks"], summary="학습 과제 목록 조회")
async def list_tasks(
    goal_id: Optional[str] = Query(None, description="목표 ID 필터"),
    plan_week_start: Optional[str] = Query(None, description="계획 주간 시작일 필터"),
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"], summary="학습 과제 생성")
async def create_task(payload: TaskCreateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"], summary="과제 상태/추천요일 수정")
async def update_task(task_id: str, payload: TaskUpdateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.delete("/api/tasks/{task_id}", tags=["tasks"], summary="과제 삭제")
async def delete_task(task_id: str, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


# 5. Study Logs & Reflections CRUD
@app.get("/api/study-logs", response_model=List[StudyLogResponse], tags=["study-logs"], summary="학습 실행 기록 목록 조회")
async def list_study_logs(
    task_id: Optional[str] = Query(None, description="과제 ID 필터"),
    period: Optional[str] = Query("week", description="조회 기간 (week | all)"),
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.post("/api/study-logs", response_model=StudyLogResponse, status_code=status.HTTP_201_CREATED, tags=["study-logs"], summary="학습 실행 기록 및 회고 생성")
async def create_study_log(payload: StudyLogCreateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.patch("/api/study-logs/{log_id}", response_model=StudyLogResponse, tags=["study-logs"], summary="학습 실행 기록 및 회고 수정")
async def update_study_log(log_id: str, payload: StudyLogUpdateRequest, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.delete("/api/study-logs/{log_id}", tags=["study-logs"], summary="학습 실행 기록 삭제 (회고 포함, 과제 유지)")
async def delete_study_log(log_id: str, token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


# 6. Summaries
@app.get(
    "/api/data/summary",
    response_model=LearningDataSummaryResponse,
    tags=["summary"],
    summary="AI 튜터 컨텍스트용 학습 요약 및 최근 회고(최대 5건) 조회",
)
async def get_data_summary(
    keywords: Optional[str] = Query(None, description="질문 관련 회고 검색 키워드"),
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.get(
    "/api/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["summary"],
    summary="대시보드 화면용 종합 집계 (4대 지표, 오늘 과제, 주간 hit, 인사이트)",
)
async def get_dashboard_summary(token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


# 7. Conversations (AI Tutor - 단일화된 튜터 호출 엔드포인트)
@app.post(
    "/api/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["conversations"],
    summary="새 튜터 대화 세션 생성",
)
async def create_conversation(
    payload: ConversationCreateRequest,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.get(
    "/api/conversations",
    response_model=List[ConversationListItem],
    tags=["conversations"],
    summary="최근 대화 세션 목록 조회 (메시지 본문 제외)",
)
async def list_conversations(token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    tags=["conversations"],
    summary="대화 세션 상세 및 전체 메시지 이력 조회",
)
async def get_conversation(
    conversation_id: str,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    tags=["conversations"],
    summary="튜터 질의 전송 및 응답 수신 (튜터 대화 단일 엔드포인트)",
)
async def send_message(
    conversation_id: str,
    payload: SendMessageRequest,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


# 8. Resources
@app.get(
    "/api/resources",
    response_model=ResourceListResponse,
    tags=["resources"],
    summary="사전 검토된 읽기 전용 참고자료 검색 및 목록 조회",
)
async def list_resources(
    search: Optional[str] = Query(None, description="검색어"),
    category: Optional[str] = Query(None, description="과정 분류"),
):
    _not_implemented()


# 9. User Profile & Data Deletion
@app.get("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 조회")
async def get_profile(token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()


@app.patch("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 수정")
async def update_profile(
    payload: ProfileUpdateRequest,
    token: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    _not_implemented()


@app.post("/api/user/delete-data", response_model=DataDeleteResponse, tags=["user"], summary="내 학습 데이터 전체 삭제 요청")
async def delete_user_data(token: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    _not_implemented()
