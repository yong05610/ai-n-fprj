/** Display helpers for the dashboard and analysis screens (Phase 5C). Pure; dates are YYYY-MM-DD. */

/**
 * "10/05 – 12/28" as in the mockup. When the period leaves `thisYear` the year is added to
 * the end that is outside it ("10/05 – 2027/01/30"), so two dates a year apart stay readable.
 */
export function formatPeriod(startDate: string, targetDate: string, thisYear: number): string {
  const part = (iso: string): string => {
    const [y, m, d] = iso.split("-");
    return Number(y) === thisYear ? `${m}/${d}` : `${y}/${m}/${d}`;
  };
  return `${part(startDate)} – ${part(targetDate)}`;
}

/** The API's level_progress_text is "<current> → <target>"; the mockup reads "현재 … → 목표 …". */
export function levelSummary(levelProgressText: string): { current: string; target: string } | null {
  const [current, target, ...rest] = levelProgressText.split(" → ");
  if (!current || !target || rest.length > 0) return null;
  return { current, target };
}

/** 420 -> "7시간", 450 -> "450분": hours only when the minutes divide evenly. */
export function formatTargetMinutes(minutes: number): string {
  return minutes > 0 && minutes % 60 === 0 ? `${minutes / 60}시간` : `${minutes}분`;
}
