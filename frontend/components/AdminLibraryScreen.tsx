"use client";

import { type FormEvent, useCallback, useEffect, useRef, useState } from "react";

import { useAuth } from "@/components/AuthProvider";
import { ResourceCandidateCard } from "@/components/ResourceCandidateCard";
import { requestIdFor } from "@/lib/adminLabels";
import {
  AI_TOPIC_NOTICE,
  type CandidateList,
  type CollectResult,
  type CollectorInfo,
  type Edits,
  type FieldDemandItem,
  type ResourceCandidate,
  type StatsEntry,
  collectSummary,
  collectorOff,
  collectorUsageLabel,
  demandAreaVisible,
  durationLabel,
  editsPayload,
  listView,
  percent,
  autoRejectLabel,
} from "@/lib/adminResources";
import { ApiError, apiRequest } from "@/lib/api";

type Tab = "pending" | "done";
type DoneFilter = "all" | "approved" | "rejected_admin" | "rejected_system";
type Loaded<T> = { data: T | null; failed: boolean };
type DemandOutcome = { kind: "ok"; items: FieldDemandItem[] } | { kind: "off" } | { kind: "error" };
type Message = { kind: "ok" | "error"; text: string } | null;

const LINK_TIMEOUT_MS = 90_000;
const TOPIC_TIMEOUT_MS = 200_000;

