/**
 * Which task the execution screen should show as selected so a timer that is still running
 * on the server is visible (F3). Pure, so the state rule can be unit-tested.
 *
 * The server keeps one active timer per user. After a refresh, or after switching to another
 * learning and back, the screen's own selection is empty; without this the timer would keep
 * running while the screen showed 00:00:00 and a "start" button.
 */
export type TimerState = { active: boolean; task_id: string | null; goal_id: string | null };

/** The task to auto-select: only when the timer belongs to the learning being shown. */
export function taskToSelectForTimer(
  timer: TimerState | null,
  activeGoalId: string | null,
  taskIds: readonly string[],
): string | null {
  if (!timer?.active || !timer.task_id || !timer.goal_id) return null;
  if (timer.goal_id !== activeGoalId) return null;
  return taskIds.includes(timer.task_id) ? timer.task_id : null;
}

export type TimerLocation = "none" | "selected-task" | "other-task-same-goal" | "other-goal";

/** Where the running timer is relative to what the screen currently shows. */
export function timerLocation(
  timer: TimerState | null,
  activeGoalId: string | null,
  selectedTaskId: string | null,
): TimerLocation {
  if (!timer?.active || !timer.task_id) return "none";
  if (timer.goal_id && timer.goal_id !== activeGoalId) return "other-goal";
  return timer.task_id === selectedTaskId ? "selected-task" : "other-task-same-goal";
}
