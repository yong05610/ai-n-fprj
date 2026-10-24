/**
 * Wording of the whole-course plan (Phase 5F) as pure functions, shared by the wizard preview,
 * the weekly plan screen and the dashboard. Neutral wording only: never "overdue" or "late".
 */
import { formatHoursMinutes, weekRangeLabel } from "@/lib/weekPlan";

export { formatHoursMinutes };

/** "총 예상 시간 5시간 / 가용 시간 43시간 34분 (총 61일(약 8.7주), 주 5시간)" */
export function planSummaryText(totalMinutes: number, availableMinutes: number, days: number, weeks: number, weeklyHours: number): string {
  return `총 예상 시간 ${formatHoursMinutes(totalMinutes)} / 가용 시간 ${formatHoursMinutes(availableMinutes)} (총 ${days}일(약 ${weeks.toFixed(1)}주), 주 ${weeklyHours}시간)`;
}

/** Small print when the first or the last week of the period is a partial week; null for whole weeks. */
export function partialWeekNote(firstDays: number, lastDays: number): string | null {
  const parts: string[] = [];
  if (firstDays < 7) parts.push(`첫 주는 ${firstDays}일만 남아 있어요`);
  if (lastDays < 7) parts.push(`마지막 주는 ${lastDays}일까지예요`);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export const COVERAGE_HINT_BELOW = 40;

/** Neutral hint when a plan uses a small share of the available time (never blocks confirming). */
export function coverageHint(percent: number): string | null {
  return percent < COVERAGE_HINT_BELOW
    ? `이 계획은 가용 시간의 ${percent}% 예요. 더 깊게 배우려면 목표 수준이나 기간을 조정해 보세요.`
    : null;
}

export function coverageText(percent: number): string {
  return `가용 시간의 ${percent}% 사용`;
}

/** Share of the available time the plan uses, 0..100 for the bar (capped), plus whether it is over. */
export function budgetBar(totalMinutes: number, availableMinutes: number): { percent: number; over: boolean } {
  if (availableMinutes <= 0) return { percent: totalMinutes > 0 ? 100 : 0, over: totalMinutes > 0 };
  return { percent: Math.min(100, Math.round((totalMinutes / availableMinutes) * 100)), over: totalMinutes > availableMinutes };
}

export function overBudgetMessage(totalMinutes: number, availableMinutes: number): string {
  return `총 예상 시간(${formatHoursMinutes(totalMinutes)})이 가용 시간(${formatHoursMinutes(availableMinutes)})을 넘어 확정할 수 없어요. 과제를 줄이거나 시간을 조정해 주세요.`;
}

/** "10/19–10/25 · 1주차 · 예정 5시간" (index is 0-based) */
export function weekGroupHeading(weekStart: string, index: number, scheduledMinutes: number): string {
  return `${weekRangeLabel(weekStart)} · ${index + 1}주차 · 예정 ${formatHoursMinutes(scheduledMinutes)}`;
}

/** Shown on the start week of a task that continues into later weeks. */
export function spanNote(weeksSpanned: number): string | null {
  return weeksSpanned > 1 ? `이어서 ${weeksSpanned}주에 걸쳐 진행` : null;
}

/** "이어서 (이번 주 90분 / 총 150분)" for the weeks a task continues into. */
export function continuedLabel(weekMinutes: number, totalMinutes: number): string {
  return `이어서 (이번 주 ${weekMinutes}분 / 총 ${totalMinutes}분)`;
}

export const TASK_COUNT_MIN = 3;
export const TASK_COUNT_MAX = 60;

export function taskCountHint(count: number): string {
  return `과제는 ${TASK_COUNT_MIN}~${TASK_COUNT_MAX}개예요. 지금 ${count}개입니다.`;
}

export function taskCountOk(count: number): boolean {
  return count >= TASK_COUNT_MIN && count <= TASK_COUNT_MAX;
}

/** "이번 주 예정 5시간 · 오늘 예정 1시간 30분" for the dashboard. */
export function dashboardScheduleText(weekMinutes: number, todayMinutes: number): string {
  return `이번 주 예정 ${formatHoursMinutes(weekMinutes)} · 오늘 예정 ${formatHoursMinutes(todayMinutes)}`;
}

/** "총 소요 시간 … · 가용 … · 이번 주 예정 …" on top of the weekly plan card. */
export function weeklyPlanHeaderText(totalMinutes: number, availableMinutes: number, weekMinutes: number): string {
  return `총 소요 시간 ${formatHoursMinutes(totalMinutes)} · 가용 ${formatHoursMinutes(availableMinutes)} · 이번 주 예정 ${formatHoursMinutes(weekMinutes)}`;
}
