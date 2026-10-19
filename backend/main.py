import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

import clock
from ai_client import AIClient, AIRetryFeedback, AISchemaError, AITimeoutError, AIUnavailableError, get_ai_client
from ai_schemas import AIPathRecommendation, AIPlanDraft
from auth import assert_safe_auth_config, delete_auth_user, get_current_uid
from errors import api_error, bad_request, forbidden, not_found, validation_exception_handler
from prompts import PATH_RECOMMEND_SYSTEM_PROMPT, PLAN_GENERATE_SYSTEM_PROMPT
from resources_catalog import match_references, no_match_notice
from schemas import (
    ErrorResponse,
    PathRecommendationRequest,
    PathRecommendationResponse,
    CourseItem,
    PlanGenerateRequest,
    PlanGenerateResponse,
    WeeklyTaskPlanItem,
    AdviceItem,
    ResourceReferenceItem,
    PlanConfirmRequest,
    PlanConfirmResponse,
    GoalCreateRequest,
    GoalUpdateRequest,
    GoalResponse,
    TaskCreateRequest,
    TaskUpdateRequest,
    TaskResponse,
    StudyLogCreateRequest,
    StudyLogUpdateRequest,
    StudyLogResponse,
    TimerStartRequest,
    ActiveTimerResponse,
    TimerFinishRequest,
    TimerCancelRequest,
    LearningDataSummaryResponse,
    DashboardSummaryResponse,
    TodayTaskItem,
    DailyHitItem,
    AIInsightSummary,
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


def get_current_user_doc(uid: str = Depends(get_current_uid), db=Depends(get_db)) -> Optional[dict[str, Any]]:
    """Shared sub-dependency so a request needing both the consent check and the user
    document (Phase 5's dashboard/timer endpoints) reads `users` once, not twice.

    FastAPI caches a dependency's result per request when the same callable is reached
    through more than one path - `require_consented_uid` and `require_consented_user_doc`
    both depend on this, so only one `db.get("users", uid)` happens per request. This is
    deliberately narrow (Phase 3/4's existing endpoints are untouched) rather than a
    blanket refactor of every `require_consented_uid` call site (검증팀 항목 1, 보류 사유는
    docs/phase5_report.md 참고).
    """
    return db.get("users", uid)


def require_consented_uid(uid: str = Depends(get_current_uid), user=Depends(get_current_user_doc)) -> str:
    """Personal data endpoints are available only after the current terms are accepted."""
    if not user or user.get("consent_version") != CURRENT_TERMS_VERSION:
        raise _consent_required()
    return uid


def require_consented_user_doc(
    uid: str = Depends(get_current_uid), user=Depends(get_current_user_doc)
) -> dict[str, Any]:
    """Like require_consented_uid, but for endpoints that need the user document itself
    (active_goal_id, active_timer) and would otherwise re-fetch it."""
    if not user or user.get("consent_version") != CURRENT_TERMS_VERSION:
        raise _consent_required()
    return user


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
    if _parse_date(target_date, "target_date") < clock.today():
        raise bad_request("목표 완료 희망일은 오늘 이후여야 합니다.", {"field": "target_date"})


def _validate_week_start(value: str) -> None:
    if _parse_date(value, "plan_week_start").weekday() != 0:
        raise bad_request("계획 주간 시작일은 월요일이어야 합니다.", {"field": "plan_week_start"})


def _validate_week_within_target(week_start: date, target_date: date) -> None:
    if week_start > target_date:
        raise bad_request("계획 주간이 목표 완료 희망일을 넘습니다.", {"field": "plan_week_start"})


def _validate_task_time_budget(
    db,
    uid: str,
    goal: dict[str, Any],
    plan_week_start: str,
    estimated_minutes: int,
    exclude_task_id: Optional[str] = None,
) -> None:
    """Shared by POST /api/tasks and PATCH /api/tasks/{id}: the same weekly time-budget
    rule AI-generated plans follow must also apply to tasks created/edited by hand,
    so the manual path can't bypass it (docs/phase4_dev_prompt.md 4.5)."""
    existing = db.find("tasks", user_id=uid, goal_id=goal["id"], plan_week_start=plan_week_start)
    total = sum(t["estimated_minutes"] for t in existing if t["id"] != exclude_task_id) + estimated_minutes
    if total > goal["weekly_hours"] * 60:
        raise bad_request(
            "이번 주 과업 총 예상 시간이 주당 가능 시간을 초과합니다.",
            {"field": "estimated_minutes"},
        )


def _delete_task_children(db, uid: str, task_id: str) -> None:
    db.delete_where("reflections", user_id=uid, task_id=task_id)
    db.delete_where("study_logs", user_id=uid, task_id=task_id)


def _study_log_stats(db, uid: str, task_id: str) -> tuple[int, int]:
    logs = db.find("study_logs", user_id=uid, task_id=task_id)
    return len(logs), sum(log["minutes"] for log in logs)


def _with_task_stats(task: dict[str, Any], record_count: int, total_minutes: int) -> dict[str, Any]:
    return {**task, "record_count": record_count, "total_minutes": total_minutes}


def _find_by_client_request_id(db, collection: str, uid: str, client_request_id: Optional[str]) -> Optional[dict[str, Any]]:
    """Shared idempotency lookup (Phase 4 plan/confirm pattern): a write request carrying
    a client_request_id that already succeeded returns the prior result instead of
    creating a duplicate."""
    if not client_request_id:
        return None
    return next(
        (d for d in db.find(collection, user_id=uid, client_request_id=client_request_id)),
        None,
    )


def _validate_study_date_not_future(study_date: str) -> date:
    parsed = _parse_date(study_date, "study_date")
    if parsed > clock.today():
        raise bad_request("학습 날짜는 오늘보다 미래일 수 없습니다.", {"field": "study_date"})
    return parsed


def _clear_active_timer_for_task(db, uid: str, task_id: str) -> None:
    """Deleting a task must not leave a dangling active timer pointing at it (5.2)."""
    user = db.get("users", uid)
    active = (user or {}).get("active_timer")
    if active and active.get("task_id") == task_id:
        db.update("users", uid, {"active_timer": None})


def _reflection_for_log(db, uid: str, study_log_id: str, task_id: str, payload, now: str) -> dict[str, Any]:
    return db.create(
        "reflections",
        {
            "user_id": uid,
            "study_log_id": study_log_id,
            "task_id": task_id,
            "content": payload.content,
            "tags": payload.tags or [],
            "created_at": now,
            "updated_at": now,
        },
    )


def _attach_reflection(db, uid: str, log: dict[str, Any]) -> dict[str, Any]:
    reflections = db.find("reflections", user_id=uid, study_log_id=log["id"])
    return {**log, "reflection": reflections[0] if reflections else None}


def _attach_reflections_bulk(db, uid: str, logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """P5-6: list_study_logs previously ran one reflections query per log (200 reads on
    Firestore for a full page). One query for all of this user's reflections, grouped by
    study_log_id, replaces that."""
    by_log_id = {r["study_log_id"]: r for r in db.find("reflections", user_id=uid)}
    return [{**log, "reflection": by_log_id.get(log["id"])} for log in logs]


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


def _ai_error_response(exc: Exception) -> HTTPException:
    if isinstance(exc, AITimeoutError):
        return api_error(status.HTTP_504_GATEWAY_TIMEOUT, "AI_TIMEOUT", "AI 응답이 지연되고 있습니다. 다시 시도해 주세요.")
    if isinstance(exc, AISchemaError):
        return api_error(status.HTTP_502_BAD_GATEWAY, "AI_SCHEMA_ERROR", "AI 결과를 해석하지 못했습니다. 다시 시도해 주세요.")
    return api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "AI_UNAVAILABLE", "AI 서비스를 사용할 수 없습니다. 잠시 후 다시 시도해 주세요.")


def _validate_ai_path(parsed: AIPathRecommendation) -> None:
    if len(parsed.suggested_roles) > 5:
        raise ValueError("직무명은 5개 이하여야 합니다.")
    for course in parsed.courses:
        if not course.title.strip() or not course.description.strip():
            raise ValueError("과정 이름/설명이 비어 있습니다.")
        # Pydantic's AICourseItem.levels already enforces min_length=2; this re-check
        # exists for a clearer, specific error message (P4-8).
        if len(course.levels) < 2:
            raise ValueError("과정마다 수준이 최소 2개 이상이어야 목표 수준을 선택할 수 있습니다.")
        orders = [lvl.order for lvl in course.levels]
        if orders != sorted(orders) or len(orders) != len(set(orders)):
            raise ValueError("수준 순서(order)가 과정 안에서 중복 없이 오름차순이어야 합니다.")
        for lvl in course.levels:
            if not lvl.name.strip() or not lvl.description.strip():
                raise ValueError("수준 이름/설명이 비어 있습니다.")


def _validate_ai_plan(parsed: AIPlanDraft, max_total_minutes: int) -> None:
    total = sum(t.estimated_minutes for t in parsed.tasks)
    if total > max_total_minutes:
        # P4-9: tell the next retry attempt how far over budget this one was, instead
        # of just repeating the same instruction the model already failed to follow.
        raise AIRetryFeedback(
            "총 예상 시간이 주당 가능 시간을 초과합니다.",
            feedback={"previous_total_minutes": total, "max_total_minutes": max_total_minutes},
        )
    for t in parsed.tasks:
        if not t.title.strip() or not t.description.strip():
            raise ValueError("과업 제목/설명이 비어 있습니다.")
    if not parsed.advice_title.strip() or not parsed.advice_content.strip():
        raise ValueError("조언 제목/내용이 비어 있습니다.")


# 1. Path Recommendation
@app.post(
    "/api/path/recommend",
    response_model=PathRecommendationResponse,
    tags=["path"],
    summary="1단계: 분야 입력 기반 세부 과정 및 수준 체계 추천",
)
def recommend_path(
    payload: PathRecommendationRequest,
    uid: str = Depends(require_consented_uid),
    ai: AIClient = Depends(get_ai_client),
):
    user_payload = {"field": payload.field, "goal": payload.goal, "user_context": payload.user_context}
    try:
        parsed = ai.generate(PATH_RECOMMEND_SYSTEM_PROMPT, user_payload, AIPathRecommendation, validator=_validate_ai_path)
    except (AITimeoutError, AISchemaError, AIUnavailableError) as exc:
        raise _ai_error_response(exc)

    courses = [
        CourseItem(id=f"course-{i + 1}", title=c.title, description=c.description, levels=c.levels)
        for i, c in enumerate(parsed.courses)
    ]
    return PathRecommendationResponse(field=payload.field, courses=courses, suggested_roles=parsed.suggested_roles)


# 2. Plan Generation (draft only - nothing is persisted here; see /api/plan/confirm)
@app.post(
    "/api/plan/generate",
    response_model=PlanGenerateResponse,
    tags=["plan"],
    summary="2단계: 주간 학습 과업·조언·참고자료 생성 (초안, 미저장)",
)
def generate_plan(
    payload: PlanGenerateRequest,
    uid: str = Depends(require_consented_uid),
    ai: AIClient = Depends(get_ai_client),
):
    if payload.target_level_order <= payload.current_level_order:
        raise bad_request("목표 수준은 현재 수준보다 높은 수준만 선택할 수 있습니다.", {"field": "target_level_order"})
    target_date = _parse_date(payload.target_date, "target_date")
    if target_date < clock.today():
        raise bad_request("목표 완료 희망일은 오늘 이후여야 합니다.", {"field": "target_date"})

    week_start_str = payload.plan_week_start or clock.week_monday(clock.today()).isoformat()
    _validate_week_start(week_start_str)
    week_start = _parse_date(week_start_str, "plan_week_start")
    _validate_week_within_target(week_start, target_date)
    week_end = week_start + timedelta(days=6)

    max_total_minutes = payload.weekly_hours * 60
    user_payload = {
        "field": payload.field,
        "course": payload.course,
        "selected_role": payload.selected_role,
        "current_level_name": payload.current_level_name,
        "current_level_description": payload.current_level_description,
        "target_level_name": payload.target_level_name,
        "target_level_description": payload.target_level_description,
        "weekly_hours": payload.weekly_hours,
        "max_total_minutes": max_total_minutes,
    }
    try:
        draft = ai.generate(
            PLAN_GENERATE_SYSTEM_PROMPT,
            user_payload,
            AIPlanDraft,
            validator=lambda parsed: _validate_ai_plan(parsed, max_total_minutes),
        )
    except (AITimeoutError, AISchemaError, AIUnavailableError) as exc:
        raise _ai_error_response(exc)

    matches = match_references(payload.field, payload.course)
    references = [
        ResourceReferenceItem(title=m["title"], category=m["category"], url=m["url"], is_verified=bool(m.get("verified")))
        for m in matches
    ]
    references_notice = None if matches else no_match_notice(payload.field)

    tasks = [
        WeeklyTaskPlanItem(
            title=t.title,
            description=t.description,
            estimated_minutes=t.estimated_minutes,
            suggested_weekday=t.suggested_weekday or "none",
        )
        for t in draft.tasks
    ]
    return PlanGenerateResponse(
        plan_week_start=week_start.isoformat(),
        plan_week_end=week_end.isoformat(),
        total_estimated_minutes=sum(t.estimated_minutes for t in tasks),
        tasks=tasks,
        advice=AdviceItem(title=draft.advice_title, content=draft.advice_content),
        references=references,
        references_notice=references_notice,
    )


# 2b. Plan Confirmation - saves the goal and its edited draft tasks together (see
# PlanConfirmRequest docstring / docs/phase4_dev_prompt.md "열린 결정 1").
@app.post(
    "/api/plan/confirm",
    response_model=PlanConfirmResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["plan"],
    summary="편집한 계획 초안을 학습 목표·과제로 함께 저장",
)
def confirm_plan(
    payload: PlanConfirmRequest,
    response: Response,
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    # Idempotency (P4-4): a client that never saw the response to a prior confirm
    # (timeout, dropped connection) must be able to retry with the same
    # client_request_id instead of creating a second goal+task set.
    if payload.client_request_id:
        existing_goal = next(
            (g for g in db.find("goals", user_id=uid, client_request_id=payload.client_request_id)),
            None,
        )
        if existing_goal is not None:
            response.status_code = status.HTTP_200_OK
            existing_tasks = db.find("tasks", user_id=uid, goal_id=existing_goal["id"])
            existing_tasks.sort(key=lambda t: t["order_index"])
            return PlanConfirmResponse(goal=existing_goal, tasks=existing_tasks)

    goal_data = {
        "field": payload.field,
        "course": payload.course,
        "current_level_order": payload.current_level_order,
        "current_level_name": payload.current_level_name,
        "current_level_description": payload.current_level_description,
        "target_level_order": payload.target_level_order,
        "target_level_name": payload.target_level_name,
        "target_level_description": payload.target_level_description,
        "weekly_hours": payload.weekly_hours,
        "target_date": payload.target_date,
        "client_request_id": payload.client_request_id,
    }
    # Validate everything before writing anything, so a rejected request never leaves a
    # partial save (the store layer has no multi-document transaction to roll back).
    _validate_goal_levels(goal_data)
    _validate_target_date_not_past(goal_data["target_date"])
    _validate_week_start(payload.plan_week_start)
    target_date = _parse_date(payload.target_date, "target_date")
    week_start = _parse_date(payload.plan_week_start, "plan_week_start")
    _validate_week_within_target(week_start, target_date)
    total_minutes = sum(t.estimated_minutes for t in payload.tasks)
    if total_minutes > payload.weekly_hours * 60:
        raise bad_request("과업 총 예상 시간이 주당 가능 시간을 초과합니다.", {"field": "tasks"})

    now = _now_iso()
    goal = db.create("goals", {**goal_data, "user_id": uid, "status": "active", "created_at": now, "updated_at": now})
    user = db.get("users", uid)
    if user and not user.get("active_goal_id"):
        db.update("users", uid, {"active_goal_id": goal["id"]})

    tasks = []
    for idx, t in enumerate(payload.tasks):
        task_data = t.model_dump()
        task_data["description"] = task_data["description"] or ""
        task_data["suggested_weekday"] = task_data["suggested_weekday"] or "none"
        task = db.create(
            "tasks",
            {
                **task_data,
                "goal_id": goal["id"],
                "user_id": uid,
                "plan_week_start": payload.plan_week_start,
                "status": "pending",
                "order_index": idx,
                "created_at": now,
                "updated_at": now,
            },
        )
        tasks.append(task)
    return PlanConfirmResponse(goal=goal, tasks=tasks)


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
        _clear_active_timer_for_task(db, uid, task["id"])  # P5-2: a goal delete must not strand a timer
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
    sorted_tasks = sorted(tasks, key=lambda t: (t["plan_week_start"], t["order_index"], t["created_at"]))

    # One query for all of this user's logs (not one per task) - 5.9's "쿼리 수를 줄인다".
    stats: dict[str, tuple[int, int]] = {}
    for log in db.find("study_logs", user_id=uid):
        count, minutes = stats.get(log["task_id"], (0, 0))
        stats[log["task_id"]] = (count + 1, minutes + log["minutes"])
    return [_with_task_stats(t, *stats.get(t["id"], (0, 0))) for t in sorted_tasks]


@app.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"], summary="학습 과제 생성")
def create_task(payload: TaskCreateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", payload.goal_id, uid)
    _validate_week_start(payload.plan_week_start)
    _validate_week_within_target(_parse_date(payload.plan_week_start, "plan_week_start"), _parse_date(goal["target_date"], "target_date"))
    _validate_task_time_budget(db, uid, goal, payload.plan_week_start, payload.estimated_minutes)
    now = _now_iso()
    data = payload.model_dump()
    data["description"] = data["description"] or ""
    data["suggested_weekday"] = data["suggested_weekday"] or "none"
    data["order_index"] = data["order_index"] or 0
    task = db.create("tasks", {**data, "user_id": uid, "status": "pending", "created_at": now, "updated_at": now})
    return _with_task_stats(task, 0, 0)


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"], summary="과제 상태/추천요일 수정")
def update_task(task_id: str, payload: TaskUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    task = _get_owned(db, "tasks", task_id, uid)
    changes = _changes(payload)
    if "estimated_minutes" in changes:
        goal = _get_owned(db, "goals", task["goal_id"], uid)
        _validate_task_time_budget(
            db, uid, goal, task["plan_week_start"], changes["estimated_minutes"], exclude_task_id=task_id
        )
    updated = db.update("tasks", task_id, {**changes, "updated_at": _now_iso()})
    return _with_task_stats(updated, *_study_log_stats(db, uid, task_id))


@app.delete("/api/tasks/{task_id}", tags=["tasks"], summary="과제 삭제 (하위 기록·회고 포함)")
def delete_task(task_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "tasks", task_id, uid)
    _delete_task_children(db, uid, task_id)
    _clear_active_timer_for_task(db, uid, task_id)
    db.delete("tasks", task_id)
    return {"status": "deleted", "id": task_id}


STUDY_LOG_LIST_LIMIT = 200  # hard cap, no cursor pagination yet (5.4 decision, documented in report)


def _parse_iso_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# 5. Study Logs & Reflections CRUD
@app.get("/api/study-logs", response_model=List[StudyLogResponse], tags=["study-logs"], summary="학습 실행 기록 목록 조회")
def list_study_logs(
    response: Response,
    task_id: Optional[str] = Query(None, description="과제 ID 필터"),
    period: str = Query("week", description="조회 기간 (week | all)"),
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    if period not in ("week", "all"):
        raise bad_request("period는 week 또는 all이어야 합니다.", {"field": "period"})
    filters: dict[str, Any] = {"user_id": uid}
    if task_id:
        filters["task_id"] = task_id
    logs = db.find("study_logs", **filters)
    if period == "week":
        week_start = clock.week_monday(clock.today())
        logs = [log for log in logs if clock.is_within_week(date.fromisoformat(log["study_date"]), week_start)]
    logs.sort(key=lambda log: (log["study_date"], log["created_at"]), reverse=True)
    if len(logs) > STUDY_LOG_LIST_LIMIT:
        # 사소한 사항: 잘림을 조용히 하지 않는다 - 프론트가 안내 문구를 보여줄 수 있게 헤더로 알린다.
        response.headers["X-Study-Logs-Truncated"] = "true"
    return _attach_reflections_bulk(db, uid, logs[:STUDY_LOG_LIST_LIMIT])


@app.post(
    "/api/study-logs",
    response_model=StudyLogResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["study-logs"],
    summary="학습 실행 기록 및 회고 생성",
)
def create_study_log(
    payload: StudyLogCreateRequest, response: Response, uid: str = Depends(require_consented_uid), db=Depends(get_db)
):
    existing = _find_by_client_request_id(db, "study_logs", uid, payload.client_request_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _attach_reflection(db, uid, existing)

    task = _get_owned(db, "tasks", payload.task_id, uid)
    _validate_study_date_not_future(payload.study_date)

    now = _now_iso()
    log = db.create(
        "study_logs",
        {
            "user_id": uid,
            "task_id": payload.task_id,
            "goal_id": task["goal_id"],
            "study_date": payload.study_date,
            "minutes": payload.minutes,
            "activity": payload.activity,
            "started_at": payload.started_at,
            "ended_at": payload.ended_at,
            "client_request_id": payload.client_request_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    # Best-effort: validated before any write, but the store has no multi-document
    # transaction, so a failure between these two creates could leave an orphan
    # study_log with no reflection (documented in docs/phase5_report.md).
    if payload.reflection is not None:
        _reflection_for_log(db, uid, log["id"], payload.task_id, payload.reflection, now)
    return _attach_reflection(db, uid, log)


@app.patch("/api/study-logs/{log_id}", response_model=StudyLogResponse, tags=["study-logs"], summary="학습 실행 기록 및 회고 수정")
def update_study_log(
    log_id: str, payload: StudyLogUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)
):
    log = _get_owned(db, "study_logs", log_id, uid)
    if payload.study_date is not None:
        _validate_study_date_not_future(payload.study_date)

    changes = _changes(payload)
    changes.pop("reflection", None)
    changes.pop("delete_reflection", None)
    changes.pop("client_request_id", None)
    updated = db.update("study_logs", log_id, {**changes, "updated_at": _now_iso()}) if changes else log

    now = _now_iso()
    if payload.delete_reflection:
        # 열린 결정 4: PATCH 의 _changes()는 exclude_none 이라 reflection=null 로는 삭제를
        # 표현할 수 없다. 별도 불리언 플래그로 "회고만 삭제"를 명확히 구분한다.
        db.delete_where("reflections", user_id=uid, study_log_id=log_id)
    elif payload.reflection is not None:
        existing_reflections = db.find("reflections", user_id=uid, study_log_id=log_id)
        if existing_reflections:
            db.update(
                "reflections",
                existing_reflections[0]["id"],
                {"content": payload.reflection.content, "tags": payload.reflection.tags or [], "updated_at": now},
            )
        else:
            _reflection_for_log(db, uid, log_id, log["task_id"], payload.reflection, now)
    return _attach_reflection(db, uid, updated)


@app.delete("/api/study-logs/{log_id}", tags=["study-logs"], summary="학습 실행 기록 삭제 (회고 포함, 과제 유지)")
def delete_study_log(log_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "study_logs", log_id, uid)
    db.delete_where("reflections", user_id=uid, study_log_id=log_id)
    db.delete("study_logs", log_id)
    return {"status": "deleted", "id": log_id}


# 5b. Timer - server-authoritative, one active timer per user (열린 결정 1: 저장 위치는
# users.active_timer 필드. 일시정지는 MVP에서 제외한다 - 시작/종료/취소만. 근거는
# docs/phase5_report.md 참고). 경과 시간 계산은 _compute_elapsed_minutes 한 곳에만 있다 -
# 나중에 일시정지(누적 시간)를 추가해도 이 함수만 바꾸면 된다.
MAX_TIMER_DURATION_MINUTES = 1440  # 24h; beyond this, finishing requires a manual minutes override


def _compute_elapsed_minutes(started_at: str, ended_at: str) -> int:
    return max(1, round((_parse_iso_dt(ended_at) - _parse_iso_dt(started_at)).total_seconds() / 60))


@app.post(
    "/api/timer/start",
    response_model=ActiveTimerResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["timer"],
    summary="학습 타이머 시작 (사용자당 하나만 허용)",
)
def start_timer(
    payload: TimerStartRequest,
    response: Response,
    user: dict[str, Any] = Depends(require_consented_user_doc),
    db=Depends(get_db),
):
    # P5-7 (documented limitation, not fixed here): this is read-then-write, not atomic.
    # MemoryStore/FirestoreStore have no compare-and-set or transaction primitive, so two
    # tabs/devices starting a timer within the same instant can both pass this check and
    # both write users.active_timer (last write wins, no 409 for either). Firestore
    # transactions (`db.transaction()` + a read-modify-write callback) would close this
    # once real Firestore is connected (Task 0.5); the in-memory store would need an
    # equivalent compare-and-set. Low risk for a single-user MVP session, but a real gap.
    uid = user["uid"]
    task = _get_owned(db, "tasks", payload.task_id, uid)
    active = user.get("active_timer")
    if active:
        if payload.client_request_id and active.get("client_request_id") == payload.client_request_id:
            response.status_code = status.HTTP_200_OK
            return ActiveTimerResponse(
                active=True, task_id=active["task_id"], goal_id=active["goal_id"], started_at=active["started_at"]
            )
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TIMER_ALREADY_RUNNING",
            "진행 중인 학습을 먼저 종료·저장하세요.",
            {"task_id": active.get("task_id"), "goal_id": active.get("goal_id"), "started_at": active.get("started_at")},
        )

    now = _now_iso()
    active_timer = {
        "task_id": payload.task_id,
        "goal_id": task["goal_id"],
        "started_at": now,
        "client_request_id": payload.client_request_id,
    }
    db.update("users", uid, {"active_timer": active_timer})
    return ActiveTimerResponse(active=True, task_id=payload.task_id, goal_id=task["goal_id"], started_at=now)


@app.get(
    "/api/timer/active",
    response_model=ActiveTimerResponse,
    tags=["timer"],
    summary="활성 타이머 조회 (새로고침 복원용)",
)
def get_active_timer(user: dict[str, Any] = Depends(require_consented_user_doc)):
    active = user.get("active_timer")
    if not active:
        return ActiveTimerResponse(active=False)
    return ActiveTimerResponse(
        active=True, task_id=active["task_id"], goal_id=active["goal_id"], started_at=active["started_at"]
    )


@app.post(
    "/api/timer/cancel",
    response_model=ActiveTimerResponse,
    tags=["timer"],
    summary="활성 타이머 취소 (기록을 만들지 않음)",
)
def cancel_timer(payload: TimerCancelRequest, user: dict[str, Any] = Depends(require_consented_user_doc), db=Depends(get_db)):
    db.update("users", user["uid"], {"active_timer": None})
    return ActiveTimerResponse(active=False)


@app.post(
    "/api/timer/finish",
    response_model=StudyLogResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["timer"],
    summary="활성 타이머 종료 및 학습 기록 저장",
)
def finish_timer(
    payload: TimerFinishRequest,
    response: Response,
    user: dict[str, Any] = Depends(require_consented_user_doc),
    db=Depends(get_db),
):
    uid = user["uid"]

    # P5-1: check idempotency *before* the active-timer check. The first successful call
    # already cleared active_timer, so a retry that checked "is a timer running" first
    # would always hit TIMER_NOT_RUNNING (409) instead of returning the record it already
    # saved - the client sees a false failure and may re-enter the same session by hand.
    existing = _find_by_client_request_id(db, "study_logs", uid, payload.client_request_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        # Only clear active_timer if it's still the one this finish produced (same task) -
        # covers a crash between creating the log and clearing the timer on the first
        # attempt, without touching a timer the user may have started again since.
        current_user = db.get("users", uid) or {}
        still_active = current_user.get("active_timer")
        if still_active and still_active.get("task_id") == existing.get("task_id"):
            db.update("users", uid, {"active_timer": None})
        return _attach_reflection(db, uid, existing)

    active = user.get("active_timer")
    if not active:
        raise api_error(status.HTTP_409_CONFLICT, "TIMER_NOT_RUNNING", "진행 중인 타이머가 없습니다.")

    # P5-2: a deleted goal already clears active_timer for its tasks (delete_goal /
    # delete_task), but this defends against any other path that might leave it dangling.
    task = db.get("tasks", active["task_id"])
    if task is None or task.get("user_id") != uid:
        db.update("users", uid, {"active_timer": None})
        raise api_error(
            status.HTTP_409_CONFLICT,
            "TIMER_TASK_GONE",
            "타이머가 연결된 과제가 삭제되어 타이머를 정리했습니다. 새로 시작해 주세요.",
        )

    started_at = active["started_at"]
    ended_at = _now_iso()
    elapsed_minutes = _compute_elapsed_minutes(started_at, ended_at)
    if payload.minutes is not None:
        minutes = payload.minutes
    elif elapsed_minutes > MAX_TIMER_DURATION_MINUTES:
        raise bad_request(
            "타이머가 24시간을 넘게 실행되어 자동 계산할 수 없습니다. 학습 시간을 직접 입력해 주세요.",
            {"field": "minutes"},
        )
    else:
        minutes = elapsed_minutes

    task_id = active["task_id"]
    now = ended_at
    log = db.create(
        "study_logs",
        {
            "user_id": uid,
            "task_id": task_id,
            "goal_id": active["goal_id"],
            "study_date": clock.date_from_utc_iso(started_at).isoformat(),
            "minutes": minutes,
            "activity": payload.activity,
            "started_at": started_at,
            "ended_at": ended_at,
            "client_request_id": payload.client_request_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    if payload.reflection is not None:
        _reflection_for_log(db, uid, log["id"], task_id, payload.reflection, now)
    db.update("users", uid, {"active_timer": None})
    return _attach_reflection(db, uid, log)


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


DASHBOARD_WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")
DASHBOARD_INSIGHT_MIN_RECORDS = 3
DASHBOARD_INSIGHT_MIN_REFLECTIONS = 1
# P5-4: today_tasks shows at most this many items, ordered incomplete-first (today's
# suggested weekday, then this week's remaining order_index), with completed tasks
# filling any leftover slots. If a week has more than this many incomplete tasks,
# completed ones are the first to be cut.
TODAY_TASKS_LIMIT = 5


def _empty_dashboard_summary(week_start: date, today: date) -> DashboardSummaryResponse:
    weekly_hits = [
        DailyHitItem(
            day=DASHBOARD_WEEKDAY_LABELS[i],
            date=(week_start + timedelta(days=i)).isoformat(),
            has_activity=False,
            is_today=(week_start + timedelta(days=i)) == today,
        )
        for i in range(7)
    ]
    return DashboardSummaryResponse(
        active_goal_title="",
        level_progress_text="",
        completed_task_count=0,
        total_task_count=0,
        progress_percentage=0,
        weekly_study_minutes=0,
        weekly_target_minutes=0,
        total_study_log_count=0,
        today_tasks=[],
        all_tasks_completed_this_week=False,
        weekly_hits=weekly_hits,
        insight=AIInsightSummary(
            text="학습 목표를 만들면 진행현황과 인사이트를 볼 수 있어요.",
            notice="",
            is_insufficient=True,
        ),
    )


@app.get(
    "/api/dashboard/summary",
    response_model=DashboardSummaryResponse,
    tags=["summary"],
    summary="대시보드 화면용 종합 집계 (4대 지표, 오늘 과제, 주간 hit, 인사이트)",
)
def get_dashboard_summary(user: dict[str, Any] = Depends(require_consented_user_doc), db=Depends(get_db)):
    today = clock.today()
    week_start = clock.week_monday(today)

    goal_id = user.get("active_goal_id")
    goal = db.get("goals", goal_id) if goal_id else None
    if goal is None or goal.get("user_id") != user["uid"]:
        # No active goal, or it was deleted out from under a stale active_goal_id - both
        # are the normal "nothing to show yet" case, not an error (always 200).
        return _empty_dashboard_summary(week_start, today)

    uid = user["uid"]
    tasks = db.find("tasks", user_id=uid, goal_id=goal_id)
    total_task_count = len(tasks)
    completed_task_count = sum(1 for t in tasks if t["status"] == "completed")
    progress_percentage = round(completed_task_count / total_task_count * 100) if total_task_count else 0

    logs = db.find("study_logs", user_id=uid, goal_id=goal_id)
    weekly_logs = [log for log in logs if clock.is_within_week(date.fromisoformat(log["study_date"]), week_start)]
    weekly_study_minutes = sum(log["minutes"] for log in weekly_logs)

    log_counts_by_task: dict[str, int] = {}
    for log in logs:
        log_counts_by_task[log["task_id"]] = log_counts_by_task.get(log["task_id"], 0) + 1

    this_week_tasks = sorted(
        (t for t in tasks if t["plan_week_start"] == week_start.isoformat()), key=lambda t: t["order_index"]
    )
    incomplete = [t for t in this_week_tasks if t["status"] != "completed"]
    completed_this_week = [t for t in this_week_tasks if t["status"] == "completed"]
    today_weekday = clock.WEEKDAY_BY_INDEX[today.weekday()]
    today_match = [t for t in incomplete if t["suggested_weekday"] == today_weekday]
    today_match_ids = {t["id"] for t in today_match}
    rest_incomplete = [t for t in incomplete if t["id"] not in today_match_ids]
    # P5-4: completed tasks stay visible (and toggleable back) instead of disappearing -
    # incomplete tasks keep priority for the limited slots, completed ones fill the rest.
    ordered = today_match + rest_incomplete + completed_this_week
    today_tasks = [
        TodayTaskItem(
            id=t["id"],
            title=t["title"],
            estimated_minutes=t["estimated_minutes"],
            suggested_weekday=t["suggested_weekday"],
            is_completed=t["status"] == "completed",
            record_count=log_counts_by_task.get(t["id"], 0),
        )
        for t in ordered[:TODAY_TASKS_LIMIT]
    ]
    all_tasks_completed_this_week = bool(this_week_tasks) and not incomplete

    reflection_count = len(db.find("reflections", user_id=uid))
    sufficient = len(logs) >= DASHBOARD_INSIGHT_MIN_RECORDS and reflection_count >= DASHBOARD_INSIGHT_MIN_REFLECTIONS
    insight = (
        AIInsightSummary(text="AI 인사이트는 Phase 6에서 제공됩니다.", notice="", is_insufficient=False)
        if sufficient
        else AIInsightSummary(text="기록과 회고를 더 남기면 인사이트를 볼 수 있어요.", notice="", is_insufficient=True)
    )

    weekly_hits = [
        DailyHitItem(
            day=DASHBOARD_WEEKDAY_LABELS[i],
            date=(week_start + timedelta(days=i)).isoformat(),
            has_activity=any(log["study_date"] == (week_start + timedelta(days=i)).isoformat() for log in weekly_logs),
            is_today=(week_start + timedelta(days=i)) == today,
        )
        for i in range(7)
    ]

    return DashboardSummaryResponse(
        active_goal_title=f"{goal['field']} · {goal['course']}",
        level_progress_text=f"{goal['current_level_name']} → {goal['target_level_name']}",
        completed_task_count=completed_task_count,
        total_task_count=total_task_count,
        progress_percentage=progress_percentage,
        weekly_study_minutes=weekly_study_minutes,
        weekly_target_minutes=goal["weekly_hours"] * 60,
        total_study_log_count=len(logs),
        today_tasks=today_tasks,
        all_tasks_completed_this_week=all_tasks_completed_this_week,
        weekly_hits=weekly_hits,
        insight=insight,
    )


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
