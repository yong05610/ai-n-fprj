"use client";

import { useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ApiError, apiRequest } from "@/lib/api";
import { splitAnswer } from "@/lib/richText";
import {
  RELATED_LINKS_HEADING,
  SEARCH_LINKS_HEADING,
  SEARCH_LINKS_WARNING,
  type SearchLink,
  visibleSearchLinks,
} from "@/lib/searchLinks";
import { type TutorMessage, latestExtraLinks, latestSources, parseSummaryLines, referencePanelState, shortenText } from "@/lib/tutorState";
import { buildHash, parseHash } from "@/lib/viewHash";
import { dateTimeKSTLabel, timeKSTLabel } from "@/lib/week";

type ConversationItem = { id: string; title: string; created_at: string; updated_at: string };
type Conversation = { id: string; title: string; messages: TutorMessage[] };
type DataSummary = {
  learning_summary: string;
  recent_reflections: { id: string; study_date: string; task_title: string; content: string }[];
};
type SendResult = {
  user_message: TutorMessage;
  assistant_message: TutorMessage;
  conversation_title: string;
  refused: boolean;
};

const AI_TIMEOUT_MS = 70_000; // the server retries up to 3 times a ~20s provider call
const NEW_TITLE = "새 대화";

function newRequestId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function setHash(conversationId: string | null) {
  window.history.replaceState(null, "", buildHash("tutor", conversationId));
}

