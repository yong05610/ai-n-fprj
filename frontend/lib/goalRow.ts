/**
 * CR-013: a learning row of the dashboard's overview opens that learning's execution record. The learning
 * first becomes the current one (PATCH /api/user/profile, as the learning switch does), unless it already is.
 */

export function goalRowLabel(course: string): string {
  return `${course} 학습 실행 기록으로 이동`;
}

export const SWITCH_FAILED = "학습을 전환하지 못했어요. 잠시 후 다시 눌러 주세요.";

export type OpenOutcome = { ok: true } | { ok: false; error: string };

/**
 * `ok: true` = go to the execution record now. A failed switch never moves on. If the current learning cannot be
 * read, the switch is attempted anyway (setting the same learning again does no harm).
 */
export async function openGoalExecution(args: {
  goalId: string;
  getActiveGoalId: () => Promise<string | null>;
  switchGoal: (goalId: string) => Promise<void>;
  errorText: (error: unknown) => string;
}): Promise<OpenOutcome> {
  let active: string | null = null;
  try {
    active = await args.getActiveGoalId();
  } catch {
    active = null;
  }
  if (active === args.goalId) return { ok: true };
  try {
    await args.switchGoal(args.goalId);
  } catch (error) {
    return { ok: false, error: args.errorText(error) };
  }
  return { ok: true };
}
