import os
from datetime import date, datetime, timezone
from typing import Any, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials

from auth import assert_safe_auth_config, delete_auth_user, get_current_uid, security
from errors import api_error, bad_request, forbidden, not_found, validation_exception_handler
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
    ConsentCreateRequest,
    ConsentResponse,
)
from store import USER_OWNED_COLLECTIONS, assert_safe_store_config, get_store

CURRENT_TERMS_VERSION = "v1.0"

assert_safe_auth_config()
assert_safe_store_config()


def _allowed_origins() -> list[str]:
    raw = os.getenv("CORS_ORIGINS", "http://localhost:3000")
    return [origin.strip() for origin in raw.split(",") if origin.strip()]


app = FastAPI(
    title="PaceMate API",
    version="0.1.0",
    description="PaceMate MVP backend API",
    responses={
        400: {"model": ErrorResponse, "description": "잘못된 요청"},
        401: {"model": ErrorResponse, "description": "인증 실패 (토큰 누락 또는 유효하지 않음)"},
        403: {"model": ErrorResponse, "description": "권한 없음 (타 UID 자원 접근)"},
        404: {"model": ErrorResponse, "description": "자원을 찾을 수 없음"},
        500: {"model": ErrorResponse, "description": "서버 내부 오류"},
    },
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)

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


# --- Common helpers & dependencies ---

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _parse_date(value: str, field_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise bad_request(f"{field_name} 값이 올바른 날짜(YYYY-MM-DD)가 아닙니다.", {"field": field_name})


def get_db():
    try:
        return get_store()
    except Exception:
        raise api_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STORE_UNAVAILABLE",
            "데이터 저장소에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.",
        )


def _consent_required() -> HTTPException:
    return api_error(
        status.HTTP_403_FORBIDDEN,
        "CONSENT_REQUIRED",
        "서비스 이용 안내에 동의한 뒤 이용할 수 있습니다.",
    )


def require_consented_uid(uid: str = Depends(get_current_uid), db=Depends(get_db)) -> str:
    """Personal data endpoints are available only after the current terms are accepted."""
    user = db.get("users", uid)
    if not user or user.get("consent_version") != CURRENT_TERMS_VERSION:
        raise _consent_required()
    return uid


def _get_owned(db, collection: str, doc_id: str, uid: str) -> dict[str, Any]:
    doc = db.get(collection, doc_id)
    if doc is None:
        raise not_found()
    if doc.get("user_id") != uid:
        raise forbidden()
    return doc


def _changes(payload) -> dict[str, Any]:
    return payload.model_dump(exclude_unset=True, exclude_none=True)


def _validate_goal_levels(goal: dict[str, Any]) -> None:
    if goal["target_level_order"] <= goal["current_level_order"]:
        raise bad_request("목표 수준은 현재 수준보다 높은 수준만 선택할 수 있습니다.", {"field": "target_level_order"})


def _validate_target_date_not_past(target_date: str) -> None:
    """Only call this when target_date is being set/changed by the caller.

    A goal's deadline naturally moves into the past over time; re-checking it on every
    unrelated update (e.g. marking an old goal completed/archived) would make goals past
    their deadline permanently un-editable.
    """
    if _parse_date(target_date, "target_date") < date.today():
        raise bad_request("목표 완료 희망일은 오늘 이후여야 합니다.", {"field": "target_date"})


def _validate_week_start(value: str) -> None:
    if _parse_date(value, "plan_week_start").weekday() != 0:
        raise bad_request("계획 주간 시작일은 월요일이어야 합니다.", {"field": "plan_week_start"})


def _delete_task_children(db, uid: str, task_id: str) -> None:
    db.delete_where("reflections", user_id=uid, task_id=task_id)
    db.delete_where("study_logs", user_id=uid, task_id=task_id)


# --- Consent (Phase 3) ---

