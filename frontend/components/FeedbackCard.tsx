"use client";

import { useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { FEEDBACK_SCREEN_OPTIONS, type FeedbackScreenKey, requestIdFor } from "@/lib/adminLabels";

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `fb-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

type Phase = "idle" | "sending" | "sent" | "error" | "limit";

/**
 * "테스트 피드백" card of the settings screen (Phase 5E). The server stores the answer without
 * any user information, so there is nothing to delete afterwards - the note under the comment
 * field says so. A failed send keeps the form and is retried with the same idempotency key.
 */
export function FeedbackCard() {
  const { session } = useAuth();
  const [usability, setUsability] = useState("");
  const [aiUsefulness, setAiUsefulness] = useState("");
  const [screen, setScreen] = useState<FeedbackScreenKey>("dashboard");
  const [comment, setComment] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [message, setMessage] = useState<string | null>(null);
  const request = useRef<{ key: string; requestId: string } | null>(null);

  const ready = usability !== "" && aiUsefulness !== "" && phase !== "sending";

  async function submit() {
    if (!session || !ready) return;
    const key = JSON.stringify([usability, aiUsefulness, screen, comment]);
    request.current = requestIdFor(request.current, key, newId);
    setPhase("sending");
    setMessage(null);
    try {
      await apiRequest("/api/feedback", {
        method: "POST",
        token: await session.getToken(),
        body: {
          usability: Number(usability),
          ai_usefulness: Number(aiUsefulness),
          screen,
          comment: comment.trim() || undefined,
          client_request_id: request.current.requestId,
        },
      });
      setPhase("sent");
      setUsability("");
      setAiUsefulness("");
      setScreen("dashboard");
      setComment("");
      request.current = null;
    } catch (e) {
      if (e instanceof ApiError && e.status === 429) {
        setPhase("limit");
        setMessage("이번 테스트에서 보낼 수 있는 피드백 수를 넘었어요.");
      } else {
        setPhase("error");
        setMessage(e instanceof ApiError ? e.message : "보내지 못했어요. 입력한 내용은 그대로 두었어요. 다시 시도해 주세요.");
      }
    }
  }

  const scoreOptions = [5, 4, 3, 2, 1];
  return (
    <section className="card" id="feedback-card" style={{ marginTop: 13 }}>
      <h2>테스트 피드백</h2>
      <p className="small muted">사용해 본 느낌을 알려 주세요. 제출은 선택입니다.</p>
      <div className="field">
        <label htmlFor="fb-usability">사용 편의성 (1~5)</label>
        <select id="fb-usability" value={usability} onChange={(e) => setUsability(e.target.value)}>
          <option value="" disabled>
            선택하세요
          </option>
          {scoreOptions.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="fb-ai">AI 답변 유용성 (1~5)</label>
        <select id="fb-ai" value={aiUsefulness} onChange={(e) => setAiUsefulness(e.target.value)}>
          <option value="" disabled>
            선택하세요
          </option>
          {scoreOptions.map((n) => (
            <option key={n} value={n}>
              {n}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="fb-screen">어느 화면에 대한 의견인가요</label>
        <select id="fb-screen" value={screen} onChange={(e) => setScreen(e.target.value as FeedbackScreenKey)}>
          {FEEDBACK_SCREEN_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="fb-comment">의견 (선택, 1000자 이하)</label>
        <textarea
          id="fb-comment"
          rows={3}
          maxLength={1000}
          value={comment}
          placeholder="불편했던 점이나 바라는 점을 적어 주세요"
          onChange={(e) => setComment(e.target.value)}
        />
      </div>
      <p className="small muted">피드백에는 사용자 정보가 저장되지 않아 제출 후 삭제 요청으로 지울 수 없어요.</p>
      {phase === "sent" && (
        <p className="small" role="status" style={{ color: "#248160", fontWeight: 800 }}>
          보내 주셔서 고마워요
        </p>
      )}
      {(phase === "error" || phase === "limit") && message && (
        <p className="error" role="alert">
          {message}
        </p>
      )}
      <button type="button" className="btn" id="feedback-send" onClick={submit} disabled={!ready || phase === "limit"}>
        {phase === "sending" ? "보내는 중…" : phase === "error" ? "다시 시도" : "피드백 보내기"}
      </button>
    </section>
  );
}
