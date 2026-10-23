/** Pure helpers for the learning-insight card (Phase 6B): texts, button label, retry key. */
import { dateTimeKSTLabel } from "@/lib/week";

export type InsightData = {
  summary: string;
  difficulty: string;
  next_action: string;
  generated_at: string;
  record_count: number;
  reflection_count: number;
  is_stale: boolean;
};

export const NO_INSIGHT_TEXT = "아직 만든 인사이트가 없어요. 버튼을 누르면 최근 14일의 기록과 회고로 만들어요.";
export const CREATING_TEXT = "인사이트를 만드는 중이에요…";

/** "인사이트 만들기" until one exists, then "인사이트 갱신"; "만드는 중…" while the request runs. */
export function createButtonLabel(hasInsight: boolean, creating: boolean): string {
  if (creating) return "만드는 중…";
  return hasInsight ? "인사이트 갱신" : "인사이트 만들기";
}

/** Shown next to an existing insight whose inputs changed; the old text stays visible. */
export function staleNotice(insight: Pick<InsightData, "is_stale"> | null): string | null {
  return insight?.is_stale ? "기록이 바뀌었어요. 다시 만들 수 있어요." : null;
}

export function footerText(generatedAt: string | null): string {
  const base = "내 실행 기록과 회고 기반 · AI 생성 안내";
  return generatedAt ? `${base} · 생성 ${dateTimeKSTLabel(generatedAt)}` : base;
}

/** The difficulty line is hidden when the model found no repeated difficulty. */
export function hasDifficulty(insight: Pick<InsightData, "difficulty">): boolean {
  return insight.difficulty.trim().length > 0;
}

/**
 * Retrying after an error must reuse the same idempotency key, so a request that did reach the
 * server is never created twice; after a success (or a definite refusal) the next press gets a new one.
 */
export function nextRequestId(current: string | null, makeId: () => string): string {
  return current ?? makeId();
}

/** Seconds from a 429 INSIGHT_COOLDOWN error's details, or null if the shape is unexpected. */
export function cooldownSeconds(details: unknown): number | null {
  const value = (details as { retry_after_seconds?: unknown } | null | undefined)?.retry_after_seconds;
  return typeof value === "number" && Number.isFinite(value) && value > 0 ? Math.ceil(value) : null;
}

export function cooldownText(seconds: number | null): string {
  return seconds ? `인사이트는 ${seconds}초 뒤에 다시 만들 수 있어요.` : "잠시 뒤에 다시 만들 수 있어요.";
}
