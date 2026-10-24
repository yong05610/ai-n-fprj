import hashlib
import json
import logging
import os
from datetime import date, datetime, timedelta, timezone
from typing import Any, Optional, List

from fastapi import FastAPI, HTTPException, Depends, Query, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

import clock
from ai_client import (
    AIClient,
    AIRetryFeedback,
    AISchemaError,
    AITimeoutError,
    AIUnavailableError,
    call_limits,
    get_ai_client,
    plan_max_output_tokens,
    plan_timeout_seconds,
)
from ai_schemas import AIInsight, AIInsightBasic, AIPathRecommendation, AIPlanDraft, AIRoleIdeas, AITutorAnswer
from auth import assert_safe_auth_config, delete_auth_user, get_current_uid
from errors import api_error, bad_request, forbidden, not_found, validation_exception_handler
import insight_rules
import rag
import schedule
import tutor
from prompts import (
    PATH_RECOMMEND_SYSTEM_PROMPT,
    PLAN_GENERATE_SYSTEM_PROMPT,
    ROLE_IDEAS_SYSTEM_PROMPT,
    TUTOR_SYSTEM_PROMPT,
    INSIGHT_SYSTEM_PROMPT,
    INSIGHT_SYSTEM_PROMPT_BASIC,
)
from resources_catalog import match_references, no_match_notice, search_links
from schemas import (
    ErrorResponse,
    PathRecommendationRequest,
    PathRecommendationResponse,
    RoleIdeasRequest,
    RoleIdeasResponse,
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
    GoalReferencesResponse,
    SearchLinkItem,
    InsightItem,
    InsightRequest,
    InsightResponse,
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
    GoalOverviewItem,
    AnalyticsGoalItem,
    AnalyticsOverviewResponse,
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
    AdminUserItem,
    AdminUserListResponse,
    FeedbackCreateRequest,
    FeedbackReceipt,
    AdminFeedbackItem,
    AdminFeedbackSummary,
    FeedbackStatusUpdate,
    ProfileUpdateRequest,
    DataDeleteResponse,
    ConsentCreateRequest,
    ConsentResponse,
)
from store import USER_OWNED_COLLECTIONS, assert_safe_store_config, get_store

CURRENT_TERMS_VERSION = "v1.1"

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


LAST_ACTIVE_TOUCH_INTERVAL = timedelta(minutes=10)


def _touch_last_active(db, user: dict[str, Any]) -> None:
    """Phase 5E: keep users.last_active_at meaningful for the admin user list without a write on
    every request - it is rewritten only when the stored value is 10 minutes old or missing.
    Called only for consented requests (after the consent check), by both require_consented_*."""
    now = datetime.now(timezone.utc)  # not _now_iso(): the check must not consume that helper's calls
    last = user.get("last_active_at")
    if last:
        try:
            if now - datetime.fromisoformat(last.replace("Z", "+00:00")) < LAST_ACTIVE_TOUCH_INTERVAL:
                return
        except ValueError:
            pass  # an unreadable stored value is simply replaced
    db.update("users", user["uid"], {"last_active_at": now.isoformat(timespec="seconds").replace("+00:00", "Z")})


def require_consented_uid(
    uid: str = Depends(get_current_uid), user=Depends(get_current_user_doc), db=Depends(get_db)
) -> str:
    """Personal data endpoints are available only after the current terms are accepted."""
    if not user or user.get("consent_version") != CURRENT_TERMS_VERSION:
        raise _consent_required()
    _touch_last_active(db, user)
    return uid


def require_consented_user_doc(
    uid: str = Depends(get_current_uid), user=Depends(get_current_user_doc), db=Depends(get_db)
) -> dict[str, Any]:
    """Like require_consented_uid, but for endpoints that need the user document itself
    (active_goal_id, active_timer) and would otherwise re-fetch it."""
    if not user or user.get("consent_version") != CURRENT_TERMS_VERSION:
        raise _consent_required()
    _touch_last_active(db, user)
    return user


def _admin_uids() -> frozenset[str]:
    """ADMIN_UIDS: comma separated, whitespace trimmed, empty entries ignored. Read per call
    so a change of the environment variable needs no code change. No UID lives in the code."""
    return frozenset(p.strip() for p in os.getenv("ADMIN_UIDS", "").split(",") if p.strip())


def _is_admin(uid: str) -> bool:
    return uid in _admin_uids()


def require_admin_uid(uid: str = Depends(require_consented_uid)) -> str:
    """Admin-only endpoints: normal authentication and consent first, then the UID that comes
    from the verified token must be listed in ADMIN_UIDS. Nothing in the request body, header
    or query takes part in this decision."""
    if not _is_admin(uid):
        raise forbidden("관리자만 사용할 수 있습니다.")
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
    if _parse_date(target_date, "target_date") < clock.today():
        raise bad_request("목표 완료 희망일은 오늘 이후여야 합니다.", {"field": "target_date"})


def _validate_week_start(value: str) -> None:
    if _parse_date(value, "plan_week_start").weekday() != 0:
        raise bad_request("계획 주간 시작일은 월요일이어야 합니다.", {"field": "plan_week_start"})


def _validate_week_within_target(week_start: date, target_date: date) -> None:
    """A week the plan names must not begin after the target date (the plan covers every week up to it)."""
    if week_start > target_date:
        raise bad_request("계획 주간이 목표 완료 희망일을 넘습니다.", {"field": "plan_week_start"})


def _resolve_plan_period(start_date_str: str, plan_week_start: Optional[str], target_date: date) -> tuple[date, date]:
    """F1: the user picks any start date (today or later, KST); the FIRST plan week is the Monday
    week that contains it, derived here via clock.py (Phase 5F: the plan then runs through the week
    of target_date, see schedule.week_count). A caller-supplied plan_week_start is only accepted
    when it agrees with that derived Monday. target_date may equal start_date.
    Returns (start_date, first_week_start)."""
    start = _parse_date(start_date_str, "start_date")
    if start < clock.today():
        raise bad_request("학습 시작일은 오늘 이후여야 합니다.", {"field": "start_date"})
    if target_date < start:
        raise bad_request("목표 완료 희망일은 학습 시작일 이후여야 합니다.", {"field": "target_date"})
    week_start = clock.week_monday(start)
    if plan_week_start is not None and _parse_date(plan_week_start, "plan_week_start") != week_start:
        raise bad_request(
            "plan_week_start가 학습 시작일이 속한 주의 월요일과 다릅니다.", {"field": "plan_week_start"}
        )
    _validate_week_within_target(week_start, target_date)
    return start, week_start


PLAN_TASKS_MIN = 3
PLAN_TASKS_MAX = 60


def _goal_available_minutes(goal: dict[str, Any]) -> int:
    """Phase 5F: the time budget of a whole learning = weekly minutes x the weeks from the week of
    its start date to the week of its target date (both included)."""
    weeks = schedule.week_count(_goal_start_date(goal), date.fromisoformat(goal["target_date"]))
    return schedule.available_minutes(goal["weekly_hours"], weeks)


def _validate_task_time_budget(
    db,
    uid: str,
    goal: dict[str, Any],
    estimated_minutes: int,
    exclude_task_id: Optional[str] = None,
) -> None:
    """Shared by POST /api/tasks and PATCH /api/tasks/{id}: the budget AI-generated plans follow
    (all tasks of the learning <= available minutes, Phase 5F) must also apply to tasks created or
    edited by hand, so the manual path can't bypass it. After confirmation the schedule is frozen:
    editing minutes never re-places the following tasks (docs/phase5f_design.md section 3)."""
    existing = db.find("tasks", user_id=uid, goal_id=goal["id"])
    total = sum(t["estimated_minutes"] for t in existing if t["id"] != exclude_task_id) + estimated_minutes
    available = _goal_available_minutes(goal)
    if total > available:
        raise bad_request(
            f"이 학습의 과업 총 예상 시간({insight_rules.format_minutes(total)})이 가용 시간"
            f"({insight_rules.format_minutes(available)})을 초과합니다.",
            {"field": "estimated_minutes"},
        )


def _normalized_title(title: str) -> str:
    return " ".join(title.split()).casefold()


def _duplicate_title_count(titles: list[str]) -> int:
    """How many titles repeat an earlier one (whitespace folded, case ignored)."""
    return len(titles) - len({_normalized_title(t) for t in titles})


def _goal_start_date(goal: dict[str, Any]) -> date:
    """Read-side start_date of a goal (Phase 5B).

    Goals saved before Phase 5B have no start_date; for them the Asia/Seoul calendar date of
    created_at stands in. Stored data is not migrated - every reader goes through here.
    """
    stored = goal.get("start_date")
    if stored:
        return date.fromisoformat(stored)
    return clock.date_from_utc_iso(goal["created_at"])