@app.post(
    "/api/consent",
    response_model=ConsentResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["user"],
    summary="서비스 이용 안내 동의 기록 (익명 UID 발급 직후 호출)",
)
def create_consent(
    payload: ConsentCreateRequest,
    response: Response,
    uid: str = Depends(get_current_uid),
    db=Depends(get_db),
):
    if payload.terms_version != CURRENT_TERMS_VERSION:
        raise api_error(
            status.HTTP_400_BAD_REQUEST,
            "TERMS_VERSION_MISMATCH",
            "안내 문구가 변경되었습니다. 새 안내를 확인해 주세요.",
            {"current_version": CURRENT_TERMS_VERSION},
        )
    if not (payload.privacy_agreed and payload.ai_use_agreed):
        raise bad_request("필수 안내 항목에 모두 동의해야 시작할 수 있습니다.")

    existing = next(
        (r for r in db.find("consent_records", user_id=uid) if r.get("terms_version") == payload.terms_version),
        None,
    )
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return existing

    now = _now_iso()
    record = db.create(
        "consent_records",
        {
            "user_id": uid,
            "terms_version": payload.terms_version,
            "privacy_agreed": True,
            "ai_use_agreed": True,
            "consented_at": now,
        },
    )
    if db.get("users", uid) is None:
        db.set(
            "users",
            uid,
            {
                "uid": uid,
                "role": "learner",
                "active_goal_id": None,
                "consent_version": payload.terms_version,
                "created_at": now,
                "last_active_at": now,
            },
        )
    else:
        db.update("users", uid, {"consent_version": payload.terms_version, "last_active_at": now})
    return record


# --- Phase 4~6 API Skeletons (OpenAPI DTO Documentation) ---
# NOTE: 핸들러 내부 로직은 Phase 1 범위에 따라 501 Not Implemented를 반환하며 실제 동작을 가장하지 않습니다.