function AnswerText({ text }: { text: string }) {
  return (
    <span style={{ whiteSpace: "pre-wrap" }}>
      {splitAnswer(text).map((seg, i) =>
        seg.kind === "block" ? (
          <pre key={i} className="code-block">
            {seg.text}
          </pre>
        ) : seg.kind === "inline" ? (
          <code key={i}>{seg.text}</code>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </span>
  );
}

function SearchLinkRow({ links }: { links: SearchLink[] }) {
  const shown = visibleSearchLinks(links);
  if (shown.length === 0) return null;
  return (
    <span className="search-links" style={{ display: "block" }}>
      <span className="small muted">{SEARCH_LINKS_HEADING}: </span>
      {shown.map((l) => (
        <a key={l.url} href={l.url} target="_blank" rel="noreferrer" style={{ marginRight: 8 }}>
          {l.label} ↗
        </a>
      ))}
    </span>
  );
}

export function TutorScreen() {
  const { session } = useAuth();
  const [items, setItems] = useState<ConversationItem[]>([]);
  const [listError, setListError] = useState<string | null>(null);
  const [current, setCurrent] = useState<Conversation | null>(null); // null = a new, not yet created conversation
  const [opening, setOpening] = useState(true);
  const [openError, setOpenError] = useState<string | null>(null);
  const [summary, setSummary] = useState<DataSummary | null>(null);
  const [summaryFailed, setSummaryFailed] = useState(false);

  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  // The text being sent (or that failed) and its idempotency key: retrying the same text reuses
  // the key, so a request that actually succeeded is never saved twice.
  const [pending, setPending] = useState<{ text: string; requestId: string } | null>(null);
  const createKey = useRef<string>(newRequestId());
  const bottomRef = useRef<HTMLDivElement | null>(null);

  async function token(): Promise<string> {
    return (await session!.getToken()) as string;
  }

  async function loadList() {
    try {
      setItems(await apiRequest<ConversationItem[]>("/api/conversations", { token: await token() }));
      setListError(null);
    } catch (e) {
      setListError(e instanceof ApiError ? e.message : "대화 목록을 불러오지 못했습니다.");
    }
  }

  async function loadSummary() {
    try {
      setSummary(await apiRequest<DataSummary>("/api/data/summary", { token: await token() }));
      setSummaryFailed(false);
    } catch {
      setSummary(null); // the side panel is a convenience; chatting still works
      setSummaryFailed(true);
    }
  }

  async function openConversation(id: string) {
    setOpening(true);
    setOpenError(null);
    try {
      const detail = await apiRequest<Conversation>(`/api/conversations/${encodeURIComponent(id)}`, { token: await token() });
      setCurrent(detail);
      setHash(detail.id);
    } catch (e) {
      if (e instanceof ApiError && (e.status === 403 || e.status === 404)) {
        // Someone else's or a missing id (stale hash): quietly show a new conversation instead.
        setCurrent(null);
        setHash(null);
      } else {
        setOpenError(e instanceof ApiError ? e.message : "대화를 불러오지 못했습니다.");
      }
    } finally {
      setOpening(false);
    }
  }

  useEffect(() => {
    if (!session) return;
    const { param } = parseHash(window.location.hash);
    loadList();
    loadSummary();
    if (param) openConversation(param);
    else setOpening(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView?.({ block: "end" });
  }, [current?.messages.length, sending]);

  function startNew() {
    if (sending) return;
    setCurrent(null);
    setHash(null);
    setInput("");
    setPending(null);
    setSendError(null);
    createKey.current = newRequestId();
  }

  async function send(text: string) {
    if (!session || sending || !text.trim()) return;
    const requestId = pending && pending.text === text ? pending.requestId : newRequestId();
    setPending({ text, requestId });
    setSending(true);
    setSendError(null);
    try {
      const t = await token();
      let conv = current;
      if (!conv) {
        const created = await apiRequest<Conversation>("/api/conversations", {
          method: "POST",
          token: t,
          body: { client_request_id: createKey.current },
        });
        conv = created;
        setCurrent(created);
        setHash(created.id);
      }
      const result = await apiRequest<SendResult>(`/api/conversations/${encodeURIComponent(conv.id)}/messages`, {
        method: "POST",
        token: t,
        timeoutMs: AI_TIMEOUT_MS,
        body: { content: text, client_request_id: requestId },
      });
      const nextConv: Conversation = {
        id: conv.id,
        title: result.conversation_title,
        messages: [...conv.messages, result.user_message, result.assistant_message],
      };
      setCurrent(nextConv);
      setInput("");
      setPending(null);
      createKey.current = newRequestId();
      setItems((prev) => {
        const entry: ConversationItem = {
          id: nextConv.id,
          title: nextConv.title,
          created_at: prev.find((i) => i.id === nextConv.id)?.created_at ?? result.assistant_message.timestamp,
          updated_at: result.assistant_message.timestamp,
        };
        return [entry, ...prev.filter((i) => i.id !== nextConv.id)];
      });
    } catch (e) {
      // Keep the typed text (and the idempotency key) so "다시 시도" can resend it.
      setSendError(e instanceof ApiError ? e.message : "답변을 받지 못했습니다. 다시 시도해 주세요.");
    } finally {
      setSending(false);
    }
  }

  const messages = current?.messages ?? [];
  const refState = referencePanelState(messages);
  const sources = latestSources(messages);
  const extra = latestExtraLinks(messages);
  const summaryLines = summary ? parseSummaryLines(summary.learning_summary) : [];

  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">AI STUDY TUTOR</p>
          <h1>학습 질문과 답변</h1>
          <p>등록 자료와 나의 학습 회고를 참고해 답변합니다. 이전 대화를 이어서 질문할 수 있어요.</p>
        </div>
        <span className="pill">자료 검색 + 내 회고</span>
      </div>
      <p className="scope-note">
        진행 중인 모든 학습과 학습 방법·요령에 관한 질문에 답해요. 학습과 관련 없는 질문에는 답변하지 않습니다.
      </p>

      <div className="grid tutor-layout">
        <aside className="card conversation-panel">
          <div className="card-head">
            <div>
              <h2>대화 기록</h2>
              <p>최근 대화를 선택해 이어가세요.</p>
            </div>
            <button type="button" className="btn small" onClick={startNew} disabled={sending}>
              ＋ 새 대화
            </button>
          </div>
          {listError && (
            <p className="error" role="alert">
              {listError}{" "}
              <button type="button" className="link-btn" onClick={loadList}>
                다시 시도
              </button>
            </p>
          )}
          <div className="conversation-list" aria-label="이전 대화 목록">
            {items.map((c) => (
              <button
                type="button"
                key={c.id}
                className={`conversation-item${current?.id === c.id ? " active" : ""}`}
                onClick={() => openConversation(c.id)}
                disabled={sending}
              >
                <strong>{c.title}</strong>
                <span>{dateTimeKSTLabel(c.updated_at)}</span>
              </button>
            ))}
          </div>
          {items.length === 0 && !listError && (
            <p className="small muted conversation-note">아직 대화가 없어요. 질문을 보내면 여기에 쌓여요.</p>
          )}
        </aside>

        <section className="card chat">
          <div className="card-head">
            <div>
              <h2>{current?.title ?? NEW_TITLE}</h2>
              <p>AI가 생성한 설명은 참고용이며, 정확성과 출처를 확인해 주세요.</p>
            </div>
            <span className="pill blue">학습 요약·회고 활용</span>
          </div>

          {openError && (
            <p className="error" role="alert">
              {openError}{" "}
              <button type="button" className="link-btn" onClick={() => parseHash(window.location.hash).param && openConversation(parseHash(window.location.hash).param as string)}>
                다시 시도
              </button>
            </p>
          )}

          <div className="messages" aria-live="polite">
            {opening && <p className="small muted">대화를 불러오는 중…</p>}
            {!opening && messages.length === 0 && !sending && (
              <p className="small muted">궁금한 학습 질문을 입력해 보세요. 예: 리스트와 딕셔너리는 언제 각각 쓰나요?</p>
            )}
            {messages.map((m, i) => (
              <div key={`${m.timestamp}-${i}`} className={`bubble${m.role === "user" ? " user" : ""}`}>
                {m.role === "assistant" ? <AnswerText text={m.content} /> : <span style={{ whiteSpace: "pre-wrap" }}>{m.content}</span>}
                {m.role === "assistant" && m.sources.length === 0 && <SearchLinkRow links={m.search_links ?? []} />}
                <small>
                  {m.role === "assistant" ? "AI 생성 · 참고용 · " : ""}
                  {timeKSTLabel(m.timestamp)}
                  {m.role === "assistant" && m.sources.length > 0 && ` · 출처 ${m.sources.map((s) => s.title).join(", ")}`}
                </small>
              </div>
            ))}
            {sending && pending && (
              <>
                <div className="bubble user">
                  <span style={{ whiteSpace: "pre-wrap" }}>{pending.text}</span>
                </div>
                <div className="bubble" role="status">
                  <span>답변을 만드는 중이에요…</span>
                </div>
              </>
            )}
            <div ref={bottomRef} />
          </div>

          {sendError && (
            <p className="error" role="alert">
              {sendError}{" "}
              <button type="button" className="link-btn" onClick={() => pending && send(pending.text)} disabled={sending || !pending}>
                다시 시도
              </button>
            </p>
          )}

          <form
            className="composer"
            onSubmit={(e) => {
              e.preventDefault();
              send(input);
            }}
          >
            <input
              aria-label="질문"
              placeholder="질문을 입력하세요"
              value={input}
              maxLength={1000}
              autoComplete="off"
              disabled={sending}
              onChange={(e) => setInput(e.target.value)}
            />
            <button className="btn" type="submit" disabled={sending || !input.trim()}>
              {sending ? "답변 중…" : "보내기"}
            </button>
          </form>
        </section>

        <aside className="card tutor-context">
          <h2>답변 참고 정보</h2>
          <div className="context-block">
            <span className="pill blue">학습 요약</span>
            {summaryLines.length === 0 && summaryFailed && (
              <p className="small muted">
                학습 요약을 불러오지 못했어요.{" "}
                <button type="button" className="link-btn" onClick={() => void loadSummary()}>
                  다시 시도
                </button>
              </p>
            )}
            {summaryLines.length === 0 && !summaryFailed && <p className="small muted">학습 요약을 불러오는 중이거나 아직 없어요.</p>}
            {summaryLines.map((line) => (
              <div key={line.title}>
                <p>{line.title}</p>
                {line.levels && <p className="small muted">{line.levels}</p>}
              </div>
            ))}
          </div>
          <div className="context-block">
            <span className="pill gold">최근 회고</span>
            {summary && summary.recent_reflections.length === 0 && <p className="small muted">아직 남긴 회고가 없어요.</p>}
            {summary?.recent_reflections.slice(0, 3).map((r) => (
              <p key={r.id}>“{shortenText(r.content, 80)}”</p>
            ))}
          </div>
          <h3>참고자료</h3>
          {refState === "ask" && <p className="small muted">질문하면 답변에 쓴 참고자료가 여기에 표시돼요.</p>}
          {refState === "none" && <p className="small muted">참고한 자료가 없어요. 일반적인 학습 조언이에요.</p>}
          {refState === "sources" &&
            sources.map((s) => (
              <div key={s.doc_id} className="resource">
                <strong>{s.title}</strong>
                <p>{s.source_name}</p>
                {s.url && (
                  <a href={s.url} target="_blank" rel="noreferrer">
                    원문 보기 ↗
                  </a>
                )}
              </div>
            ))}
          {extra.related.length > 0 && (
            <>
              <h3>{RELATED_LINKS_HEADING}</h3>
              {extra.related.map((l) => (
                <div key={l.url} className="resource">
                  <strong>{l.title}</strong>
                  {l.source_name && <p>{l.source_name}</p>}
                  <a href={l.url} target="_blank" rel="noreferrer">
                    원문 보기 ↗
                  </a>
                </div>
              ))}
            </>
          )}
          {extra.search.length > 0 && (
            <>
              <h3>{SEARCH_LINKS_HEADING}</h3>
              {extra.search.map((l) => (
                <div key={l.url} className="resource">
                  <a href={l.url} target="_blank" rel="noreferrer">
                    {l.label} ↗
                  </a>
                </div>
              ))}
              <p className="small muted">{SEARCH_LINKS_WARNING}</p>
            </>
          )}
          <p className="small muted">요약과 회고는 본인 UID의 기록만 사용합니다.</p>
        </aside>
      </div>
    </>
  );
}