def _goal_out(goal: dict[str, Any]) -> dict[str, Any]:
    return {**goal, "start_date": _goal_start_date(goal).isoformat()}


MAX_CONCURRENT_GOALS = 2


def _check_goal_period_overlap(db, uid: str, start: date, target: date) -> None:
    """Phase 5B/R1: at most MAX_CONCURRENT_GOALS (2) active goals may run on any single day.

    A new goal's [start, target] (both ends inclusive) is rejected when, on at least one day of
    it, the user already has MAX_CONCURRENT_GOALS status="active" goals in progress; completed
    and archived goals are not counted. One overlapping goal is fine, and two goals that only
    touch the new period on different days are fine too.

    Called by both goal-creation paths (POST /api/plan/confirm, POST /api/goals) after all
    other validation and right before the first write, so a rejection saves nothing.
    Implementation: split the new period at every boundary of an overlapping goal (its start
    and its end + 1 day, clipped to the new period) and count the goals covering each piece.
    """
    spans = []
    for other in db.find("goals", user_id=uid, status="active"):
        other_start = _goal_start_date(other)
        other_target = date.fromisoformat(other["target_date"])
        if start <= other_target and other_start <= target:
            spans.append((other_start, other_target, other))
    if len(spans) < MAX_CONCURRENT_GOALS:
        return

    one_day = timedelta(days=1)
    cuts = {start, target + one_day}
    for other_start, other_target, _ in spans:
        cuts.add(max(other_start, start))
        cuts.add(min(other_target, target) + one_day)
    ordered = sorted(cuts)

    conflict_from: Optional[date] = None
    conflict_to: Optional[date] = None
    for piece_start, next_cut in zip(ordered, ordered[1:]):
        piece_end = next_cut - one_day
        busy = sum(1 for s, t, _ in spans if s <= piece_start and piece_end <= t)
        if busy >= MAX_CONCURRENT_GOALS:
            if conflict_from is None:
                conflict_from = piece_start
            conflict_to = piece_end
        elif conflict_from is not None:
            break  # the first continuous crowded stretch is enough to report
    if conflict_from is None or conflict_to is None:
        return

    overlaps = [
        {
            "goal_id": other["id"],
            "course": other["course"],
            "start_date": other_start.isoformat(),
            "target_date": other_target.isoformat(),
        }
        for other_start, other_target, other in spans
        if other_start <= conflict_to and conflict_from <= other_target
    ]
    overlaps.sort(key=lambda o: (o["start_date"], o["target_date"]))
    listing = ", ".join(f"'{o['course']}'({o['start_date']} ~ {o['target_date']})" for o in overlaps)
    count_label = "두" if len(overlaps) == 2 else str(len(overlaps))
    raise api_error(
        status.HTTP_409_CONFLICT,
        "GOAL_PERIOD_OVERLAP",
        f"한 날에 진행할 수 있는 학습은 최대 {MAX_CONCURRENT_GOALS}개예요. "
        f"{conflict_from.isoformat()} ~ {conflict_to.isoformat()} 에 이미 {listing} {count_label} 학습이 있습니다. "
        "학습 시작일이나 목표 완료일을 조정해 주세요.",
        # The flat fields mirror the first overlap for clients written before `overlaps` existed.
        {
            **overlaps[0],
            "overlaps": overlaps,
            "max_concurrent": MAX_CONCURRENT_GOALS,
            "conflict_from": conflict_from.isoformat(),
            "conflict_to": conflict_to.isoformat(),
        },
    )


def _goal_recency_key(goal: dict[str, Any]) -> tuple[str, str]:
    """Newest registration sorts highest. created_at has one-second resolution, so goals
    registered in the same second fall back to the later schedule. Shared by GET /api/goals
    and the active-goal fallback below so both agree on what "most recent" means."""
    return goal["created_at"], goal["start_date"]


def _fall_back_active_goal(db, uid: str, leaving_goal_id: str) -> None:
    """P5B-1: if `leaving_goal_id` is the user's current learning (active_goal_id) and it is
    being deleted or is no longer status="active", move active_goal_id to the most recently
    registered remaining active goal - null only when none is left. Any other goal leaving
    leaves active_goal_id untouched."""
    user = db.get("users", uid)
    if not user or user.get("active_goal_id") != leaving_goal_id:
        return
    remaining = [
        _goal_out(g) for g in db.find("goals", user_id=uid, status="active") if g["id"] != leaving_goal_id
    ]
    fallback = max(remaining, key=_goal_recency_key)["id"] if remaining else None
    db.update("users", uid, {"active_goal_id": fallback})


def _register_new_goal_as_recent(db, uid: str, goal_id: str) -> None:
    """The most recent learning is users.active_goal_id; a newly registered goal becomes it."""
    if db.get("users", uid):
        db.update("users", uid, {"active_goal_id": goal_id})


def _delete_task_children(db, uid: str, task_id: str) -> None:
    db.delete_where("reflections", user_id=uid, task_id=task_id)
    db.delete_where("study_logs", user_id=uid, task_id=task_id)


def _study_log_stats(db, uid: str, task_id: str) -> tuple[int, int]:
    logs = db.find("study_logs", user_id=uid, task_id=task_id)
    return len(logs), sum(log["minutes"] for log in logs)


def _with_task_stats(
    task: dict[str, Any], record_count: int, total_minutes: int, timeline_start: Optional[int] = None
) -> dict[str, Any]:
    start = timeline_start if timeline_start is not None else task.get("timeline_start_minutes") or 0
    return {**task, "record_count": record_count, "total_minutes": total_minutes, "timeline_start_minutes": start}


def _timeline_starts_of(db, uid: str, tasks: list[dict[str, Any]]) -> dict[str, int]:
    """timeline_start_minutes for the given tasks. A learning saved before Phase 5F has tasks without
    the field; its starts are accumulated from all of its tasks in order_index order (no error)."""
    starts = {t["id"]: t["timeline_start_minutes"] for t in tasks if t.get("timeline_start_minutes") is not None}
    for goal_id in {t["goal_id"] for t in tasks if t.get("timeline_start_minutes") is None}:
        starts.update(schedule.timeline_starts(db.find("tasks", user_id=uid, goal_id=goal_id)))
    return starts


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


ROLE_IDEA_MAX_LENGTH = 40


def _validate_ai_role_ideas(parsed: AIRoleIdeas) -> None:
    roles = [r.strip() for r in parsed.suggested_roles]
    if not 3 <= len(roles) <= 5:
        raise ValueError("직무·목표 예시는 3개 이상 5개 이하여야 합니다.")
    if any(not r for r in roles):
        raise ValueError("직무·목표 예시가 비어 있습니다.")
    if any(len(r) > ROLE_IDEA_MAX_LENGTH for r in roles):
        raise ValueError(f"직무·목표 예시는 {ROLE_IDEA_MAX_LENGTH}자 이하여야 합니다.")
    if len({r.lower() for r in roles}) != len(roles):
        raise ValueError("직무·목표 예시에 중복이 있습니다.")


def _validate_ai_plan(parsed: AIPlanDraft, max_total_minutes: int) -> None:
    """Server rules for the whole-course plan (Phase 5F). A violation is rejected and retried,
    never patched; the feedback carries counts only, never task text."""
    if not (PLAN_TASKS_MIN <= len(parsed.tasks) <= PLAN_TASKS_MAX):
        problem = f"과제는 {PLAN_TASKS_MIN}개 이상 {PLAN_TASKS_MAX}개 이하여야 합니다. (이번 시도 {len(parsed.tasks)}개)"
        raise AIRetryFeedback(problem, feedback={"validation_error": problem})
    total = sum(t.estimated_minutes for t in parsed.tasks)
    if total > max_total_minutes:
        # P4-9: tell the next retry attempt how far over budget this one was, instead
        # of just repeating the same instruction the model already failed to follow.
        raise AIRetryFeedback(
            "총 예상 시간이 가용 시간을 초과합니다.",
            feedback={"previous_total_minutes": total, "max_total_minutes": max_total_minutes},
        )
    duplicates = _duplicate_title_count([t.title for t in parsed.tasks])
    if duplicates:
        problem = f"과제 제목이 서로 달라야 합니다. 중복된 제목이 {duplicates}개 있습니다."
        raise AIRetryFeedback(problem, feedback={"validation_error": problem})
    for t in parsed.tasks:
        if not t.title.strip() or not t.description.strip():
            raise ValueError("과업 제목/설명이 비어 있습니다.")
    if not parsed.advice_title.strip() or not parsed.advice_content.strip():
        raise ValueError("조언 제목/내용이 비어 있습니다.")


