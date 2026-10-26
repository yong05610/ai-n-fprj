/** Types and display helpers of the admin reference-material screen (Phase 8B). Pure, no window access. */

export type CandidateStatus = "pending" | "approved" | "rejected";
export type AiStatus = "ok" | "failed" | "skipped" | "none";

export type ResourceSuggestion = {
  field: string;
  course: string;
  level_label: string;
  tags: string[];
  summary: string;
  is_learning_resource: boolean;
};

export type ResourceCandidate = {
  id: string;
  url: string;
  source_domain: string;
  collector_type: string;
  collector_note: string;
  title: string;
  description: string;
  ai_suggestion: ResourceSuggestion | null;
  ai_status: AiStatus;
  check_results: Record<string, string>;
  status: CandidateStatus;
  reviewed_by: "admin" | "system" | null;
  reviewed_at: string | null;
  reject_reason: string | null;
  approved_document_id: string | null;
  admin_field: string;
  admin_course: string;
  created_at: string;
};

export type CollectorInfo = {
  type: string;
  label: string;
  enabled: boolean;
  daily_limit: number;
  used_today: number;
  daily_run_limit: number | null;
  runs_today: number | null;
};

export type CollectResult = {
  candidates: ResourceCandidate[];
  pending_count: number;
  auto_rejected_count: number;
  duplicate_count: number;
};

export type CandidateList = { items: ResourceCandidate[]; total: number; page: number; page_size: number };

export type StatsEntry = {
  collector_type: string | null;
  label: string | null;
  total: number;
  pending: number;
  approved: number;
  rejected_by_admin: number;
  auto_rejected: number;
  auto_rejected_reasons: Record<string, number>;
  approval_rate: number | null;
  reviewed_approval_rate: number | null;
  median_seconds_to_approve: number | null;
};

export type FieldDemandItem = { field: string; user_count: number; linked_document_count: number };

export type Edits = {
  title: string;
  field: string;
  course: string;
  level_label: string;
  tags: string;
  summary: string;
};

/** Why a link was refused automatically (reject_reason "auto:<code>"). */
export const AUTO_REJECT_LABEL: Record<string, string> = {
  bad_url: "링크 형식이 올바르지 않음",
  not_allowed_domain: "허용된 도메인이 아님",
  private_address: "내부 주소로 연결됨",
  dns_failed: "주소를 찾지 못함",
  timeout: "시간 안에 열리지 않음",
  too_large: "응답이 너무 큼",
  fetch_failed: "연결하지 못함",
  bad_redirect: "허용되지 않은 곳으로 이동",
  bad_status: "페이지가 열리지 않음",
  bad_type: "HTML 문서가 아님",
  empty_body: "내용이 없음",
  duplicate: "이미 있는 링크",
};

export const CHECK_STAGE_LABEL: Record<string, string> = {
  format: "형식",
  domain: "허용 도메인",
  duplicate: "중복",
  address: "주소",
  fetch: "연결",
  response: "응답",
  redirect: "이동",
};

export function autoRejectLabel(code: string): string {
  return AUTO_REJECT_LABEL[code] ?? "검사를 통과하지 못함";
}

/** "자동 반려 · 허용된 도메인이 아님" for a system rejection, the admin's own words otherwise. */
export function rejectReasonLabel(candidate: Pick<ResourceCandidate, "reject_reason" | "reviewed_by">): string {
  const reason = candidate.reject_reason ?? "";
  if (candidate.reviewed_by === "system" || reason.startsWith("auto:")) {
    return `자동 반려 · ${autoRejectLabel(reason.replace(/^auto:/, ""))}`;
  }
  return reason ? `반려 · ${reason}` : "반려";
}

export function checkStageSummary(results: Record<string, string>): { stage: string; label: string; ok: boolean; code: string }[] {
  return Object.entries(results).map(([stage, code]) => ({
    stage,
    label: CHECK_STAGE_LABEL[stage] ?? stage,
    ok: code === "pass",
    code,
  }));
}

export function collectorLabel(type: string, collectors: CollectorInfo[]): string {
  return collectors.find((c) => c.type === type)?.label ?? type;
}

/** A link is shown as clickable only when it is a plain https address; anything else stays text. */
export function isSafeHttpsUrl(value: string): boolean {
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password;
  } catch {
    return false;
  }
}

export function editsFromCandidate(c: ResourceCandidate): Edits {
  const s = c.ai_suggestion;
  return {
    title: c.title,
    field: s?.field ?? c.admin_field,
    course: s?.course ?? c.admin_course,
    level_label: s?.level_label ?? "",
    tags: (s?.tags ?? []).join(", "),
    summary: s?.summary ?? "",
  };
}

export function splitTags(text: string): string[] {
  return text
    .split(/[,\n，]/)
    .map((t) => t.trim())
    .filter((t) => t.length > 0);
}

/** The body of an approve-with-edits request: every field the form shows, tags as a list. */
export function editsPayload(edits: Edits) {
  return {
    title: edits.title,
    field: edits.field,
    course: edits.course,
    level_label: edits.level_label,
    tags: splitTags(edits.tags),
    summary: edits.summary,
  };
}

export type ListView = "loading" | "error" | "empty" | "items";

/** An empty list is shown only after the list was really read; a failed read is an error, never "empty". */
export function listView(loaded: boolean, failed: boolean, count: number): ListView {
  if (failed) return "error";
  if (!loaded) return "loading";
  return count === 0 ? "empty" : "items";
}

export function collectSummary(result: CollectResult): string {
  const parts = [`검토 대기 ${result.pending_count}건`];
  if (result.auto_rejected_count > 0) parts.push(`자동 반려 ${result.auto_rejected_count}건`);
  if (result.duplicate_count > 0) parts.push(`이미 있는 링크 ${result.duplicate_count}건`);
  return parts.join(" · ");
}

export function percent(rate: number | null): string {
  return rate === null ? "–" : `${Math.round(rate * 100)}%`;
}

/** Seconds as the largest sensible unit: "45초", "12분", "3시간", "2일". */
export function durationLabel(seconds: number | null): string {
  if (seconds === null) return "–";
  if (seconds < 60) return `${Math.round(seconds)}초`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}분`;
  if (seconds < 86400) return `${Math.round(seconds / 3600)}시간`;
  return `${Math.round(seconds / 86400)}일`;
}

/** The field-demand area exists only when the server answers; 404 means the feature is off. */
export function demandAreaVisible(outcome: { kind: "ok"; items: FieldDemandItem[] } | { kind: "off" } | { kind: "error" }): boolean {
  return outcome.kind === "ok";
}

export function collectorUsageLabel(c: CollectorInfo): string {
  const base = `오늘 ${c.used_today} / ${c.daily_limit}건`;
  return c.daily_run_limit === null ? base : `${base} · 실행 ${c.runs_today ?? 0} / ${c.daily_run_limit}회`;
}

/** The collector a form needs is switched off: its button is disabled and says so. */
export function collectorOff(collectors: CollectorInfo[], type: string): boolean {
  const found = collectors.find((c) => c.type === type);
  return !found || !found.enabled;
}

export const AI_TOPIC_NOTICE = "AI 가 만든 주소는 존재하지 않을 수 있어 검사를 통과한 것만 남아요.";
