import assert from "node:assert/strict";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ResourceCandidateCard, ResourceEditForm, ResourceRejectForm } from "../components/ResourceCandidateCard";
import type { CollectorInfo, ResourceCandidate } from "./adminResources";

const collectors: CollectorInfo[] = [
  { type: "direct_link", label: "링크 직접 입력", enabled: true, daily_limit: 20, used_today: 0, daily_run_limit: null, runs_today: null },
  { type: "ai_topic", label: "AI 주제 제안", enabled: true, daily_limit: 20, used_today: 0, daily_run_limit: 5, runs_today: 0 },
];

const noop = () => {};

function candidate(over: Partial<ResourceCandidate> = {}): ResourceCandidate {
  return {
    id: "c1",
    url: "https://docs.python.org/3/library/os.html",
    source_domain: "docs.python.org",
    collector_type: "direct_link",
    collector_note: "",
    title: "os 모듈",
    description: "운영체제 인터페이스",
    ai_suggestion: { field: "Python 개발", course: "표준 라이브러리", level_label: "입문", tags: ["python", "os", "파이썬"], summary: "os 모듈 설명", is_learning_resource: true },
    ai_status: "ok",
    check_results: { format: "pass", domain: "pass", duplicate: "pass", address: "pass", fetch: "pass", response: "pass" },
    status: "pending",
    reviewed_by: null,
    reviewed_at: null,
    reject_reason: null,
    approved_document_id: null,
    admin_field: "",
    admin_course: "",
    created_at: "2026-10-26T00:00:00Z",
    ...over,
  };
}

function render(c: ResourceCandidate, props: { busy?: boolean; error?: string | null } = {}): string {
  return renderToStaticMarkup(
    createElement(ResourceCandidateCard, { candidate: c, collectors, busy: props.busy ?? false, error: props.error ?? null, onApprove: noop, onReject: noop }),
  );
}

const ATTACK = `<img src=x onerror=alert(1)>`;

test("text from an outside page is shown as text and never as markup", () => {
  const html = render(
    candidate({
      title: ATTACK,
      description: `<script>alert(1)</script> ${ATTACK}`,
      collector_note: ATTACK,
      ai_suggestion: { field: ATTACK, course: ATTACK, level_label: ATTACK, tags: [ATTACK, "b", "c"], summary: ATTACK, is_learning_resource: true },
    }),
  );
  assert.ok(!html.includes("<img"), "no raw <img> element");
  assert.ok(!html.includes("<script"), "no raw <script> element");
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"), "shown as escaped text");
  assert.ok(html.includes("&lt;script&gt;alert(1)&lt;/script&gt;"));
});

test("a safe https link opens in a new tab without opener or referrer", () => {
  const html = render(candidate());
  assert.match(html, /<a href="https:\/\/docs\.python\.org\/3\/library\/os\.html" target="_blank" rel="noopener noreferrer">/);
});

test("an address that is not plain https is shown as text, not as a link", () => {
  for (const url of ["javascript:alert(1)", "http://docs.python.org/x", "https://user:pw@docs.python.org/"]) {
    const html = render(candidate({ url, status: "rejected", reviewed_by: "system", reject_reason: "auto:bad_url" }));
    assert.ok(!html.includes("<a "), url);
    assert.ok(!html.includes(`href="${url}"`), url);
  }
});

test("a pending candidate offers approve, edit-and-approve and reject", () => {
  const html = render(candidate());
  assert.ok(html.includes("승인") && html.includes("수정 후 승인") && html.includes("반려"));
  assert.ok(html.includes("AI 제안") && html.includes("Python 개발 / 표준 라이브러리") && html.includes("python"));
  assert.ok(html.includes("검사 통과: 형식 · 허용 도메인 · 중복 · 주소 · 연결 · 응답"));
  assert.ok(html.includes("링크 직접 입력") && html.includes("docs.python.org"));
});

test("buttons are disabled while another action is running", () => {
  const html = render(candidate(), { busy: true });
  assert.equal((html.match(/disabled=""/g) ?? []).length, 3);
});

test("a processed candidate has no action buttons", () => {
  const approved = render(candidate({ status: "approved", reviewed_by: "admin", reviewed_at: "2026-10-26T03:00:00Z", approved_document_id: "doc_a_12345678" }));
  assert.ok(approved.includes("승인") && !approved.includes("수정 후 승인") && !approved.includes("<button"));
  const rejected = render(candidate({ status: "rejected", reviewed_by: "admin", reviewed_at: "2026-10-26T03:00:00Z", reject_reason: "광고성 문서" }));
  assert.ok(rejected.includes("반려 · 광고성 문서") && !rejected.includes("<button"));
});

test("an automatic rejection says so and why", () => {
  const html = render(
    candidate({ status: "rejected", reviewed_by: "system", reviewed_at: "2026-10-26T00:00:00Z", reject_reason: "auto:not_allowed_domain", ai_suggestion: null, ai_status: "none", check_results: { format: "pass", domain: "not_allowed_domain" } }),
  );
  assert.ok(html.includes("자동 반려") && html.includes("자동 반려 · 허용된 도메인이 아님"));
  assert.ok(!html.includes("<button"));
});

test("without an AI suggestion the admin is told to fill the values in", () => {
  const html = render(candidate({ ai_suggestion: null, ai_status: "failed" }));
  assert.ok(html.includes("AI 제안이 없어요"));
});

test("an AI that does not see a learning resource is flagged, the candidate is still pending", () => {
  const html = render(candidate({ ai_suggestion: { field: "f", course: "c", level_label: "입문", tags: ["a", "b", "c"], summary: "s", is_learning_resource: false } }));
  assert.ok(html.includes("AI 가 학습 자료로 보지 않음") && html.includes("수정 후 승인"));
});

test("an action error is announced next to the candidate", () => {
  const html = render(candidate(), { error: "field 은(는) 비어 있으면 안 됩니다." });
  assert.match(html, /role="alert"[^>]*>field 은\(는\) 비어 있으면 안 됩니다\./);
});

test("the edit form shows every value as an input value (escaped), and the reject form needs a reason", () => {
  const edits = { title: ATTACK, field: "f", course: "c", level_label: "l", tags: "a, b, c", summary: ATTACK };
  const form = renderToStaticMarkup(createElement(ResourceEditForm, { id: "c1", edits, busy: false, onChange: noop, onSubmit: noop, onCancel: noop }));
  assert.ok(!form.includes("<img"));
  assert.ok(form.includes("&lt;img src=x onerror=alert(1)&gt;"));
  for (const label of ["제목", "분야", "과정", "수준 (서술형)", "태그 (쉼표로 구분, 3~8개)", "한 줄 요약", "수정한 내용으로 승인", "취소"]) assert.ok(form.includes(label), label);

  const missing = renderToStaticMarkup(createElement(ResourceRejectForm, { id: "c1", reason: "", missing: true, busy: false, onChange: noop, onSubmit: noop, onCancel: noop }));
  assert.ok(missing.includes("반려 사유를 입력해 주세요.") && missing.includes('maxLength="200"') && missing.includes("반려 확정"));
  const ok = renderToStaticMarkup(createElement(ResourceRejectForm, { id: "c1", reason: "중복 내용", missing: false, busy: false, onChange: noop, onSubmit: noop, onCancel: noop }));
  assert.ok(!ok.includes("반려 사유를 입력해 주세요.") && ok.includes('value="중복 내용"'));
});
