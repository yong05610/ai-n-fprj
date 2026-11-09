/**
 * CR-013: the "이 학습 삭제" confirmation and its flow. Pure pieces, so the wording and the outcomes are tested
 * without a browser. The server does the deleting (DELETE /api/goals/{id}); the numbers in the confirmation are
 * the ones the screen has already loaded - never a guess.
 */

export const DELETE_TITLE = "이 학습을 삭제할까요?";
export const DELETE_TUTOR_NOTE = "AI 튜터 대화는 학습과 따로 저장되어 지워지지 않아요.";
export const DELETE_FAILED = "학습을 삭제하지 못했어요. 아무것도 지워지지 않았어요. 잠시 후 다시 시도해 주세요.";

export type DeleteCounts = { tasks: number | null; records: number | null };

/**
 * Task count = the length of the loaded task list. Record count = the sum of the tasks' record counts, known only
 * when every loaded task carries one. `null` = not known (the sentence then has no number).
 */
export function deleteCounts(tasks: { record_count?: number }[] | null): DeleteCounts {
  if (tasks === null) return { tasks: null, records: null };
  const allKnown = tasks.every((t) => typeof t.record_count === "number");
  return {
    tasks: tasks.length,
    records: allKnown ? tasks.reduce((sum, t) => sum + (t.record_count as number), 0) : null,
  };
}

/** The confirmation text as [course name (shown bold), the rest of the sentence]. */
export function deleteBody(course: string, counts: DeleteCounts): [string, string] {
  const tasks = counts.tasks === null ? "그 과제" : `그 과제 ${counts.tasks}개`;
  const records = counts.records === null ? "실행 기록" : `실행 기록 ${counts.records}건`;
  return [course, ` 학습과 ${tasks}, ${records}, 회고, 학습 인사이트가 모두 지워지고 되돌릴 수 없어요. 켜 둔 타이머도 멈춰요.`];
}

/** The confirm button: disabled while deleting, "다시 시도" after a failure. */
export function deleteConfirmButton(busy: boolean, failed: boolean): { label: string; disabled: boolean } {
  if (busy) return { label: "삭제하는 중…", disabled: true };
  return { label: failed ? "다시 시도" : "삭제", disabled: false };
}

export type DeleteOutcome = { ok: true } | { ok: false; error: string };

/** "Not found" for the learning being deleted = it is already gone (e.g. the first request got through but its answer was lost). */
export function isAlreadyDeleted(error: unknown): boolean {
  return typeof error === "object" && error !== null && (error as { status?: unknown }).status === 404;
}

/**
 * Delete, then reload the list of learnings and the current learning (the server already moved the current
 * learning to a remaining one, or to none). A failed delete leaves everything as it was; a failed reload does not
 * undo a delete that succeeded. A 404 is "already deleted" and counts as a success (the reload then shows the truth);
 * any other error (403 ...) stays a failure.
 */
export async function runGoalDelete(
  remove: () => Promise<void>,
  reload: () => Promise<void>,
  errorText: (error: unknown) => string,
): Promise<DeleteOutcome> {
  try {
    await remove();
  } catch (error) {
    if (!isAlreadyDeleted(error)) return { ok: false, error: errorText(error) };
  }
  try {
    await reload();
  } catch {
    // the learning is gone; the screen's own load error handling covers the reload
  }
  return { ok: true };
}