def _not_implemented():
    raise api_error(
        status.HTTP_501_NOT_IMPLEMENTED,
        "NOT_IMPLEMENTED",
        "Phase 1 schema skeleton - business logic will be implemented in future phases.",
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
def list_goals(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goals = db.find("goals", user_id=uid)
    return sorted(goals, key=lambda g: g["created_at"], reverse=True)


@app.post("/api/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED, tags=["goals"], summary="학습 목표 저장")
def create_goal(payload: GoalCreateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    data = payload.model_dump()
    _validate_goal_levels(data)
    _validate_target_date_not_past(data["target_date"])
    now = _now_iso()
    goal = db.create("goals", {**data, "user_id": uid, "status": "active", "created_at": now, "updated_at": now})
    user = db.get("users", uid)
    if user and not user.get("active_goal_id"):
        db.update("users", uid, {"active_goal_id": goal["id"]})
    return goal


@app.get("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 상세 조회")
def get_goal(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    return _get_owned(db, "goals", goal_id, uid)


@app.patch("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 수정")
def update_goal(goal_id: str, payload: GoalUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", goal_id, uid)
    changes = _changes(payload)
    _validate_goal_levels({**goal, **changes})
    if "target_date" in changes:
        _validate_target_date_not_past(changes["target_date"])
    return db.update("goals", goal_id, {**changes, "updated_at": _now_iso()})


@app.delete("/api/goals/{goal_id}", tags=["goals"], summary="목표 삭제 (하위 과제·기록·회고 포함)")
def delete_goal(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "goals", goal_id, uid)
    for task in db.find("tasks", user_id=uid, goal_id=goal_id):
        _delete_task_children(db, uid, task["id"])
    db.delete_where("tasks", user_id=uid, goal_id=goal_id)
    db.delete("goals", goal_id)
    user = db.get("users", uid)
    if user and user.get("active_goal_id") == goal_id:
        db.update("users", uid, {"active_goal_id": None})
    return {"status": "deleted", "id": goal_id}


# 4. Tasks CRUD
@app.get("/api/tasks", response_model=List[TaskResponse], tags=["tasks"], summary="학습 과제 목록 조회")
def list_tasks(
    goal_id: Optional[str] = Query(None, description="목표 ID 필터"),
    plan_week_start: Optional[str] = Query(None, description="계획 주간 시작일 필터"),
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    filters: dict[str, Any] = {"user_id": uid}
    if goal_id:
        filters["goal_id"] = goal_id
    if plan_week_start:
        filters["plan_week_start"] = plan_week_start
    tasks = db.find("tasks", **filters)
    return sorted(tasks, key=lambda t: (t["plan_week_start"], t["order_index"], t["created_at"]))


@app.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"], summary="학습 과제 생성")
def create_task(payload: TaskCreateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "goals", payload.goal_id, uid)
    _validate_week_start(payload.plan_week_start)
    now = _now_iso()
    data = payload.model_dump()
    data["description"] = data["description"] or ""
    data["suggested_weekday"] = data["suggested_weekday"] or "none"
    data["order_index"] = data["order_index"] or 0
    return db.create("tasks", {**data, "user_id": uid, "status": "pending", "created_at": now, "updated_at": now})


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"], summary="과제 상태/추천요일 수정")
def update_task(task_id: str, payload: TaskUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "tasks", task_id, uid)
    return db.update("tasks", task_id, {**_changes(payload), "updated_at": _now_iso()})


@app.delete("/api/tasks/{task_id}", tags=["tasks"], summary="과제 삭제 (하위 기록·회고 포함)")
def delete_task(task_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "tasks", task_id, uid)
    _delete_task_children(db, uid, task_id)
    db.delete("tasks", task_id)
    return {"status": "deleted", "id": task_id}


# 5. Study Logs & Reflections CRUD
@app.get("/api/study-logs", response_model=List[StudyLogResponse], tags=["study-logs"], summary="학습 실행 기록 목록 조회")
async def list_study_logs(
    task_id: Optional[str] = Query(None, description="과제 ID 필터"),
    period: Optional[str] = Query("week", description="조회 기간 (week | all)"),
    uid: str = Depends(require_consented_uid),
):
    _not_implemented()


@app.post("/api/study-logs", response_model=StudyLogResponse, status_code=status.HTTP_201_CREATED, tags=["study-logs"], summary="학습 실행 기록 및 회고 생성")
async def create_study_log(payload: StudyLogCreateRequest, uid: str = Depends(require_consented_uid)):
    _not_implemented()


@app.patch("/api/study-logs/{log_id}", response_model=StudyLogResponse, tags=["study-logs"], summary="학습 실행 기록 및 회고 수정")
async def update_study_log(log_id: str, payload: StudyLogUpdateRequest, uid: str = Depends(require_consented_uid)):
    _not_implemented()


@app.delete("/api/study-logs/{log_id}", tags=["study-logs"], summary="학습 실행 기록 삭제 (회고 포함, 과제 유지)")
async def delete_study_log(log_id: str, uid: str = Depends(require_consented_uid)):
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
    uid: str = Depends(require_consented_uid),
):
    _not_implemented()


@app.get(
    "/api/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["summary"],
    summary="대시보드 화면용 종합 집계 (4대 지표, 오늘 과제, 주간 hit, 인사이트)",
)
async def get_dashboard_summary(uid: str = Depends(require_consented_uid)):
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
    uid: str = Depends(require_consented_uid),
):
    _not_implemented()


@app.get(
    "/api/conversations",
    response_model=List[ConversationListItem],
    tags=["conversations"],
    summary="최근 대화 세션 목록 조회 (메시지 본문 제외)",
)
async def list_conversations(uid: str = Depends(require_consented_uid)):
    _not_implemented()


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    tags=["conversations"],
    summary="대화 세션 상세 및 전체 메시지 이력 조회",
)
async def get_conversation(
    conversation_id: str,
    uid: str = Depends(require_consented_uid),
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
    uid: str = Depends(require_consented_uid),
):
    _not_implemented()


# 8. Resources
# 결정: 사전 검토된 공용 자료 카탈로그이며 사용자 소유 데이터가 아니므로 인증 없이 공개한다.
@app.get(
    "/api/resources",
    response_model=ResourceListResponse,
    tags=["resources"],
    summary="사전 검토된 읽기 전용 참고자료 검색 및 목록 조회 (공개, 인증 불필요)",
)
async def list_resources(
    search: Optional[str] = Query(None, description="검색어"),
    category: Optional[str] = Query(None, description="과정 분류"),
):
    _not_implemented()


# 9. User Profile & Data Deletion
def _profile(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": user["uid"],
        "role": user.get("role", "learner"),
        "active_goal_id": user.get("active_goal_id"),
        "consent_version": user.get("consent_version"),
        "created_at": user["created_at"],
    }


@app.get("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 조회")
def get_profile(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    return _profile(db.get("users", uid))


@app.patch("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 수정")
def update_profile(payload: ProfileUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("active_goal_id"):
        _get_owned(db, "goals", changes["active_goal_id"], uid)
    user = db.update("users", uid, {**changes, "last_active_at": _now_iso()})
    return _profile(user)


@app.post("/api/user/delete-data", response_model=DataDeleteResponse, tags=["user"], summary="내 학습 데이터 전체 삭제 요청")
def delete_user_data(uid: str = Depends(get_current_uid), db=Depends(get_db)):
    for collection in USER_OWNED_COLLECTIONS:
        db.delete_where(collection, user_id=uid)
    db.delete("users", uid)
    try:
        delete_auth_user(uid)
    except Exception:
        # Data is already gone at this point; only the Firebase account cleanup failed
        # (and can be retried safely). Do not report this to the caller as a failure.
        return DataDeleteResponse(
            status="auth_cleanup_pending",
            message="학습 데이터는 모두 삭제되었습니다. 계정 정리만 남아 있으며 다시 시도할 수 있습니다.",
        )
    return DataDeleteResponse()
