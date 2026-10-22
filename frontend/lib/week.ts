/**
 * Service-wide "this week's Monday" in Asia/Seoul, matching backend/clock.py.
 *
 * `new Date().toISOString()` converts to UTC, which silently shifts the date
 * backwards for anyone viewing between 00:00-09:00 KST (UTC+9) - the plan
 * week default would land on a Sunday and the server rejects it with
 * "월요일이어야 합니다". Reading the date via Intl with an explicit
 * `timeZone: "Asia/Seoul"` avoids that round-trip entirely.
 */
export function mondayOfThisWeekKST(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string): number => Number(parts.find((p) => p.type === type)?.value);

  // Anchor the calendar date as a UTC pseudo-instant so day-of-week arithmetic
  // never re-interprets it against a real timezone again.
  const anchor = new Date(Date.UTC(get("year"), get("month") - 1, get("day")));
  const mondayOffset = (anchor.getUTCDay() + 6) % 7; // Monday = 0
  anchor.setUTCDate(anchor.getUTCDate() - mondayOffset);
  return anchor.toISOString().slice(0, 10);
}

export function isMondayDateString(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split("-").map(Number);
  return new Date(Date.UTC(y, m - 1, d)).getUTCDay() === 1;
}

export function todayKSTDateString(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(now);
  const get = (type: string): string => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}-${get("month")}-${get("day")}`;
}

/** "2026년 10월 22일 · 목요일" in Asia/Seoul, for the top bar (Phase 5C). */
export function todayKSTLabel(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("ko-KR", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "long",
    day: "numeric",
    weekday: "long",
  }).formatToParts(now);
  const get = (type: string): string => parts.find((p) => p.type === type)?.value ?? "";
  return `${get("year")}년 ${get("month")} ${get("day")}일 · ${get("weekday")}`;
}

function kstParts(iso: string): Record<string, string> {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul",
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).formatToParts(new Date(iso));
  return Object.fromEntries(parts.map((p) => [p.type, p.value]));
}

/** "14:05" in Asia/Seoul for an ISO instant (chat message time). */
export function timeKSTLabel(iso: string): string {
  const p = kstParts(iso);
  return `${p.hour}:${p.minute}`;
}

/** "10/22 14:05" in Asia/Seoul for an ISO instant (conversation list). */
export function dateTimeKSTLabel(iso: string): string {
  const p = kstParts(iso);
  return `${p.month}/${p.day} ${p.hour}:${p.minute}`;
}
