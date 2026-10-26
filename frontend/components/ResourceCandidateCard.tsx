"use client";

import { useEffect, useState } from "react";

import {
  type CollectorInfo,
  type Edits,
  type ResourceCandidate,
  checkStageSummary,
  collectorLabel,
  editsFromCandidate,
  isSafeHttpsUrl,
  rejectReasonLabel,
} from "@/lib/adminResources";
import { dateTimeKSTLabel } from "@/lib/week";

type Props = {
  candidate: ResourceCandidate;
  collectors: CollectorInfo[];
  busy: boolean;
  /** An error of the last action on this card (a refused edit, a failed request). */
  error: string | null;
  /** The server refused the plain approval because values are missing: open the edit form. */
  needsEdit?: boolean;
  onApprove: (edits: Edits | null) => void;
  onReject: (reason: string) => void;
};

/**
 * One reference-material candidate. Everything that came from an outside page (title, description,
 * note, tags, summary, address) is rendered as React text, never as HTML, and the address becomes a
 * link only when it is a plain https URL (target _blank, noopener noreferrer).
 */
export function ResourceCandidateCard({ candidate: c, collectors, busy, error, needsEdit = false, onApprove, onReject }: Props) {
  const [mode, setMode] = useState<"view" | "edit" | "reject">("view");
  const [edits, setEdits] = useState<Edits>(() => editsFromCandidate(c));
  const [reason, setReason] = useState("");
  const [reasonMissing, setReasonMissing] = useState(false);
  useEffect(() => {
    if (needsEdit) setMode("edit");
  }, [needsEdit]);
  const suggestion = c.ai_suggestion;
  const pending = c.status === "pending";

  return (
    <article className="card resource-card" data-status={c.status}>
      <div className="resource-head">
        <div style={{ minWidth: 0 }}>
          <strong className="resource-title">{c.title || "(제목을 읽지 못함)"}</strong>
          <p className="resource-url">
            {isSafeHttpsUrl(c.url) ? (
              <a href={c.url} target="_blank" rel="noopener noreferrer">
                {c.url}
              </a>
            ) : (
              <span>{c.url || "(링크 없음)"}</span>
            )}
          </p>
        </div>
        <div className="resource-pills">
          {c.source_domain && <span className="pill gray">{c.source_domain}</span>}
          <span className="pill blue">{collectorLabel(c.collector_type, collectors)}</span>
          {c.status === "approved" && <span className="pill green">승인</span>}
          {c.status === "rejected" && <span className="pill gray">{c.reviewed_by === "system" ? "자동 반려" : "반려"}</span>}
        </div>
      </div>

      {c.description && <p className="resource-desc">{c.description}</p>}
      {c.collector_note && <p className="small muted">수집 메모: {c.collector_note}</p>}

      {suggestion ? (
        <div className="resource-suggestion">
          <p className="small">
            <b>AI 제안</b> · {suggestion.field} / {suggestion.course} · {suggestion.level_label}
          </p>
          <div className="resource-tags">
            {suggestion.tags.map((t, i) => (
              <span key={`${t}-${i}`} className="pill blue">
                {t}
              </span>
            ))}
          </div>
          <p className="small muted">{suggestion.summary}</p>
          {!suggestion.is_learning_resource && <span className="pill gold">AI 가 학습 자료로 보지 않음</span>}
        </div>
      ) : (
        pending && <p className="small muted">AI 제안이 없어요. 분야·과정·태그를 직접 입력해 승인해 주세요.</p>
      )}

      <p className="small muted resource-checks">
        {c.status === "rejected" && c.reviewed_by === "system"
          ? rejectReasonLabel(c)
          : `검사 통과: ${checkStageSummary(c.check_results)
              .filter((s) => s.ok)
              .map((s) => s.label)
              .join(" · ")}`}
      </p>

      {c.status === "rejected" && c.reviewed_by === "admin" && <p className="small muted">{rejectReasonLabel(c)}</p>}
      {c.status !== "pending" && c.reviewed_at && <p className="small muted">처리 {dateTimeKSTLabel(c.reviewed_at)}</p>}

      {error && (
        <p className="error" role="alert">
          {error}
        </p>
      )}

      {pending && mode === "view" && (
        <div className="resource-actions">
          <button type="button" className="btn small" disabled={busy} onClick={() => onApprove(null)}>
            승인
          </button>
          <button type="button" className="btn light small" disabled={busy} onClick={() => setMode("edit")}>
            수정 후 승인
          </button>
          <button type="button" className="btn danger small" disabled={busy} onClick={() => setMode("reject")}>
            반려
          </button>
        </div>
      )}

      {pending && mode === "edit" && (
        <ResourceEditForm id={c.id} edits={edits} busy={busy} onChange={setEdits} onSubmit={() => onApprove(edits)} onCancel={() => setMode("view")} />
      )}

      {pending && mode === "reject" && (
        <ResourceRejectForm
          id={c.id}
          reason={reason}
          missing={reasonMissing}
          busy={busy}
          onChange={(value) => {
            setReason(value);
            setReasonMissing(false);
          }}
          onSubmit={() => (reason.trim() ? onReject(reason.trim()) : setReasonMissing(true))}
          onCancel={() => setMode("view")}
        />
      )}
    </article>
  );
}

const EDIT_FIELDS: { name: keyof Edits; label: string; wide?: boolean }[] = [
  { name: "title", label: "제목", wide: true },
  { name: "field", label: "분야" },
  { name: "course", label: "과정" },
  { name: "level_label", label: "수준 (서술형)" },
  { name: "tags", label: "태그 (쉼표로 구분, 3~8개)" },
  { name: "summary", label: "한 줄 요약", wide: true },
];

export function ResourceEditForm(props: {
  id: string;
  edits: Edits;
  busy: boolean;
  onChange: (edits: Edits) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  const { id, edits, busy, onChange, onSubmit, onCancel } = props;
  return (
    <div className="resource-form">
      <div className="field-grid">
        {EDIT_FIELDS.map(({ name, label, wide }) => (
          <div className="field" key={name} style={wide ? { gridColumn: "1 / -1" } : undefined}>
            <label htmlFor={`edit-${id}-${name}`}>{label}</label>
            <input
              id={`edit-${id}-${name}`}
              value={edits[name]}
              onChange={(e) => onChange({ ...edits, [name]: e.target.value })}
              autoComplete="off"
            />
          </div>
        ))}
      </div>
      <div className="resource-actions">
        <button type="button" className="btn small" disabled={busy} onClick={onSubmit}>
          수정한 내용으로 승인
        </button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  );
}

export function ResourceRejectForm(props: {
  id: string;
  reason: string;
  missing: boolean;
  busy: boolean;
  onChange: (reason: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
}) {
  const { id, reason, missing, busy, onChange, onSubmit, onCancel } = props;
  return (
    <div className="resource-form">
      <div className="field">
        <label htmlFor={`reason-${id}`}>반려 사유 (필수, 200자 이하)</label>
        <input id={`reason-${id}`} value={reason} maxLength={200} autoComplete="off" onChange={(e) => onChange(e.target.value)} />
        {missing && (
          <p className="error" role="alert">
            반려 사유를 입력해 주세요.
          </p>
        )}
      </div>
      <div className="resource-actions">
        <button type="button" className="btn danger small" disabled={busy} onClick={onSubmit}>
          반려 확정
        </button>
        <button type="button" className="btn secondary small" disabled={busy} onClick={onCancel}>
          취소
        </button>
      </div>
    </div>
  );
}
