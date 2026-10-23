/** Display labels for the admin screens and the feedback form (Phase 5E). Pure helpers. */

export type FeedbackStatus = "new" | "seen" | "candidate" | "done";
export type FeedbackScreenKey = "dashboard" | "path" | "execution" | "analysis" | "settings" | "other";

export const FEEDBACK_STATUS_LABEL: Record<FeedbackStatus, string> = {
  new: "미확인",
  seen: "확인",
  candidate: "개선 후보",
  done: "반영 완료",
};

/** The statuses an admin can choose; "new" is never selectable (the server rejects it too). */
export const CHOOSABLE_STATUSES: Exclude<FeedbackStatus, "new">[] = ["seen", "candidate", "done"];

export const FEEDBACK_SCREEN_OPTIONS: { value: FeedbackScreenKey; label: string }[] = [
  { value: "dashboard", label: "대시보드" },
  { value: "path", label: "학습 경로 설정" },
  { value: "execution", label: "학습 실행 기록" },
  { value: "analysis", label: "종합 학습 분석" },
  { value: "settings", label: "내 정보·설정" },
  { value: "other", label: "기타" },
];

export function feedbackScreenLabel(value: string): string {
  return FEEDBACK_SCREEN_OPTIONS.find((o) => o.value === value)?.label ?? "기타";
}

/** "동의함 (v1.1)", "재동의 필요 (v1.0)" for an older version, "동의 안 함" when there is none. */
export function consentLabel(consented: boolean, version: string | null): string {
  if (consented) return `동의함 (${version ?? ""})`.replace(" ()", "");
  return version ? `재동의 필요 (${version})` : "동의 안 함";
}

/** Average with one decimal, or a dash when there are no answers. */
export function formatAverage(value: number | null): string {
  return value === null ? "–" : value.toFixed(1);
}

/** A comment for the list; blank comments read "(의견 없음)". */
export function commentOrPlaceholder(comment: string): string {
  const text = comment.trim();
  return text ? `“${text}”` : "(의견 없음)";
}

export function pageCount(total: number, pageSize: number): number {
  return Math.max(1, Math.ceil(total / pageSize));
}

/** Identical form content keeps the same idempotency key (a retry), changed content gets a new one. */
export function requestIdFor(
  current: { key: string; requestId: string } | null,
  key: string,
  makeId: () => string,
): { key: string; requestId: string } {
  return current && current.key === key ? current : { key, requestId: makeId() };
}