function newId(): string {
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

function errorText(e: unknown, fallback: string): string {
  return e instanceof ApiError ? e.message : fallback;
}

/**
 * Reference material collection and approval (Phase 8B, admin only). The screen only sends requests:
 * reading outside addresses, the AI and the storage are the server's. Writes are sent once and never
 * repeated by the app; a failed one shows its error and the admin presses the button again (the same
 * form content keeps the same client_request_id, so a repeat does not create a second candidate).
 */
export function AdminLibraryScreen() {
  const { session } = useAuth();
  const [collectors, setCollectors] = useState<Loaded<CollectorInfo[]>>({ data: null, failed: false });
  const [pending, setPending] = useState<Loaded<CandidateList>>({ data: null, failed: false });
  const [done, setDone] = useState<Loaded<ResourceCandidate[]>>({ data: null, failed: false });
  const [stats, setStats] = useState<Loaded<{ overall: StatsEntry; collectors: StatsEntry[] }>>({ data: null, failed: false });
  const [demand, setDemand] = useState<DemandOutcome | null>(null);
  const [tab, setTab] = useState<Tab>("pending");
  const [doneFilter, setDoneFilter] = useState<DoneFilter>("all");

  const [link, setLink] = useState({ url: "", field: "", course: "", note: "" });
  const [linkBusy, setLinkBusy] = useState(false);
  const [linkMessage, setLinkMessage] = useState<Message>(null);
  const linkRequest = useRef<{ key: string; requestId: string } | null>(null);

  const [topic, setTopic] = useState({ field: "", course: "", count: 3 });
  const [topicBusy, setTopicBusy] = useState(false);
  const [topicMessage, setTopicMessage] = useState<Message>(null);
  const topicRequest = useRef<{ key: string; requestId: string } | null>(null);

  const [busyId, setBusyId] = useState<string | null>(null);
  const [cardErrors, setCardErrors] = useState<Record<string, { text: string; needsEdit: boolean }>>({});

  const token = useCallback(async () => (session ? session.getToken() : ""), [session]);

  const loadCollectors = useCallback(async () => {
    try {
      const body = await apiRequest<{ items: CollectorInfo[] }>("/api/admin/resources/collectors", { token: await token() });
      setCollectors({ data: body.items, failed: false });
    } catch {
      setCollectors((c) => ({ data: c.data, failed: true }));
    }
  }, [token]);

  const loadPending = useCallback(async () => {
    try {
      const body = await apiRequest<CandidateList>("/api/admin/resources/candidates?status=pending", { token: await token() });
      setPending({ data: body, failed: false });
    } catch {
      setPending((p) => ({ data: p.data, failed: true }));
    }
  }, [token]);

  const loadDone = useCallback(async () => {
    try {
      const t = await token();
      const [approved, rejected] = await Promise.all([
        apiRequest<CandidateList>("/api/admin/resources/candidates?status=approved", { token: t }),
        apiRequest<CandidateList>("/api/admin/resources/candidates?status=rejected", { token: t }),
      ]);
      const merged = [...approved.items, ...rejected.items].sort((a, b) =>
        (b.reviewed_at ?? b.created_at).localeCompare(a.reviewed_at ?? a.created_at),
      );
      setDone({ data: merged, failed: false });
    } catch {
      setDone((d) => ({ data: d.data, failed: true }));
    }
  }, [token]);

  const loadStats = useCallback(async () => {
    try {
      setStats({ data: await apiRequest("/api/admin/resources/stats", { token: await token() }), failed: false });
    } catch {
      setStats((s) => ({ data: s.data, failed: true }));
    }
  }, [token]);

  const loadDemand = useCallback(async () => {
    try {
      const body = await apiRequest<{ items: FieldDemandItem[] }>("/api/admin/resources/field-demand", { token: await token() });
      setDemand({ kind: "ok", items: body.items });
    } catch (e) {
      // 404 = the feature is off (the normal state): the whole area, its title included, stays hidden.
      setDemand(e instanceof ApiError && e.status === 404 ? { kind: "off" } : { kind: "error" });
    }
  }, [token]);

  useEffect(() => {
    if (!session) return;
    void loadCollectors();
    void loadPending();
    void loadStats();
    void loadDemand();
  }, [session, loadCollectors, loadPending, loadStats, loadDemand]);

  useEffect(() => {
    if (session && tab === "done" && done.data === null && !done.failed) void loadDone();
  }, [session, tab, done, loadDone]);

  async function refreshAfterChange() {
    await Promise.all([loadPending(), loadCollectors(), loadStats(), done.data !== null ? loadDone() : Promise.resolve()]);
  }

  async function submitLink(event: FormEvent) {
    event.preventDefault();
    if (!session || linkBusy) return;
    if (!link.url.trim()) {
      setLinkMessage({ kind: "error", text: "검토할 링크를 입력해 주세요." });
      return;
    }
    setLinkBusy(true);
    setLinkMessage(null);
    linkRequest.current = requestIdFor(linkRequest.current, JSON.stringify(link), newId);
    try {
      const result = await apiRequest<CollectResult>("/api/admin/resources/candidates", {
        method: "POST",
        token: await token(),
        body: {
          url: link.url.trim(),
          field: link.field.trim() || undefined,
          course: link.course.trim() || undefined,
          note: link.note.trim() || undefined,
          client_request_id: linkRequest.current.requestId,
        },
        timeoutMs: LINK_TIMEOUT_MS,
      });
      setLinkMessage({ kind: "ok", text: collectSummary(result) });
      setLink({ url: "", field: "", course: "", note: "" });
      linkRequest.current = null;
      await refreshAfterChange();
    } catch (e) {
      setLinkMessage({ kind: "error", text: errorText(e, "링크를 처리하지 못했습니다. 다시 시도해 주세요.") });
    } finally {
      setLinkBusy(false);
    }
  }

  async function submitTopic(event: FormEvent) {
    event.preventDefault();
    if (!session || topicBusy) return;
    if (!topic.field.trim() || !topic.course.trim()) {
      setTopicMessage({ kind: "error", text: "분야와 과정을 입력해 주세요." });
      return;
    }
    setTopicBusy(true);
    setTopicMessage(null);
    topicRequest.current = requestIdFor(topicRequest.current, JSON.stringify(topic), newId);
    try {
      const result = await apiRequest<CollectResult>("/api/admin/resources/collect", {
        method: "POST",
        token: await token(),
        body: {
          collector: "ai_topic",
          field: topic.field.trim(),
          course: topic.course.trim(),
          count: topic.count,
          client_request_id: topicRequest.current.requestId,
        },
        timeoutMs: TOPIC_TIMEOUT_MS,
      });
      setTopicMessage({ kind: "ok", text: collectSummary(result) });
      topicRequest.current = null;
      await refreshAfterChange();
    } catch (e) {
      setTopicMessage({ kind: "error", text: errorText(e, "AI 수집에 실패했습니다. 다시 시도해 주세요.") });
    } finally {
      setTopicBusy(false);
    }
  }

  async function decide(candidate: ResourceCandidate, body: Record<string, unknown>) {
    if (!session || busyId) return;
    setBusyId(candidate.id);
    setCardErrors(({ [candidate.id]: _removed, ...rest }) => rest);
    try {
      await apiRequest<ResourceCandidate>(`/api/admin/resources/candidates/${encodeURIComponent(candidate.id)}`, {
        method: "PATCH",
        token: await token(),
        body,
      });
      await refreshAfterChange();
    } catch (e) {
      const needsEdit = e instanceof ApiError && e.status === 422 && body.action === "approve" && !body.edits;
      setCardErrors((prev) => ({
        ...prev,
        [candidate.id]: { text: errorText(e, "처리하지 못했습니다. 다시 시도해 주세요."), needsEdit },
      }));
    } finally {
      setBusyId(null);
    }
  }

  const collectorList = collectors.data ?? [];
  const linkOff = collectors.data !== null && collectorOff(collectorList, "direct_link");
  const topicOff = collectors.data !== null && collectorOff(collectorList, "ai_topic");
  const pendingItems = pending.data?.items ?? [];
  const doneItems = (done.data ?? []).filter((c) => {
    if (doneFilter === "approved") return c.status === "approved";
    if (doneFilter === "rejected_admin") return c.status === "rejected" && c.reviewed_by === "admin";
    if (doneFilter === "rejected_system") return c.status === "rejected" && c.reviewed_by === "system";
    return true;
  });

  function renderCards(items: ResourceCandidate[]) {
    return items.map((c) => (
      <ResourceCandidateCard
        key={c.id}
        candidate={c}
        collectors={collectorList}
        busy={busyId !== null}
        error={cardErrors[c.id]?.text ?? null}
        needsEdit={cardErrors[c.id]?.needsEdit ?? false}
        onApprove={(edits: Edits | null) => decide(c, { action: "approve", ...(edits ? { edits: editsPayload(edits) } : {}) })}
        onReject={(reason) => decide(c, { action: "reject", reject_reason: reason })}
      />
    ));
  }

  function listBlock(view: ReturnType<typeof listView>, items: ResourceCandidate[], emptyText: string, reload: () => void) {
    if (view === "loading")
      return (
        <section className="card resource-section">
          <p className="description">불러오는 중…</p>
        </section>
      );
    if (view === "error")
      return (
        <section className="card resource-section">
          <p className="error" role="alert">
            목록을 불러오지 못했어요. 잠시 후 다시 시도해 주세요.
          </p>
          <button type="button" className="btn" onClick={reload}>
            다시 시도
          </button>
        </section>
      );
    if (view === "empty")
      return (
        <section className="card resource-section">
          <p className="description">{emptyText}</p>
        </section>
      );
    return <>{renderCards(items)}</>;
  }

  return (
    <>
      <div className="heading">
        <div>
          <p className="kicker">ADMIN · REFERENCE LIBRARY</p>
          <h1>참고자료 관리</h1>
          <p>링크를 모아 검사하고, 검토한 자료만 학습자에게 참고 링크로 보여줍니다.</p>
        </div>
      </div>
      <div className="admin-banner">
        수집은 관리자가 버튼을 누를 때만 일어나요. 검토 대기 자료는 학습자에게 보이지 않고, 승인한 자료만 참고 링크가 돼요.
      </div>

      <section className="card table-wrap resource-section">
        <h3>수집기 상태</h3>
        {collectors.failed && collectors.data === null ? (
          <>
            <p className="error" role="alert">
              수집기 상태를 불러오지 못했어요.
            </p>
            <button type="button" className="btn secondary small" onClick={() => void loadCollectors()}>
              다시 시도
            </button>
          </>
        ) : collectors.data === null ? (
          <p className="description">불러오는 중…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>수집기</th>
                <th>상태</th>
                <th>오늘 사용량</th>
              </tr>
            </thead>
            <tbody>
              {collectorList.map((c) => (
                <tr key={c.type}>
                  <td>{c.label}</td>
                  <td>
                    <span className={`pill${c.enabled ? "" : " gray"}`}>{c.enabled ? "켜짐" : "꺼짐"}</span>
                  </td>
                  <td>{collectorUsageLabel(c)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      <section className="card resource-section">
        <h3>링크 직접 입력</h3>
        <form onSubmit={submitLink}>
          <div className="field">
            <label htmlFor="lib-url">링크 (https)</label>
            <input id="lib-url" value={link.url} onChange={(e) => setLink({ ...link, url: e.target.value })} autoComplete="off" placeholder="https://" />
          </div>
          <div className="field-grid three">
            <div className="field">
              <label htmlFor="lib-link-field">분야 (선택)</label>
              <input id="lib-link-field" value={link.field} maxLength={40} onChange={(e) => setLink({ ...link, field: e.target.value })} autoComplete="off" />
            </div>
            <div className="field">
              <label htmlFor="lib-link-course">과정 (선택)</label>
              <input id="lib-link-course" value={link.course} maxLength={60} onChange={(e) => setLink({ ...link, course: e.target.value })} autoComplete="off" />
            </div>
            <div className="field">
              <label htmlFor="lib-link-note">메모 (선택)</label>
              <input id="lib-link-note" value={link.note} maxLength={100} onChange={(e) => setLink({ ...link, note: e.target.value })} autoComplete="off" />
            </div>
          </div>
          <button type="submit" className="btn" disabled={linkBusy || linkOff}>
            {linkOff ? "꺼짐" : linkBusy ? "검사하는 중…" : "검사하고 후보 만들기"}
          </button>
          {linkBusy && <p className="small muted">링크를 열어 확인하고 AI 제안을 받는 중이에요. 잠시만 기다려 주세요.</p>}
          {linkMessage && (
            <p className={linkMessage.kind === "error" ? "error" : "small"} role={linkMessage.kind === "error" ? "alert" : "status"}>
              {linkMessage.text}
            </p>
          )}
        </form>
      </section>

      <section className="card resource-section">
        <h3>AI 주제 제안</h3>
        <p className="small muted">{AI_TOPIC_NOTICE}</p>
        <form onSubmit={submitTopic}>
          <div className="field-grid three">
            <div className="field">
              <label htmlFor="lib-topic-field">분야</label>
              <input id="lib-topic-field" value={topic.field} maxLength={40} onChange={(e) => setTopic({ ...topic, field: e.target.value })} autoComplete="off" />
            </div>
            <div className="field">
              <label htmlFor="lib-topic-course">과정</label>
              <input id="lib-topic-course" value={topic.course} maxLength={60} onChange={(e) => setTopic({ ...topic, course: e.target.value })} autoComplete="off" />
            </div>
            <div className="field">
              <label htmlFor="lib-topic-count">개수</label>
              <select id="lib-topic-count" value={topic.count} onChange={(e) => setTopic({ ...topic, count: Number(e.target.value) })}>
                {[1, 2, 3, 4, 5].map((n) => (
                  <option key={n} value={n}>
                    {n}개
                  </option>
                ))}
              </select>
            </div>
          </div>
          <button type="submit" className="btn" disabled={topicBusy || topicOff}>
            {topicOff ? "꺼짐" : topicBusy ? "AI 가 찾고 검사하는 중…" : "AI 에게 링크 제안받기"}
          </button>
          {topicBusy && <p className="small muted">AI 가 링크를 찾고 하나씩 열어 확인하는 중이에요. 최대 1~2분 걸릴 수 있어요.</p>}
          {topicMessage && (
            <p className={topicMessage.kind === "error" ? "error" : "small"} role={topicMessage.kind === "error" ? "alert" : "status"}>
              {topicMessage.text}
            </p>
          )}
        </form>
      </section>

      <div className="chip-row" role="tablist" aria-label="후보 목록">
        <button type="button" role="tab" aria-selected={tab === "pending"} className={`chip${tab === "pending" ? " on" : ""}`} onClick={() => setTab("pending")}>
          검토 대기{pending.data ? ` ${pending.data.total}` : ""}
        </button>
        <button type="button" role="tab" aria-selected={tab === "done"} className={`chip${tab === "done" ? " on" : ""}`} onClick={() => setTab("done")}>
          처리 완료
        </button>
        {tab === "done" && (
          <select className="weekday-select" aria-label="처리 완료 필터" value={doneFilter} onChange={(e) => setDoneFilter(e.target.value as DoneFilter)}>
            <option value="all">전체</option>
            <option value="approved">승인</option>
            <option value="rejected_admin">반려</option>
            <option value="rejected_system">자동 반려</option>
          </select>
        )}
      </div>

      {tab === "pending" &&
        listBlock(
          listView(pending.data !== null, pending.failed, pendingItems.length),
          pendingItems,
          "검토를 기다리는 자료가 없어요. 위에서 링크를 입력하거나 AI 제안을 받아 보세요.",
          () => void loadPending(),
        )}
      {tab === "done" &&
        listBlock(
          listView(done.data !== null, done.failed, doneItems.length),
          doneItems,
          "처리한 자료가 아직 없어요.",
          () => void loadDone(),
        )}

      <section className="card table-wrap resource-section">
        <h3>수집 통계</h3>
        {stats.failed && stats.data === null ? (
          <>
            <p className="error" role="alert">
              통계를 불러오지 못했어요.
            </p>
            <button type="button" className="btn secondary small" onClick={() => void loadStats()}>
              다시 시도
            </button>
          </>
        ) : stats.data === null ? (
          <p className="description">불러오는 중…</p>
        ) : (
          <table>
            <thead>
              <tr>
                <th>수집기</th>
                <th>후보</th>
                <th>승인</th>
                <th>반려</th>
                <th>자동 반려</th>
                <th>승인율</th>
                <th>승인까지(중앙값)</th>
              </tr>
            </thead>
            <tbody>
              {stats.data.collectors.map((s) => (
                <tr key={s.collector_type ?? "all"}>
                  <td>{s.label ?? s.collector_type}</td>
                  <td>{s.total}</td>
                  <td>{s.approved}</td>
                  <td>{s.rejected_by_admin}</td>
                  <td>
                    {s.auto_rejected}
                    {s.auto_rejected > 0 && (
                      <small className="muted">
                        {" "}
                        (
                        {Object.entries(s.auto_rejected_reasons)
                          .map(([code, n]) => `${autoRejectLabel(code)} ${n}`)
                          .join(", ")}
                        )
                      </small>
                    )}
                  </td>
                  <td>{percent(s.approval_rate)}</td>
                  <td>{durationLabel(s.median_seconds_to_approve)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {demand !== null && demandAreaVisible(demand) && demand.kind === "ok" && (
        <section className="card table-wrap resource-section">
          <h3>분야별 수요</h3>
          <p className="small muted">서로 다른 사용자 수 기준이에요. 사용자가 적은 분야는 표시하지 않아요.</p>
          {demand.items.length === 0 ? (
            <p className="description">표시할 분야가 아직 없어요.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>분야</th>
                  <th>사용자 수</th>
                  <th>연결된 자료</th>
                </tr>
              </thead>
              <tbody>
                {demand.items.map((d) => (
                  <tr key={d.field}>
                    <td>{d.field}</td>
                    <td>{d.user_count}명</td>
                    <td>{d.linked_document_count === 0 ? <span className="pill gold">자료 공백</span> : `${d.linked_document_count}건`}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      )}
    </>
  );
}
