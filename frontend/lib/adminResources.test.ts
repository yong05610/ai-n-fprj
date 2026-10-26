import assert from "node:assert/strict";
import { test } from "node:test";

import {
  AUTO_REJECT_LABEL,
  type CollectorInfo,
  type ResourceCandidate,
  autoRejectLabel,
  checkStageSummary,
  collectSummary,
  collectorOff,
  collectorUsageLabel,
  demandAreaVisible,
  durationLabel,
  editsFromCandidate,
  editsPayload,
  isSafeHttpsUrl,
  listView,
  percent,
  rejectReasonLabel,
  splitTags,
} from "./adminResources";
import { isAdminView, mustLeaveAdminView, parseHash } from "./viewHash";

function candidate(over: Partial<ResourceCandidate> = {}): ResourceCandidate {
  return {
    id: "c1",
    url: "https://docs.python.org/3/library/os.html",
    source_domain: "docs.python.org",
    collector_type: "direct_link",
    collector_note: "",
    title: "os",
    description: "",
    ai_suggestion: null,
    ai_status: "none",
    check_results: {},
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

const collectors: CollectorInfo[] = [
  { type: "direct_link", label: "링크 직접 입력", enabled: true, daily_limit: 20, used_today: 3, daily_run_limit: null, runs_today: null },
  { type: "ai_topic", label: "AI 주제 제안", enabled: false, daily_limit: 20, used_today: 0, daily_run_limit: 5, runs_today: 1 },
];

test("an empty list is shown only after a successful read; a failed read is an error, never empty", () => {
  assert.equal(listView(false, false, 0), "loading");
  assert.equal(listView(false, true, 0), "error");
  assert.equal(listView(true, true, 0), "error");
  assert.equal(listView(true, true, 5), "error");
  assert.equal(listView(true, false, 0), "empty");
  assert.equal(listView(true, false, 2), "items");
});

test("every automatic rejection code has a plain-language label, unknown ones a safe default", () => {
  for (const code of ["bad_url", "not_allowed_domain", "private_address", "dns_failed", "timeout", "too_large", "fetch_failed", "bad_redirect", "bad_status", "bad_type", "empty_body", "duplicate"]) {
    assert.ok(AUTO_REJECT_LABEL[code], code);
  }
  assert.equal(autoRejectLabel("not_allowed_domain"), "허용된 도메인이 아님");
  assert.equal(autoRejectLabel("something_new"), "검사를 통과하지 못함");
});

test("a rejection reads as automatic or as the admin's own words", () => {
  assert.equal(rejectReasonLabel({ reviewed_by: "system", reject_reason: "auto:bad_status" }), "자동 반려 · 페이지가 열리지 않음");
  assert.equal(rejectReasonLabel({ reviewed_by: "admin", reject_reason: "광고성 문서" }), "반려 · 광고성 문서");
  assert.equal(rejectReasonLabel({ reviewed_by: "admin", reject_reason: null }), "반려");
});

test("only a plain https address becomes a link", () => {
  assert.equal(isSafeHttpsUrl("https://docs.python.org/3/"), true);
  for (const bad of ["javascript:alert(1)", "http://docs.python.org/", "data:text/html,<script>", "https://user:pw@docs.python.org/", "//docs.python.org", "docs.python.org", "", "ftp://x.example/"]) {
    assert.equal(isSafeHttpsUrl(bad), false, bad);
  }
});

test("the edit form starts from the AI suggestion, then the admin's hints, then empty", () => {
  const withSuggestion = candidate({
    title: "메타 제목",
    ai_suggestion: { field: "Rust", course: "소유권", level_label: "입문", tags: ["a", "b", "c"], summary: "요약", is_learning_resource: true },
  });
  assert.deepEqual(editsFromCandidate(withSuggestion), { title: "메타 제목", field: "Rust", course: "소유권", level_label: "입문", tags: "a, b, c", summary: "요약" });
  const hintsOnly = candidate({ admin_field: "Python 개발", admin_course: "os" });
  assert.deepEqual(editsFromCandidate(hintsOnly), { title: "os", field: "Python 개발", course: "os", level_label: "", tags: "", summary: "" });
});

test("tags are split on commas and new lines and empty ones are dropped", () => {
  assert.deepEqual(splitTags(" rust, 러스트 ,, 소유권\nborrow，x "), ["rust", "러스트", "소유권", "borrow", "x"]);
  assert.deepEqual(splitTags(" , "), []);
  assert.deepEqual(editsPayload({ title: "t", field: "f", course: "c", level_label: "l", tags: "a, b, c", summary: "s" }).tags, ["a", "b", "c"]);
});

test("the collect summary names only what happened", () => {
  assert.equal(collectSummary({ candidates: [], pending_count: 2, auto_rejected_count: 0, duplicate_count: 0 }), "검토 대기 2건");
  assert.equal(collectSummary({ candidates: [], pending_count: 1, auto_rejected_count: 2, duplicate_count: 1 }), "검토 대기 1건 · 자동 반려 2건 · 이미 있는 링크 1건");
});

test("collector rows: usage text and the off switch", () => {
  assert.equal(collectorUsageLabel(collectors[0]), "오늘 3 / 20건");
  assert.equal(collectorUsageLabel(collectors[1]), "오늘 0 / 20건 · 실행 1 / 5회");
  assert.equal(collectorOff(collectors, "direct_link"), false);
  assert.equal(collectorOff(collectors, "ai_topic"), true);
  assert.equal(collectorOff(collectors, "unknown"), true);
});

test("numbers: rates and durations", () => {
  assert.equal(percent(null), "–");
  assert.equal(percent(0.5), "50%");
  assert.equal(percent(0.4286), "43%");
  assert.equal(durationLabel(null), "–");
  assert.equal(durationLabel(45), "45초");
  assert.equal(durationLabel(600), "10분");
  assert.equal(durationLabel(7200), "2시간");
  assert.equal(durationLabel(172800), "2일");
});

test("the field-demand area is visible only when the server answered; off or failed hides it with its title", () => {
  assert.equal(demandAreaVisible({ kind: "ok", items: [] }), true);
  assert.equal(demandAreaVisible({ kind: "off" }), false);
  assert.equal(demandAreaVisible({ kind: "error" }), false);
});

test("check stages are listed with a pass flag", () => {
  assert.deepEqual(checkStageSummary({ format: "pass", domain: "not_allowed_domain" }), [
    { stage: "format", label: "형식", ok: true, code: "pass" },
    { stage: "domain", label: "허용 도메인", ok: false, code: "not_allowed_domain" },
  ]);
});

test("the admin library screen is an admin view: hidden from non-admins, also by address", () => {
  assert.deepEqual(parseHash("#admin-library"), { view: "admin-library", param: null });
  assert.equal(isAdminView("admin-library"), true);
  assert.equal(isAdminView("admin-users"), true);
  assert.equal(isAdminView("dashboard"), false);
  assert.equal(isAdminView(null), false);
  assert.equal(mustLeaveAdminView(false, "admin-library"), true); // a non-admin who typed the address is sent away
  assert.equal(mustLeaveAdminView(true, "admin-library"), false);
  assert.equal(mustLeaveAdminView(null, "admin-library"), false); // not known yet: nothing is shown either (the page renders it only for isAdmin === true)
  assert.equal(mustLeaveAdminView(false, "dashboard"), false);
});
