"use client";

import { useEffect, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import {
  CHOOSABLE_STATUSES,
  FEEDBACK_STATUS_LABEL,
  type FeedbackStatus,
  commentOrPlaceholder,
  feedbackScreenLabel,
  formatAverage,
} from "@/lib/adminLabels";
import { dateTimeKSTLabel } from "@/lib/week";

type FeedbackItem = {
  id: string;
  created_at: string;
  screen: string;
  usability: number;
  ai_usefulness: number;
  comment: string;
  status: FeedbackStatus;
};
type Summary = {
  unseen_count: number;
  usability_avg: number | null;
  usability_count: number;
  ai_usefulness_avg: number | null;
  ai_usefulness_count: number;
  candidate_count: number;
  done_last_30_days: number;
};
type LoadStatus = "loading" | "ready" | "error";

/**
 * Feedback overview for admins (Phase 5E). The status button opens a small inline choice
 * (확인 / 개선 후보 / 반영 완료); only the status can change, never the text.
 */
export function AdminFeedbackScreen() {
  const { session } = useAuth();
  const [items, setItems] = useState<FeedbackItem[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [status, setStatus] = useState<LoadStatus>("loading");
  const [error, setError] = useState<string | null>(null);
  const [openId, setOpenId] = useState<string | null>(null);
  const [changeError, setChangeError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  async function loadSummary(token: string) {
    setSummary(await apiRequest<Summary>("/api/admin/feedback/summary", { token }));
  }

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    (async () => {
      setStatus("loading");
      setError(null);
      try {
        const token = await session.getToken();
        const [list, sum] = await Promise.all([
          apiRequest<FeedbackItem[]>("/api/admin/feedback?status=all&limit=100", { token }),
          apiRequest<Summary>("/api/admin/feedback/summary", { token }),
        ]);
        if (cancelled) return;
        setItems(list);
        setSummary(sum);
        setStatus("ready");
      } catch (e) {
        if (cancelled) return;
        setError(e instanceof ApiError ? e.message : "피드백을 불러오지 못했습니다.");
        setStatus("error");
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [session, reloadKey]);

  async function choose(id: string, next: Exclude<FeedbackStatus, "new">) {
    if (!session) return;
    setChangeError(null);
    try {
      const token = await session.getToken();
      const updated = await apiRequest<FeedbackItem>(`/api/admin/feedback/${encodeURIComponent(id)}`, {
        method: "PATCH",
        token,
        body: { status: next },
      });
      setItems((prev) => prev.map((i) => (i.id === id ? updated : i)));
      setOpenId(null);
      await loadSummary(token);
    } catch (e) {
      setChangeError(e instanceof ApiError ? e.message : "상태를 바꾸지 못했어요. 다시 시도해 주세요.");
    }
  }

  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">ADMIN · USER VOICE</p>
          <h1>사용자 피드백</h1>
          <p>실사용자 의견을 살펴보고 개선 항목을 정리합니다.</p>
        </div>
        {summary && <span className="pill gold">미확인 {summary.unseen_count}건</span>}
      </div>

      {status === "loading" && (
        <section className="card">
          <p className="description">불러오는 중…</p>
        </section>
      )}
      {status === "error" && (
        <section className="card">
          <p className="error" role="alert">
            {error}
          </p>
          <button type="button" className="btn" onClick={() => setReloadKey((k) => k + 1)}>
            다시 시도
          </button>
        </section>
      )}
      {status === "ready" && summary && (
        <>
          <div className="grid stats">
            <article className="card stat">
              <div>
                <label>사용성 평균</label>
                <strong>
                  {formatAverage(summary.usability_avg)} <small>/ 5</small>
                </strong>
                <small>응답 {summary.usability_count}명</small>
              </div>
              <span className="stat-icon">♡</span>
            </article>
            <article className="card stat">
              <div>
                <label>AI 답변 유용성</label>
                <strong>
                  {formatAverage(summary.ai_usefulness_avg)} <small>/ 5</small>
                </strong>
                <small>응답 {summary.ai_usefulness_count}명</small>
              </div>
              <span className="stat-icon">✧</span>
            </article>
            <article className="card stat">
              <div>
                <label>개선 후보</label>
                <strong>{summary.candidate_count}</strong>
                <small>우선순위 검토</small>
              </div>
              <span className="stat-icon">▤</span>
            </article>
            <article className="card stat">
              <div>
                <label>반영 완료</label>
                <strong>{summary.done_last_30_days}</strong>
                <small>최근 30일</small>
              </div>
              <span className="stat-icon">✓</span>
            </article>
          </div>

          <section className="card">
            {changeError && (
              <p className="error" role="alert">
                {changeError}
              </p>
            )}
            {items.length === 0 && <p className="description">아직 받은 피드백이 없어요.</p>}
            {items.map((f) => (
              <div key={f.id} className="wbs-row">
                <span className="wbs-date">{dateTimeKSTLabel(f.created_at).slice(0, 5)}</span>
                <div>
                  <strong>{commentOrPlaceholder(f.comment)}</strong>
                  <p>
                    {feedbackScreenLabel(f.screen)} · 익명 테스터 · 유용성 {f.ai_usefulness}/5
                  </p>
                  {openId === f.id && (
                    <div className="inline-confirm" style={{ marginTop: 6 }}>
                      {CHOOSABLE_STATUSES.map((s) => (
                        <button
                          key={s}
                          type="button"
                          className={`chip${f.status === s ? " on" : ""}`}
                          onClick={() => choose(f.id, s)}
                        >
                          {FEEDBACK_STATUS_LABEL[s]}
                        </button>
                      ))}
                    </div>
                  )}
                </div>
                <button
                  type="button"
                  className="btn secondary small"
                  aria-expanded={openId === f.id}
                  onClick={() => setOpenId(openId === f.id ? null : f.id)}
                >
                  {FEEDBACK_STATUS_LABEL[f.status]}
                </button>
              </div>
            ))}
          </section>
        </>
      )}
    </>
  );
}