# 1a. Role / goal ideas - a light, button-triggered AI call (F5). Output is only the role list.
@app.post(
    "/api/path/ideas",
    response_model=RoleIdeasResponse,
    tags=["path"],
    summary="1단계 보조: 분야 기준 대표 직무·목표 예시 3~5개 (참고용)",
)
def suggest_role_ideas(
    payload: RoleIdeasRequest,
    uid: str = Depends(require_consented_uid),
    ai: AIClient = Depends(get_ai_client),
):
    try:
        parsed = ai.generate(
            ROLE_IDEAS_SYSTEM_PROMPT, {"field": payload.field}, AIRoleIdeas, validator=_validate_ai_role_ideas
        )
    except (AITimeoutError, AISchemaError, AIUnavailableError) as exc:
        raise _ai_error_response(exc)
    return RoleIdeasResponse(field=payload.field, suggested_roles=[r.strip() for r in parsed.suggested_roles])


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
    summary="2단계: 전체 학습 과정 과업·조언·참고자료 생성 (초안, 미저장). 주차 배치는 서버가 계산",
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

    start_date, week_start = _resolve_plan_period(payload.start_date, payload.plan_week_start, target_date)
    weeks = schedule.week_count(start_date, target_date)
    weekly_minutes = payload.weekly_hours * 60
    max_total_minutes = schedule.available_minutes(payload.weekly_hours, weeks)
    user_payload = {
        "field": payload.field,
        "course": payload.course,
        "selected_role": payload.selected_role,
        "current_level_name": payload.current_level_name,
        "current_level_description": payload.current_level_description,
        "target_level_name": payload.target_level_name,
        "target_level_description": payload.target_level_description,
        "weekly_hours": payload.weekly_hours,
        "weekly_minutes": weekly_minutes,
        "week_count": weeks,
        "max_total_minutes": max_total_minutes,
    }
    try:
        # A whole-course answer is long: this call alone gets a longer timeout and output budget.
        with call_limits(plan_timeout_seconds(), plan_max_output_tokens()):
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
        ResourceReferenceItem(
            title=m["title"],
            category=m["category"],
            source_name=m.get("source_name"),
            url=m["url"],
            is_verified=bool(m.get("verified")),
        )
        for m in matches
    ]
    references_notice = None if matches else no_match_notice(payload.field)

    placements = schedule.place_tasks([t.estimated_minutes for t in draft.tasks], weekly_minutes)
    tasks = [
        WeeklyTaskPlanItem(
            title=t.title.strip(),
            description=t.description,
            estimated_minutes=t.estimated_minutes,
            suggested_weekday=p["suggested_weekday"],
            plan_week_start=schedule.week_start_date(week_start, p["start_week_index"]).isoformat(),
            timeline_start_minutes=p["timeline_start_minutes"],
        )
        for t, p in zip(draft.tasks, placements)
    ]
    return PlanGenerateResponse(
        plan_week_start=week_start.isoformat(),
        plan_week_end=clock.week_sunday(target_date).isoformat(),
        week_count=weeks,
        available_minutes=max_total_minutes,
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
            return PlanConfirmResponse(goal=_goal_out(existing_goal), tasks=existing_tasks)

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
    if payload.advice_title is not None:
        # Client-supplied text (the server cannot re-verify it against an AI result); shown only
        # to this user on their own screen and never logged.
        goal_data["advice_title"] = payload.advice_title
        goal_data["advice_content"] = payload.advice_content
    # Validate everything before writing anything, so a rejected request never leaves a
    # partial save (the store layer has no multi-document transaction to roll back).
    _validate_goal_levels(goal_data)
    _validate_target_date_not_past(goal_data["target_date"])
    target_date = _parse_date(payload.target_date, "target_date")
    start_date, week_start = _resolve_plan_period(payload.start_date, payload.plan_week_start, target_date)
    # Phase 5F: the client's task list is the ordered, edited plan. Its weeks and timeline are never
    # trusted - the server places the tasks again below.
    if not (PLAN_TASKS_MIN <= len(payload.tasks) <= PLAN_TASKS_MAX):
        raise bad_request(f"과제는 {PLAN_TASKS_MIN}개 이상 {PLAN_TASKS_MAX}개 이하여야 합니다.", {"field": "tasks"})
    if _duplicate_title_count([t.title for t in payload.tasks]):
        raise bad_request("과제 제목은 서로 달라야 합니다. 같은 제목의 과제가 있습니다.", {"field": "tasks"})
    total_minutes = sum(t.estimated_minutes for t in payload.tasks)
    weekly_minutes = payload.weekly_hours * 60
    available = schedule.available_minutes(payload.weekly_hours, schedule.week_count(start_date, target_date))
    if total_minutes > available:
        raise bad_request(
            f"과업 총 예상 시간({insight_rules.format_minutes(total_minutes)})이 가용 시간"
            f"({insight_rules.format_minutes(available)})을 초과합니다.",
            {"field": "tasks"},
        )
    _check_goal_period_overlap(db, uid, start_date, target_date)
    placements = schedule.place_tasks([t.estimated_minutes for t in payload.tasks], weekly_minutes)

    now = _now_iso()
    goal = db.create(
        "goals",
        {
            **goal_data,
            "start_date": start_date.isoformat(),
            "user_id": uid,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )
    _register_new_goal_as_recent(db, uid, goal["id"])

    tasks = []
    for idx, (t, placed) in enumerate(zip(payload.tasks, placements)):
        task_data = t.model_dump()
        task_data["description"] = task_data["description"] or ""
        # a weekday the user picked is kept; none/absent gets the server's start-position default
        task_data["suggested_weekday"] = (
            task_data["suggested_weekday"] if task_data["suggested_weekday"] not in (None, "none") else placed["suggested_weekday"]
        )
        task = db.create(
            "tasks",
            {
                **task_data,
                "goal_id": goal["id"],
                "user_id": uid,
                "plan_week_start": schedule.week_start_date(week_start, placed["start_week_index"]).isoformat(),
                "timeline_start_minutes": placed["timeline_start_minutes"],
                "status": "pending",
                "order_index": idx,
                "created_at": now,
                "updated_at": now,
            },
        )
        tasks.append(task)
    return PlanConfirmResponse(goal=_goal_out(goal), tasks=tasks)


# 3. Goals CRUD
@app.get("/api/goals", response_model=List[GoalResponse], tags=["goals"], summary="사용자의 학습 목표 목록 조회")
def list_goals(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    # Newest registration first. created_at has one-second resolution, so goals registered in
    # the same second fall back to the later schedule first.
    goals = [_goal_out(g) for g in db.find("goals", user_id=uid)]
    return sorted(goals, key=_goal_recency_key, reverse=True)


@app.post("/api/goals", response_model=GoalResponse, status_code=status.HTTP_201_CREATED, tags=["goals"], summary="학습 목표 저장")
def create_goal(payload: GoalCreateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    data = payload.model_dump()
    _validate_goal_levels(data)
    _validate_target_date_not_past(data["target_date"])
    start = clock.week_monday(clock.today())
    _check_goal_period_overlap(db, uid, start, _parse_date(data["target_date"], "target_date"))
    now = _now_iso()
    goal = db.create(
        "goals",
        {**data, "start_date": start.isoformat(), "user_id": uid, "status": "active", "created_at": now, "updated_at": now},
    )
    _register_new_goal_as_recent(db, uid, goal["id"])
    return _goal_out(goal)


@app.get("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 상세 조회")
def get_goal(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    return _goal_out(_get_owned(db, "goals", goal_id, uid))


@app.get(
    "/api/goals/{goal_id}/references",
    response_model=GoalReferencesResponse,
    tags=["goals"],
    summary="학습에 연결된 검토 참고자료 (읽기 전용, plan/generate 와 같은 분야 일치 규칙)",
)
def get_goal_references(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", goal_id, uid)
    matches = match_references(goal["field"], goal["course"])
    references = [
        ResourceReferenceItem(
            title=m["title"],
            category=m["category"],
            source_name=m.get("source_name"),
            url=m["url"],
            is_verified=bool(m.get("verified")),
        )
        for m in matches
    ]
    return GoalReferencesResponse(
        references=references,
        references_notice=None if matches else no_match_notice(goal["field"]),
        search_links=[SearchLinkItem(**link) for link in search_links(goal["field"], goal["course"])],
    )


@app.patch("/api/goals/{goal_id}", response_model=GoalResponse, tags=["goals"], summary="목표 수정")
def update_goal(goal_id: str, payload: GoalUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", goal_id, uid)
    changes = _changes(payload)
    _validate_goal_levels({**goal, **changes})
    if "target_date" in changes:
        _validate_target_date_not_past(changes["target_date"])
    # Phase 5B (user decision): changing an existing goal's schedule is deliberately NOT
    # checked for overlap with other active goals. Only goal creation is.
    updated = db.update("goals", goal_id, {**changes, "updated_at": _now_iso()})
    if updated["status"] != "active":
        _fall_back_active_goal(db, uid, goal_id)  # P5B-1: completed/archived goal can't stay "current"
    return _goal_out(updated)


@app.delete("/api/goals/{goal_id}", tags=["goals"], summary="목표 삭제 (하위 과제·기록·회고 포함)")
def delete_goal(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    _get_owned(db, "goals", goal_id, uid)
    for task in db.find("tasks", user_id=uid, goal_id=goal_id):
        _delete_task_children(db, uid, task["id"])
        _clear_active_timer_for_task(db, uid, task["id"])  # P5-2: a goal delete must not strand a timer
    db.delete_where("tasks", user_id=uid, goal_id=goal_id)
    db.delete("insights", goal_id)  # Phase 6B: one insight per learning, removed with it
    db.delete("goals", goal_id)
    _fall_back_active_goal(db, uid, goal_id)
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
    starts = _timeline_starts_of(db, uid, sorted_tasks)

    # One query for all of this user's logs (not one per task) - 5.9's "쿼리 수를 줄인다".
    stats: dict[str, tuple[int, int]] = {}
    for log in db.find("study_logs", user_id=uid):
        count, minutes = stats.get(log["task_id"], (0, 0))
        stats[log["task_id"]] = (count + 1, minutes + log["minutes"])
    return [_with_task_stats(t, *stats.get(t["id"], (0, 0)), starts.get(t["id"])) for t in sorted_tasks]


@app.post("/api/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED, tags=["tasks"], summary="학습 과제 생성")
def create_task(payload: TaskCreateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", payload.goal_id, uid)
    _validate_week_start(payload.plan_week_start)
    _validate_week_within_target(_parse_date(payload.plan_week_start, "plan_week_start"), _parse_date(goal["target_date"], "target_date"))
    _validate_task_time_budget(db, uid, goal, payload.estimated_minutes)
    now = _now_iso()
    data = payload.model_dump()
    data["description"] = data["description"] or ""
    data["suggested_weekday"] = data["suggested_weekday"] or "none"
    data["order_index"] = data["order_index"] or 0
    # A hand-made task goes to the end of the learning's timeline (or to the start of the plan week
    # it names, if that is later); the other tasks are never moved.
    existing = db.find("tasks", user_id=uid, goal_id=goal["id"])
    existing_starts = schedule.timeline_starts(existing)
    end = max((existing_starts[t["id"]] + t["estimated_minutes"] for t in existing), default=0)
    week_index = max(0, (_parse_date(payload.plan_week_start, "plan_week_start") - clock.week_monday(_goal_start_date(goal))).days // 7)
    data["timeline_start_minutes"] = max(end, week_index * goal["weekly_hours"] * 60)
    task = db.create("tasks", {**data, "user_id": uid, "status": "pending", "created_at": now, "updated_at": now})
    return _with_task_stats(task, 0, 0)


@app.patch("/api/tasks/{task_id}", response_model=TaskResponse, tags=["tasks"], summary="과제 상태/추천요일 수정")
def update_task(task_id: str, payload: TaskUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    task = _get_owned(db, "tasks", task_id, uid)
    changes = _changes(payload)
    if "estimated_minutes" in changes:
        goal = _get_owned(db, "goals", task["goal_id"], uid)
        _validate_task_time_budget(db, uid, goal, changes["estimated_minutes"], exclude_task_id=task_id)
    updated = db.update("tasks", task_id, {**changes, "updated_at": _now_iso()})
    return _with_task_stats(updated, *_study_log_stats(db, uid, task_id), _timeline_starts_of(db, uid, [updated]).get(task_id))


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
    goal_id: Optional[str] = Query(None, description="목표 ID 필터 (복수 학습 화면용)"),
    period: str = Query("week", description="조회 기간 (week | all)"),
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    if period not in ("week", "all"):
        raise bad_request("period는 week 또는 all이어야 합니다.", {"field": "period"})
    filters: dict[str, Any] = {"user_id": uid}
    if task_id:
        filters["task_id"] = task_id
    if goal_id:
        filters["goal_id"] = goal_id
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
RECENT_REFLECTIONS_LIMIT = 5


def _learning_context(db, uid: str, keywords: Optional[str]):
    """What the tutor (and GET /api/data/summary) knows about the user: every *active* learning
    (not only users.active_goal_id) and at most RECENT_REFLECTIONS_LIMIT reflections.

    Reflection rule (documented for 6.8): only reflections of tasks that belong to an active
    learning are considered; those matching the question keywords come first, the rest are
    filled newest first (study date, then creation time). Reflections are read from storage on
    every call, so an edited reflection shows its latest text and a deleted one is gone.
    One user-scoped read per collection, grouped in memory.
    """
    goals = _active_goals_sorted(db, uid)
    tasks_by_goal, logs_by_goal = _tasks_and_logs_by_goal(db, uid)
    user = db.get("users", uid) or {}
    current = next((g for g in goals if g["id"] == user.get("active_goal_id")), None)

    lines = []
    for g in goals:
        done, total, pct = _goal_progress(tasks_by_goal.get(g["id"], []))
        lines.append(
            f"{g['field']} · {g['course']} | 현재 {g['current_level_name']} → 목표 {g['target_level_name']} "
            f"| 진행률 {pct}% ({done}/{total}개 과제)"
        )
    summary = "\n".join(lines) if lines else "진행 중인 학습이 없습니다."

    active_ids = {g["id"] for g in goals}
    task_by_id = {t["id"]: t for gid, ts in tasks_by_goal.items() if gid in active_ids for t in ts}
    log_by_id = {log["id"]: log for logs in logs_by_goal.values() for log in logs}
    query_tokens = rag.topic_tokens(keywords or "")

    candidates = []
    for r in db.find("reflections", user_id=uid):
        task = task_by_id.get(r["task_id"])
        if task is None:
            continue
        log = log_by_id.get(r["study_log_id"])
        study_date = log["study_date"] if log else r["created_at"][:10]
        haystack = " ".join([r["content"], " ".join(r.get("tags", [])), task["title"]])
        matched = rag.overlaps(query_tokens, haystack)
        candidates.append((matched, study_date, r["created_at"], r, task))
    candidates.sort(key=lambda c: (c[0], c[1], c[2]), reverse=True)
    reflections = [
        {
            "id": r["id"],
            "study_date": study_date,
            "task_title": task["title"],
            "content": r["content"],
            "tags": r.get("tags", []),
        }
        for _, study_date, _, r, task in candidates[:RECENT_REFLECTIONS_LIMIT]
    ]
    return summary, (current or {}).get("field"), (current or {}).get("course"), reflections


@app.get(
    "/api/data/summary",
    response_model=LearningDataSummaryResponse,
    tags=["summary"],
    summary="AI 튜터 컨텍스트용 학습 요약 및 최근 회고(최대 5건) 조회",
)
def get_data_summary(
    keywords: Optional[str] = Query(None, max_length=200, description="질문 관련 회고 검색 키워드 (최대 200자)"),
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    summary, active_field, active_course, reflections = _learning_context(db, uid, keywords)
    return LearningDataSummaryResponse(
        user_id=uid,
        learning_summary=summary,
        active_field=active_field,
        active_course=active_course,
        recent_reflections=reflections,
    )


DASHBOARD_WEEKDAY_LABELS = ("월", "화", "수", "목", "금", "토", "일")
DASHBOARD_INSIGHT_MIN_RECORDS = 3
DASHBOARD_INSIGHT_MIN_REFLECTIONS = 1
# P5-4: today_tasks shows at most this many items, ordered incomplete-first (today's
# suggested weekday, then this week's remaining order_index), with completed tasks
# filling any leftover slots. If a week has more than this many incomplete tasks,
# completed ones are the first to be cut.
TODAY_TASKS_LIMIT = 5


def _tasks_and_logs_by_goal(db, uid: str) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    tasks: dict[str, list[dict[str, Any]]] = {}
    for t in db.find("tasks", user_id=uid):
        tasks.setdefault(t["goal_id"], []).append(t)
    logs: dict[str, list[dict[str, Any]]] = {}
    for log in db.find("study_logs", user_id=uid):
        logs.setdefault(log["goal_id"], []).append(log)
    return tasks, logs


def _active_goals_sorted(db, uid: str) -> list[dict[str, Any]]:
    """The user's status="active" goals, earliest schedule first. Shared by the dashboard's
    goals_overview and the analytics screen so their numbers can't diverge."""
    return sorted(
        (_goal_out(g) for g in db.find("goals", user_id=uid, status="active")),
        key=lambda g: (g["start_date"], g["created_at"]),
    )


def _goal_progress(tasks: list[dict[str, Any]]) -> tuple[int, int, int]:
    total = len(tasks)
    done = sum(1 for t in tasks if t["status"] == "completed")
    return done, total, (round(done / total * 100) if total else 0)


def _goals_overview(db, uid: str, tasks_by_goal: dict[str, list[dict[str, Any]]]) -> list[GoalOverviewItem]:
    items = []
    for g in _active_goals_sorted(db, uid):
        done, total, pct = _goal_progress(tasks_by_goal.get(g["id"], []))
        items.append(
            GoalOverviewItem(
                goal_id=g["id"],
                course=g["course"],
                start_date=g["start_date"],
                target_date=g["target_date"],
                completed_task_count=done,
                total_task_count=total,
                progress_percentage=pct,
            )
        )
    return items


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
        # are the normal "nothing to show yet" case, not an error (always 200). Other active
        # goals may still exist, so the overview is filled in.
        empty = _empty_dashboard_summary(week_start, today)
        empty.goals_overview = _goals_overview(db, user["uid"], _tasks_and_logs_by_goal(db, user["uid"])[0])
        return empty

    uid = user["uid"]
    # One read of the user's tasks/logs, grouped per goal, serves both the recent-learning
    # block and goals_overview (no per-goal queries).
    all_tasks, all_logs = _tasks_and_logs_by_goal(db, uid)
    tasks = all_tasks.get(goal_id, [])
    total_task_count = len(tasks)
    completed_task_count = sum(1 for t in tasks if t["status"] == "completed")
    progress_percentage = round(completed_task_count / total_task_count * 100) if total_task_count else 0

    logs = all_logs.get(goal_id, [])
    weekly_logs = [log for log in logs if clock.is_within_week(date.fromisoformat(log["study_date"]), week_start)]
    weekly_study_minutes = sum(log["minutes"] for log in weekly_logs)

    log_counts_by_task: dict[str, int] = {}
    for log in logs:
        log_counts_by_task[log["task_id"]] = log_counts_by_task.get(log["task_id"], 0) + 1

    # Phase 5F: "this week's tasks" are those with scheduled minutes this week - tasks that start
    # this week and tasks continuing from an earlier week (their share of this week).
    weekly_minutes = goal["weekly_hours"] * 60
    in_week = schedule.tasks_in_week(tasks, clock.week_monday(_goal_start_date(goal)), weekly_minutes, week_start)
    this_week_tasks = [r["task"] for r in in_week]
    week_minutes_by_task = {r["task"]["id"]: r["week_minutes"] for r in in_week}
    continued_ids = {r["task"]["id"] for r in in_week if not r["starts_here"]}
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
            week_minutes=week_minutes_by_task[t["id"]],
            continued=t["id"] in continued_ids,
        )
        for t in ordered[:TODAY_TASKS_LIMIT]
    ]
    week_scheduled_minutes = sum(week_minutes_by_task.values())
    today_scheduled_minutes = sum(week_minutes_by_task[t["id"]] for t in this_week_tasks if t["suggested_weekday"] == today_weekday)
    all_tasks_completed_this_week = bool(this_week_tasks) and not incomplete

    # Phase 6B: the dashboard only *shows* the saved insight (or says what to do); it never calls the AI.
    inputs = _insight_inputs(logs, tasks, db.find("reflections", user_id=uid), today)
    saved = db.get("insights", goal_id)
    if saved is not None and saved.get("user_id") == uid:
        insight = AIInsightSummary(text=saved["summary"], notice=INSIGHT_NOTICE, is_insufficient=False)
    elif inputs["sufficient"]:
        insight = AIInsightSummary(text="실행 기록 화면에서 인사이트를 만들어 보세요.", notice="", is_insufficient=False)
    else:
        insight = AIInsightSummary(text="기록과 회고를 더 남기면 인사이트를 볼 수 있어요.", notice="", is_insufficient=True)

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
        week_scheduled_minutes=week_scheduled_minutes,
        today_scheduled_minutes=today_scheduled_minutes,
        plan_total_minutes=sum(t["estimated_minutes"] for t in tasks),
        plan_available_minutes=_goal_available_minutes(goal),
        weekly_hits=weekly_hits,
        insight=insight,
        goals_overview=_goals_overview(db, uid, all_tasks),
    )


# 6b. Analytics (Phase 5B) - read-only, no AI call
@app.get(
    "/api/analytics/overview",
    response_model=AnalyticsOverviewResponse,
    tags=["summary"],
    summary="진행 중인 학습별 일정·진행률·이번 주 요일별 학습 분 (읽기 전용)",
)
def get_analytics_overview(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    week_start = clock.week_monday(clock.today())
    tasks_by_goal, logs_by_goal = _tasks_and_logs_by_goal(db, uid)
    goals = []
    for g in _active_goals_sorted(db, uid):
        done, total, pct = _goal_progress(tasks_by_goal.get(g["id"], []))
        minutes_by_day = [0] * 7
        for log in logs_by_goal.get(g["id"], []):
            day = date.fromisoformat(log["study_date"])
            if clock.is_within_week(day, week_start):
                minutes_by_day[(day - week_start).days] += log["minutes"]
        goals.append(
            AnalyticsGoalItem(
                goal_id=g["id"],
                course=g["course"],
                start_date=g["start_date"],
                target_date=g["target_date"],
                completed_task_count=done,
                total_task_count=total,
                progress_percentage=pct,
                weekly_minutes_by_day=minutes_by_day,
            )
        )
    return AnalyticsOverviewResponse(
        week_start=week_start.isoformat(), week_end=clock.week_sunday(week_start).isoformat(), goals=goals
    )


# 7. Conversations (AI Tutor - 단일화된 튜터 호출 엔드포인트)
def _current_learning(db, uid: str) -> tuple[Optional[str], Optional[str]]:
    """(field, course) of the user's current learning when it is still active, else (None, None)."""
    user = db.get("users", uid) or {}
    goal = db.get("goals", user["active_goal_id"]) if user.get("active_goal_id") else None
    if not goal or goal.get("user_id") != uid or goal.get("status") != "active":
        return None, None
    return goal["field"], goal["course"]


def _decorated_messages(messages: list[dict], current: tuple[Optional[str], Optional[str]]) -> list[dict]:
    """Messages with the response-time links; each answer is ordered against the question before it."""
    out, question = [], ""
    for m in messages:
        out.append(tutor.decorate(m, *current, question))
        if m.get("role") == "user":
            question = m.get("content", "")
    return out


def _conversation_out(conv: dict[str, Any], current: tuple[Optional[str], Optional[str]] = (None, None)) -> dict[str, Any]:
    return {
        "id": conv["id"],
        "user_id": conv["user_id"],
        "title": conv["title"],
        "messages": _decorated_messages(conv.get("messages", []), current),
        "created_at": conv["created_at"],
        "updated_at": conv["updated_at"],
    }


@app.post(
    "/api/conversations",
    response_model=ConversationDetailResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["conversations"],
    summary="새 튜터 대화 세션 생성 (client_request_id 로 멱등)",
)
def create_conversation(
    response: Response,
    payload: Optional[ConversationCreateRequest] = None,
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
):
    payload = payload or ConversationCreateRequest()
    existing = _find_by_client_request_id(db, "conversations", uid, payload.client_request_id)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return _conversation_out(existing)
    now = _now_iso()
    conv = db.create(
        "conversations",
        {
            "user_id": uid,
            "title": (payload.title or "").strip() or tutor.DEFAULT_TITLE,
            "messages": [],
            "client_request_id": payload.client_request_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    return _conversation_out(conv)


@app.get(
    "/api/conversations",
    response_model=List[ConversationListItem],
    tags=["conversations"],
    summary="최근 대화 세션 목록 조회 (최근 갱신순, 최대 50건, 메시지 본문 제외)",
)
def list_conversations(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    convs = sorted(db.find("conversations", user_id=uid), key=lambda c: c["updated_at"], reverse=True)
    return convs[: tutor.CONVERSATION_LIST_LIMIT]


@app.get(
    "/api/conversations/{conversation_id}",
    response_model=ConversationDetailResponse,
    tags=["conversations"],
    summary="대화 세션 상세 및 전체 메시지 이력 조회",
)
def get_conversation(conversation_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    return _conversation_out(_get_owned(db, "conversations", conversation_id, uid), _current_learning(db, uid))


def _stored_pair(conv: dict[str, Any], client_request_id: str):
    """The (user, assistant) messages already saved for this idempotency key, if any."""
    messages = conv.get("messages", [])
    for i, m in enumerate(messages):
        if m["role"] == "user" and m.get("client_request_id") == client_request_id and i + 1 < len(messages):
            return m, messages[i + 1]
    return None


@app.post(
    "/api/conversations/{conversation_id}/messages",
    response_model=SendMessageResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["conversations"],
    summary="튜터 질의 전송 및 응답 수신 (학습 요약·회고 + 검토된 자료 검색, AI 1회 호출, 멱등)",
)
def send_message(
    conversation_id: str,
    payload: SendMessageRequest,
    response: Response,
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
):
    conv = _get_owned(db, "conversations", conversation_id, uid)

    # Idempotency first: a retry of an already saved question returns it instead of asking again.
    stored = _stored_pair(conv, payload.client_request_id)
    if stored is not None:
        response.status_code = status.HTTP_200_OK
        return SendMessageResponse(
            user_message=stored[0],
            assistant_message=tutor.decorate(stored[1], *_current_learning(db, uid), stored[0].get("content", "")),
            conversation_title=conv["title"],
            refused=bool(stored[1].get("refused")),
        )

    history = conv.get("messages", [])
    if len(history) + 2 > tutor.MAX_MESSAGES_PER_CONVERSATION:
        raise api_error(
            status.HTTP_409_CONFLICT,
            "CONVERSATION_FULL",
            "이 대화가 너무 길어졌어요. 새 대화를 시작해 주세요.",
        )

    question = payload.content.strip()
    # 1) summary + reflections (all active learnings), 2) reference search, 3) one AI call.
    summary, current_field, current_course, reflections = _learning_context(db, uid, question)
    retrieved = rag.search(question)
    user_payload = {
        "question": question,
        "learning_summary": summary,
        "recent_reflections": [
            {"study_date": r["study_date"], "task_title": r["task_title"], "content": r["content"], "tags": r["tags"]}
            for r in reflections
        ],
        "reference_chunks": [
            {"source_id": c.doc_id, "chunk_id": c.chunk_id, "title": c.title, "text": c.text} for c in retrieved
        ],
        "conversation_history": [{"role": m["role"], "content": m["content"]} for m in history[-tutor.HISTORY_LIMIT :]],
    }
    try:
        answer = ai.generate(
            TUTOR_SYSTEM_PROMPT,
            user_payload,
            AITutorAnswer,
            validator=lambda parsed: tutor.validate_tutor_answer(parsed, retrieved),
        )
    except (AITimeoutError, AISchemaError, AIUnavailableError) as exc:
        raise _ai_error_response(exc)  # nothing has been saved

    refused = not answer.relevant
    if refused:
        content, sources, keywords = tutor.REFUSAL_TEXT, [], []
    else:
        sources = tutor.sources_for(answer.used_source_ids, retrieved)
        keywords = tutor.keywords_for(answer, bool(sources))
        content = answer.answer.strip()
        if not sources:
            if keywords:
                content = f"{content}\n\n{tutor.keywords_line(keywords)}"
            content = f"{content}\n\n{tutor.NO_SOURCE_NOTE}"

    now = _now_iso()
    user_message = {
        "role": "user",
        "content": question,
        "timestamp": now,
        "sources": [],
        "client_request_id": payload.client_request_id,
    }
    assistant_message = {
        "role": "assistant",
        "content": content,
        "timestamp": now,
        "sources": sources,
        "refused": refused,
        "search_keywords": keywords,
    }
    title = conv["title"]
    if not history and title == tutor.DEFAULT_TITLE:
        title = tutor.make_title(question)
    db.update(
        "conversations",
        conversation_id,
        {"messages": [*history, user_message, assistant_message], "title": title, "updated_at": now},
    )
    return SendMessageResponse(
        user_message=user_message,
        assistant_message=tutor.decorate(assistant_message, current_field, current_course, question),
        conversation_title=title,
        refused=refused,
    )


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


# 9b. AI learning insight (Phase 6B): stored per learning, created only when the user asks
INSIGHT_WINDOW_DAYS = 14
INSIGHT_MIN_RECORDS = 3
INSIGHT_MIN_REFLECTIONS = 1
INSIGHT_REFLECTION_LIMIT = 5
INSIGHT_RECORD_LIMIT = 40  # records sent to the model (newest first); the count shown stays the real one
INSIGHT_COOLDOWN_SECONDS = 60
INSIGHT_NOTICE = "내 실행 기록과 회고 기반 · AI 생성 안내"
# Wording that would treat a suggested weekday as a deadline (the weekday is a hint, never a due date).
INSIGHT_FORBIDDEN_TERMS = ("연체", "실패", "밀렸", "밀려", "놓쳤", "놓친", "지연", "늦었", "뒤처", "마감")


def _insight_inputs(
    goal_logs: list[dict[str, Any]],
    goal_tasks: list[dict[str, Any]],
    all_reflections: list[dict[str, Any]],
    today: date,
) -> dict[str, Any]:
    """Everything an insight is built from (and judged stale against), for one learning.

    - records: this learning's study logs of the last 14 calendar days (today included,
      Asia/Seoul via clock.today), newest first.
    - reflections: the newest 5 reflections of this learning's tasks (same newest-first rule as
      the tutor's context, not limited to the window). Read from storage on every call, so an
      edited reflection shows its latest text and a deleted one is gone.
    - sufficient: at least 3 records in the window and at least 1 reflection.
    - signature: a hash of (id, updated_at) of every input item, used by is_stale.
    """
    start = today - timedelta(days=INSIGHT_WINDOW_DAYS - 1)
    records = sorted(
        (log for log in goal_logs if start <= date.fromisoformat(log["study_date"]) <= today),
        key=lambda log: (log["study_date"], log["created_at"]),
        reverse=True,
    )
    task_by_id = {t["id"]: t for t in goal_tasks}
    log_by_id = {log["id"]: log for log in goal_logs}
    mine = [r for r in all_reflections if r["task_id"] in task_by_id]
    mine.sort(
        key=lambda r: ((log_by_id.get(r["study_log_id"]) or {}).get("study_date", r["created_at"][:10]), r["created_at"]),
        reverse=True,
    )
    used = mine[:INSIGHT_REFLECTION_LIMIT]
    parts = sorted([("l", log["id"], log["updated_at"]) for log in records] + [("r", r["id"], r["updated_at"]) for r in used])
    return {
        "records": records,
        "reflections": used,
        "task_by_id": task_by_id,
        "log_by_id": log_by_id,
        "record_count": len(records),
        "reflection_total": len(mine),
        "sufficient": len(records) >= INSIGHT_MIN_RECORDS and len(mine) >= INSIGHT_MIN_REFLECTIONS,
        "signature": hashlib.sha256(json.dumps(parts).encode("utf-8")).hexdigest(),
        "window_start": start,
    }


def _goal_insight_inputs(db, uid: str, goal: dict[str, Any]) -> dict[str, Any]:
    return _insight_inputs(
        db.find("study_logs", user_id=uid, goal_id=goal["id"]),
        db.find("tasks", user_id=uid, goal_id=goal["id"]),
        db.find("reflections", user_id=uid),
        clock.today(),
    )


def _insight_item(doc: dict[str, Any], inputs: dict[str, Any]) -> InsightItem:
    return InsightItem(
        summary=doc["summary"],
        difficulty=doc.get("difficulty", ""),
        next_action=doc["next_action"],
        generated_at=doc["generated_at"],
        record_count=doc["record_count"],
        reflection_count=doc["reflection_count"],
        is_stale=doc.get("source_signature") != inputs["signature"],
    )


def _own_insight(db, uid: str, goal_id: str) -> Optional[dict[str, Any]]:
    doc = db.get("insights", goal_id)
    return doc if doc is not None and doc.get("user_id") == uid else None


INSIGHT_MIN_REFLECTIONS_FOR_DIFFICULTY = 2
insight_logger = logging.getLogger("pacemate.insight")


def _insight_reject_reason(exc: Exception) -> str:
    """Category of a rejected attempt: only a fixed label, never user text, numbers or UIDs."""
    if isinstance(exc, AIRetryFeedback):
        return exc.reason
    errors = exc.errors() if hasattr(exc, "errors") else []
    kinds = {e.get("type") for e in errors}
    if "string_too_long" in kinds:
        return "length"
    if kinds & {"string_too_short", "missing"}:
        return "empty_part"
    return "other"


def _log_insight_reject(exc: Exception, attempt: int) -> None:
    insight_logger.info("insight_validation_reject reason=%s attempt=%d", _insight_reject_reason(exc), attempt)


def _validate_ai_insight(
    parsed: AIInsight, facts: insight_rules.QuantityFacts, reflection_count: int
) -> None:
    """Server rules for an insight (nothing is patched silently; a violation is retried):
    required parts, no deadline-style wording, `difficulty` only with at least two reflections,
    and every time/count expression in the text must be a value the server itself provided
    (the model must not add up or convert numbers; see insight_rules)."""
    summary, difficulty, next_action = parsed.summary.strip(), parsed.difficulty.strip(), parsed.next_action.strip()
    problem = None
    reason = "other"
    if not summary or not next_action:
        problem, reason = "summary 와 next_action 은 비어 있으면 안 됩니다.", "empty_part"
    else:
        text = " ".join([summary, difficulty, next_action])
        if any(term in text for term in INSIGHT_FORBIDDEN_TERMS):
            problem = "추천 요일은 마감일이 아닙니다. 연체·실패·밀림·지연·마감처럼 평가하거나 마감으로 보는 표현을 쓰지 마세요."
            reason = "forbidden_term"
        elif difficulty and reflection_count < INSIGHT_MIN_REFLECTIONS_FOR_DIFFICULTY:
            # Safety net. With fewer than two reflections difficulty is not even requested
            # (AIInsightBasic / INSIGHT_SYSTEM_PROMPT_BASIC), so this only fires on a stray value.
            problem, reason = "회고가 2건 미만이면 difficulty 를 비워야 합니다.", "difficulty_without_reflections"
        else:
            wrong = insight_rules.find_unsupported_quantities([summary, difficulty, next_action], facts)
            if wrong:
                problem = (
                    "다음 시간·건수 표현은 제공된 값(*_label, *_minutes, *_count)에 없습니다: "
                    + ", ".join(dict.fromkeys(wrong))
                    + ". 제공된 값만 그대로 쓰고 스스로 더하거나 환산하지 마세요."
                )
                reason = "quantity"
    if problem:
        raise AIRetryFeedback(problem, feedback={"validation_error": problem}, reason=reason)


@app.get(
    "/api/goals/{goal_id}/insight",
    response_model=InsightResponse,
    tags=["insight"],
    summary="저장된 마지막 AI 학습 인사이트 조회 (AI 를 호출하지 않는다)",
)
def get_goal_insight(goal_id: str, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    goal = _get_owned(db, "goals", goal_id, uid)
    saved = _own_insight(db, uid, goal_id)
    if saved is None:
        return InsightResponse(insight=None)
    return InsightResponse(insight=_insight_item(saved, _goal_insight_inputs(db, uid, goal)))


@app.post(
    "/api/goals/{goal_id}/insight",
    response_model=InsightResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["insight"],
    summary="AI 학습 인사이트 만들기 (사용자가 누를 때만, 기록 부족이면 AI 미호출, 멱등, 60초 간격 제한)",
)
def create_goal_insight(
    goal_id: str,
    payload: InsightRequest,
    response: Response,
    uid: str = Depends(require_consented_uid),
    db=Depends(get_db),
    ai: AIClient = Depends(get_ai_client),
):
    goal = _get_owned(db, "goals", goal_id, uid)
    inputs = _goal_insight_inputs(db, uid, goal)
    saved = _own_insight(db, uid, goal_id)

    # Idempotency first: a retry of an already stored request returns it, no AI call, no cooldown.
    if saved is not None and saved.get("client_request_id") == payload.client_request_id:
        response.status_code = status.HTTP_200_OK
        return InsightResponse(insight=_insight_item(saved, inputs))

    if not inputs["sufficient"]:
        # Not enough material: do not call the AI, do not store anything.
        response.status_code = status.HTTP_200_OK
        return InsightResponse(
            insight=None,
            is_insufficient=True,
            message=(
                "기록과 회고를 더 남기면 인사이트를 볼 수 있어요. "
                f"(기록 {inputs['record_count']}/{INSIGHT_MIN_RECORDS}, 회고 {inputs['reflection_total']}/{INSIGHT_MIN_REFLECTIONS})"
            ),
            record_count=inputs["record_count"],
            reflection_count=inputs["reflection_total"],
        )

    if saved is not None:
        try:
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(saved["generated_at"].replace("Z", "+00:00"))).total_seconds()
        except (KeyError, ValueError):
            age = INSIGHT_COOLDOWN_SECONDS  # unreadable stored time: do not block
        if age < INSIGHT_COOLDOWN_SECONDS:
            wait = max(1, int(INSIGHT_COOLDOWN_SECONDS - age + 0.999))
            raise api_error(
                status.HTTP_429_TOO_MANY_REQUESTS,
                "INSIGHT_COOLDOWN",
                f"인사이트는 {wait}초 뒤에 다시 만들 수 있어요.",
                {"retry_after_seconds": wait},
            )

    tasks = list(inputs["task_by_id"].values())
    done, total, _ = _goal_progress(tasks)
    today = clock.today()
    week_start = clock.week_monday(today)
    all_goal_logs = db.find("study_logs", user_id=uid, goal_id=goal_id)
    week_minutes = sum(
        log["minutes"] for log in all_goal_logs if clock.is_within_week(date.fromisoformat(log["study_date"]), week_start)
    )
    # The server does all the arithmetic; the model only repeats these values.
    window_minutes = sum(log["minutes"] for log in inputs["records"])
    target_minutes = goal["weekly_hours"] * 60
    reflection_used = len(inputs["reflections"])
    per_task: dict[str, int] = {}
    for log in inputs["records"]:
        per_task[log["task_id"]] = per_task.get(log["task_id"], 0) + 1
    facts = insight_rules.build_facts(
        record_minutes=[log["minutes"] for log in inputs["records"]],
        record_count_by_task=list(per_task.values()),
        window_total_minutes=window_minutes,
        this_week_minutes=week_minutes,
        weekly_target_minutes=target_minutes,
        window_record_count=inputs["record_count"],
        reflection_count=reflection_used,
        completed_tasks=done,
        total_tasks=total,
    )
    user_payload = {
        "learning": {
            "field": goal["field"],
            "course": goal["course"],
            "current_level_name": goal["current_level_name"],
            "target_level_name": goal["target_level_name"],
            "weekly_hours": goal["weekly_hours"],
        },
        "window": {"from": inputs["window_start"].isoformat(), "to": today.isoformat(), "days": INSIGHT_WINDOW_DAYS},
        "progress": {
            "completed_tasks": done,
            "total_tasks": total,
            "window_record_count": inputs["record_count"],
            "window_total_minutes": window_minutes,
            "window_total_label": insight_rules.format_minutes(window_minutes),
            "this_week_minutes": week_minutes,
            "this_week_label": insight_rules.format_minutes(week_minutes),
            "weekly_target_minutes": target_minutes,
            "weekly_target_label": insight_rules.format_minutes(target_minutes),
            "reflection_count": reflection_used,
        },
        "records": [
            {
                "study_date": log["study_date"],
                "minutes": log["minutes"],
                "activity": log["activity"],
                "task_title": (inputs["task_by_id"].get(log["task_id"]) or {}).get("title", ""),
            }
            for log in inputs["records"][:INSIGHT_RECORD_LIMIT]
        ],
        "reflections": [
            {
                "study_date": (inputs["log_by_id"].get(r["study_log_id"]) or {}).get("study_date", r["created_at"][:10]),
                "task_title": (inputs["task_by_id"].get(r["task_id"]) or {}).get("title", ""),
                "content": r["content"],
                "tags": r.get("tags", []),
            }
            for r in inputs["reflections"]
        ],
    }
    try:
        # Two reflections or more: ask for summary, difficulty and next_action. Fewer: the model is
        # not asked for difficulty at all (a repeated difficulty needs two reflections), which
        # avoids the rejected-and-retried round trips seen with the single schema.
        with_difficulty = reflection_used >= INSIGHT_MIN_REFLECTIONS_FOR_DIFFICULTY
        result = ai.generate(
            INSIGHT_SYSTEM_PROMPT if with_difficulty else INSIGHT_SYSTEM_PROMPT_BASIC,
            user_payload,
            AIInsight if with_difficulty else AIInsightBasic,
            validator=lambda parsed: _validate_ai_insight(parsed, facts, reflection_used),
            on_reject=_log_insight_reject,
        )
    except (AITimeoutError, AISchemaError, AIUnavailableError) as exc:
        raise _ai_error_response(exc)  # nothing is stored; an earlier insight stays as it was

    now = _now_iso()
    doc = {
        "user_id": uid,
        "goal_id": goal_id,
        "summary": result.summary.strip(),
        "difficulty": result.difficulty.strip() if with_difficulty else "",  # basic schema: nothing was requested
        "next_action": result.next_action.strip(),
        "generated_at": now,
        "record_count": inputs["record_count"],
        "reflection_count": len(inputs["reflections"]),
        "source_signature": inputs["signature"],
        "client_request_id": payload.client_request_id,
        "created_at": saved["created_at"] if saved else now,
        "updated_at": now,
    }
    stored = db.set("insights", goal_id, doc)  # one document per learning: a new insight overwrites
    return InsightResponse(insight=_insight_item(stored, inputs))


# 10. Feedback (learners) and admin screens (Phase 5E)
FEEDBACK_LIMIT_PER_USER = 10
ADMIN_USERS_PAGE_SIZE = 50
ACTIVE_WINDOW_DAYS = 7
FEEDBACK_DONE_WINDOW_DAYS = 30
FEEDBACK_LIST_DEFAULT = 100
FEEDBACK_LIST_MAX = 200


@app.post(
    "/api/feedback",
    response_model=FeedbackReceipt,
    status_code=status.HTTP_201_CREATED,
    tags=["feedback"],
    summary="테스트 피드백 제출 (사용자 정보 없이 저장, client_request_id 로 멱등)",
)
def create_feedback(
    payload: FeedbackCreateRequest,
    response: Response,
    user: dict[str, Any] = Depends(require_consented_user_doc),
    db=Depends(get_db),
):
    # The request is authenticated with the UID, but the stored document never carries it: the
    # idempotency key is a random value unrelated to the user, and the per-user counter lives on
    # the users document (it disappears with a data deletion request, the feedback stays).
    existing = next(iter(db.find("feedback", client_request_id=payload.client_request_id)), None)
    if existing is not None:
        response.status_code = status.HTTP_200_OK
        return {"id": existing["id"], "created_at": existing["created_at"]}

    sent = int(user.get("feedback_submitted_count") or 0)
    if sent >= FEEDBACK_LIMIT_PER_USER:
        raise api_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "FEEDBACK_LIMIT_REACHED",
            "이번 테스트에서 보낼 수 있는 피드백 수를 넘었어요.",
        )
    now = _now_iso()
    doc = db.create(
        "feedback",
        {
            "usability": payload.usability,
            "ai_usefulness": payload.ai_usefulness,
            "screen": payload.screen,
            "comment": (payload.comment or "").strip(),
            "status": "new",
            "client_request_id": payload.client_request_id,
            "created_at": now,
            "updated_at": now,
        },
    )
    db.update("users", user["uid"], {"feedback_submitted_count": sent + 1})
    return {"id": doc["id"], "created_at": doc["created_at"]}


def _mask_uid(uid: str) -> str:
    return (uid[:4] if len(uid) > 4 else uid[:1]) + "•••"


@app.get(
    "/api/admin/users",
    response_model=AdminUserListResponse,
    tags=["admin"],
    summary="[관리자] 사용자 목록 (마스킹된 ID, 동의, 진행 중 학습 수, 최근 활동, 상태). 읽기 전용",
)
def admin_list_users(
    status_filter: str = Query("all", alias="status", pattern="^(all|active|dormant)$"),
    page: int = Query(1, ge=1),
    admin_uid: str = Depends(require_admin_uid),
    db=Depends(get_db),
):
    today = clock.today()
    active_since = today - timedelta(days=ACTIVE_WINDOW_DAYS)
    # One read of the users and one of the active goals (never one query per user).
    goal_counts: dict[str, int] = {}
    for goal in db.find("goals", status="active"):
        goal_counts[goal["user_id"]] = goal_counts.get(goal["user_id"], 0) + 1

    rows = []
    for user in db.find("users"):
        last = user.get("last_active_at")
        try:
            is_active = bool(last) and clock.date_from_utc_iso(last) >= active_since
        except ValueError:
            is_active = False
        rows.append(
            {
                "sort": last or "",
                "item": AdminUserItem(
                    user_id_masked=_mask_uid(user["uid"]),
                    consented=user.get("consent_version") == CURRENT_TERMS_VERSION,
                    consent_version=user.get("consent_version"),
                    active_goal_count=goal_counts.get(user["uid"], 0),
                    last_active_at=last,
                    status="active" if is_active else "dormant",
                ),
            }
        )
    if status_filter != "all":
        rows = [r for r in rows if r["item"].status == status_filter]
    rows.sort(key=lambda r: r["sort"], reverse=True)
    start = (page - 1) * ADMIN_USERS_PAGE_SIZE
    return AdminUserListResponse(
        items=[r["item"] for r in rows[start : start + ADMIN_USERS_PAGE_SIZE]],
        total=len(rows),
        page=page,
        page_size=ADMIN_USERS_PAGE_SIZE,
    )


@app.get(
    "/api/admin/feedback/summary",
    response_model=AdminFeedbackSummary,
    tags=["admin"],
    summary="[관리자] 피드백 요약 (미확인 건수, 평균, 개선 후보, 최근 30일 반영 완료)",
)
def admin_feedback_summary(admin_uid: str = Depends(require_admin_uid), db=Depends(get_db)):
    docs = db.find("feedback")

    def average(field: str) -> Optional[float]:
        return round(sum(d[field] for d in docs) / len(docs), 1) if docs else None

    done_since = clock.today() - timedelta(days=FEEDBACK_DONE_WINDOW_DAYS)
    return AdminFeedbackSummary(
        unseen_count=sum(1 for d in docs if d["status"] == "new"),
        usability_avg=average("usability"),
        usability_count=len(docs),
        ai_usefulness_avg=average("ai_usefulness"),
        ai_usefulness_count=len(docs),
        candidate_count=sum(1 for d in docs if d["status"] == "candidate"),
        done_last_30_days=sum(
            1 for d in docs if d["status"] == "done" and clock.date_from_utc_iso(d["updated_at"]) >= done_since
        ),
    )


@app.get(
    "/api/admin/feedback",
    response_model=List[AdminFeedbackItem],
    tags=["admin"],
    summary="[관리자] 피드백 목록 (최신순, 최대 200건). 식별 정보는 저장하지 않으므로 내려갈 것도 없다",
)
def admin_list_feedback(
    status_filter: str = Query("all", alias="status", pattern="^(all|new|seen|candidate|done)$"),
    limit: int = Query(FEEDBACK_LIST_DEFAULT, ge=1, le=FEEDBACK_LIST_MAX),
    admin_uid: str = Depends(require_admin_uid),
    db=Depends(get_db),
):
    docs = db.find("feedback") if status_filter == "all" else db.find("feedback", status=status_filter)
    docs.sort(key=lambda d: d["created_at"], reverse=True)
    return docs[:limit]


@app.patch(
    "/api/admin/feedback/{feedback_id}",
    response_model=AdminFeedbackItem,
    tags=["admin"],
    summary="[관리자] 피드백 상태만 변경 (seen | candidate | done). 의견 수정·삭제는 없다",
)
def admin_update_feedback(
    feedback_id: str,
    payload: FeedbackStatusUpdate,
    admin_uid: str = Depends(require_admin_uid),
    db=Depends(get_db),
):
    doc = db.get("feedback", feedback_id)
    if doc is None:
        raise not_found()
    return db.update("feedback", feedback_id, {"status": payload.status, "updated_at": _now_iso()})


# 9. User Profile & Data Deletion
def _profile(user: dict[str, Any]) -> dict[str, Any]:
    return {
        "uid": user["uid"],
        "role": user.get("role", "learner"),
        "active_goal_id": user.get("active_goal_id"),
        "consent_version": user.get("consent_version"),
        "is_admin": _is_admin(user["uid"]),  # derived from ADMIN_UIDS, never stored or settable
        "created_at": user["created_at"],
    }


@app.get("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 조회")
def get_profile(uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    return _profile(db.get("users", uid))


@app.patch("/api/user/profile", response_model=UserProfileResponse, tags=["user"], summary="사용자 프로필 수정")
def update_profile(payload: ProfileUpdateRequest, uid: str = Depends(require_consented_uid), db=Depends(get_db)):
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("active_goal_id"):
        goal = _get_owned(db, "goals", changes["active_goal_id"], uid)
        if goal.get("status") != "active":
            raise bad_request("진행 중인 학습으로만 전환할 수 있습니다.", {"field": "active_goal_id"})
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
