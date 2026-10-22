/**
 * Date rules for the wizard's schedule inputs (F1). Pure, so they can be unit-tested.
 * All values are YYYY-MM-DD strings; compare them as strings (ISO dates sort lexically).
 * `today` must come from todayKSTDateString() (frontend/lib/week.ts), never from a local date.
 */
export function startDateError(startDate: string, targetDate: string, today: string): string | null {
  if (!startDate) return "학습 시작일을 선택해 주세요.";
  if (startDate < today) return "학습 시작일은 오늘 이후여야 해요.";
  if (targetDate && targetDate < startDate) return "목표 완료 희망일은 학습 시작일 이후여야 해요.";
  return null;
}
