"""CR-012: plan generation as three AI calls (field guideline -> design opinion -> JSON).

Stage 0 writes a field guideline (free text) from the field, course and the two level names only. Stage 1 writes
a design opinion (free text) from the whole plan request plus that guideline. Stage 2 turns the opinion into the
JSON the server validates (`AIPlanDraft`, same rules and retry feedback as before). All three use the plan model
(OPENAI_PLAN_MODEL). Nothing here is stored: the guideline is rebuilt for every request.

The whole flow has one time budget (the browser gives up after 200 s): every attempt gets the time that is left,
and no retry starts when too little is left. Failures use the usual error classes (timeout / schema / unavailable).
Logs carry the stage name, the result and the seconds only, never a stage text or any user input.
"""

import logging
import time
from typing import Callable

from ai_client import (
    AIClient,
    AITimeoutError,
    call_limits,
    plan_max_output_tokens,
    plan_model,
    plan_timeout_seconds,
)
from ai_schemas import AIPlanDraft
from prompts import PLAN_GENERATE_SYSTEM_PROMPT, PLAN_GUIDE_SYSTEM_PROMPT, PLAN_OPINION_SYSTEM_PROMPT

logger = logging.getLogger("pacemate.ai")

TOTAL_BUDGET_SECONDS = 170.0  # the front end waits 200 s (PLAN_TIMEOUT_MS)
MIN_ATTEMPT_SECONDS = 10.0  # less than this left: no new attempt
GUIDE_MAX_TOKENS = 6000
OPINION_MAX_TOKENS = 8000
GUIDE_KEYS = ("field", "course", "current_level_name", "target_level_name")

monotonic: Callable[[], float] = time.monotonic  # tests replace it with a fake clock


def generate_plan_draft(ai: AIClient, user_payload: dict, validator: Callable[[AIPlanDraft], None]) -> AIPlanDraft:
    started = monotonic()

    def left() -> float:
        return TOTAL_BUDGET_SECONDS - (monotonic() - started)

    def can_continue() -> bool:
        return left() >= MIN_ATTEMPT_SECONDS

    def attempt_timeout() -> float:
        return max(1.0, min(plan_timeout_seconds(), left()))

    model = plan_model()

    def stage(name: str, max_tokens: int, call: Callable[[], object]):
        if not can_continue():
            logger.warning("plan_stage stage=%s result=skipped kind=budget", name)
            raise AITimeoutError("AI 응답이 시간 안에 완료되지 않았습니다.")
        t0 = monotonic()
        try:
            with call_limits(attempt_timeout, max_tokens, model):
                result = call()
        except Exception as exc:
            logger.warning("plan_stage stage=%s result=failed kind=%s seconds=%.1f", name, type(exc).__name__, monotonic() - t0)
            raise
        logger.info("plan_stage stage=%s result=ok seconds=%.1f", name, monotonic() - t0)
        return result

    guideline = stage(
        "guide",
        GUIDE_MAX_TOKENS,
        lambda: ai.generate_text(
            PLAN_GUIDE_SYSTEM_PROMPT, {k: user_payload[k] for k in GUIDE_KEYS}, should_continue=can_continue
        ),
    )
    analysis = stage(
        "opinion",
        OPINION_MAX_TOKENS,
        lambda: ai.generate_text(
            PLAN_OPINION_SYSTEM_PROMPT, {**user_payload, "guideline": guideline}, should_continue=can_continue
        ),
    )
    return stage(
        "json",
        plan_max_output_tokens(),
        lambda: ai.generate(
            PLAN_GENERATE_SYSTEM_PROMPT,
            {**user_payload, "analysis": analysis},
            AIPlanDraft,
            validator=validator,
            should_continue=can_continue,
        ),
    )
