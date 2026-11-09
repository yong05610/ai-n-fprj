/**
 * CR-013: what the plan screen shows for the weekday saver. Usually a small status text, never a button; the
 * "다시 시도" button exists only after a failure. (The saver itself, LatestWinsSaver, is unchanged.)
 */
import type { SaveState } from "@/lib/latestWins";

export type SaveView = { kind: "saved" | "saving" | "error"; text: string; showRetry: boolean };

export function saveStatusView(state: SaveState): SaveView {
  if (state.status === "saving") return { kind: "saving", text: "저장 중…", showRetry: false };
  if (state.status === "error") return { kind: "error", text: "저장하지 못했어요.", showRetry: true };
  return { kind: "saved", text: "✓ 변경 내용 자동 저장됨", showRetry: false };
}
