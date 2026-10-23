"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import {
  CREATING_TEXT,
  type InsightData,
  NO_INSIGHT_TEXT,
  cooldownSeconds,
  cooldownText,
  createButtonLabel,
  footerText,
  hasDifficulty,
  nextRequestId,
  staleNotice,
} from "@/lib/insightState";

type InsightResponse = {
  insight: InsightData | null;
  is_insufficient?: boolean;
  message?: string | null;
};

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `ins-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

/**
 * "AI 학습 인사이트" card of the execution screen (Phase 6B). Opening the screen only reads the
 * saved insight (GET); the AI runs only when the user presses the button (POST).
 * `dataVersion` changes when the screen reloads its records, so the stale flag stays current.
 */
export function InsightCard({ goalId, dataVersion }: { goalId: string | null; dataVersion: unknown }) {
  const { session } = useAuth();
  const [insight, setInsight] = useState<InsightData | null>(null);
  const [loaded, setLoaded] = useState(false);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<{ kind: "error" | "info"; text: string } | null>(null);
  const requestId = useRef<string | null>(null);
  const activeGoal = useRef<string | null>(goalId);
  activeGoal.current = goalId;

  // Read the saved insight (never creates one). Switching learning shows that learning's own.
  useEffect(() => {
    setNotice(null);
    requestId.current = null;
    if (!session || !goalId) {
      setInsight(null);
      setLoaded(true);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const token = await session.getToken();
        const result = await apiRequest<InsightResponse>(`/api/goals/${encodeURIComponent(goalId)}/insight`, { token });
        if (!cancelled) setInsight(result.insight);
      } catch {
        if (!cancelled) setNotice({ kind: "error", text: "저장된 인사이트를 불러오지 못했어요." });
      } finally {
        if (!cancelled) setLoaded(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, goalId, dataVersion]);

  async function create() {
    if (!session || !goalId || creating) return;
    const startedFor = goalId;
    const key = nextRequestId(requestId.current, newId);
    requestId.current = key;
    setCreating(true);
    setNotice(null);
    try {
      const token = await session.getToken();
      const result = await apiRequest<InsightResponse>(`/api/goals/${encodeURIComponent(goalId)}/insight`, {
        method: "POST",
        token,
        timeoutMs: 70_000, // the server retries the model up to three times
        body: { client_request_id: key },
      });
      if (activeGoal.current !== startedFor) return;
      requestId.current = null;
      if (result.is_insufficient) {
        setNotice({ kind: "info", text: result.message ?? "기록과 회고를 더 남기면 인사이트를 볼 수 있어요." });
      } else {
        setInsight(result.insight);
      }
    } catch (e) {
      if (activeGoal.current !== startedFor) return;
      if (e instanceof ApiError && e.status === 429) {
        // A definite "not now": nothing was created, the next press may use a new key.
        requestId.current = null;
        setNotice({ kind: "info", text: cooldownText(cooldownSeconds(e.details)) });
      } else {
        // Keep the key so "다시 시도" resends the same request. The records on screen are untouched.
        setNotice({ kind: "error", text: e instanceof ApiError ? e.message : "인사이트를 만들지 못했어요. 다시 시도해 주세요." });
      }
    } finally {
      setCreating(false);
    }
  }

  const stale = staleNotice(insight);
  return (
    <section className="card insight-card" aria-label="AI 학습 인사이트">
      <div className="insight-mark">✦</div>
      <div className="insight-copy">
        <div className="insight-heading">
          <div>
            <p className="kicker">AI LEARNING INSIGHT</p>
            <h2>기록에서 찾은 학습 인사이트</h2>
          </div>
          <button type="button" className="btn secondary small" onClick={create} disabled={creating || !loaded || !goalId}>
            {createButtonLabel(insight !== null, creating)}
          </button>
        </div>

        {creating && (
          <p role="status" aria-live="polite">
            {CREATING_TEXT}
          </p>
        )}
        {loaded && !insight && !creating && !notice && <p>{NO_INSIGHT_TEXT}</p>}
        {insight && (
          <div>
            <div className="insight-part">
              <span className="insight-label">진행 요약</span>
              <p>{insight.summary}</p>
            </div>
            {hasDifficulty(insight) && (
              <div className="insight-part">
                <span className="insight-label">반복되는 어려움</span>
                <p>{insight.difficulty}</p>
              </div>
            )}
            <div className="insight-part">
              <span className="insight-label">다음 행동</span>
              <p>{insight.next_action}</p>
            </div>
          </div>
        )}
        {stale && !creating && (
          <p className="small" role="status" style={{ color: "#a97922", fontWeight: 800 }}>
            {stale}
          </p>
        )}
        {notice && !creating && (
          <p className={notice.kind === "error" ? "error" : "small muted"} role={notice.kind === "error" ? "alert" : "status"}>
            {notice.text}
            {/* A failed create keeps its key, so this resends the very same request. */}
            {notice.kind === "error" && requestId.current !== null && (
              <>
                {" "}
                <button type="button" className="link-btn" onClick={create}>
                  다시 시도
                </button>
              </>
            )}
          </p>
        )}
        <small>{footerText(insight?.generated_at ?? null)}</small>
      </div>
    </section>
  );
}
