// CR-013: delete a learning, the plain save status, the pressable learning rows of the dashboard.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { DeleteGoalDialog } from "../components/DeleteGoalDialog";
import {
  DELETE_FAILED,
  DELETE_TITLE,
  DELETE_TUTOR_NOTE,
  deleteBody,
  deleteConfirmButton,
  deleteCounts,
  runGoalDelete,
} from "./goalDelete";
import { goalRowLabel, openGoalExecution } from "./goalRow";
import { saveStatusView } from "./saveStatus";
import { learningListView } from "./weekPlan";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");
const noop = () => {};

// ---------------------------------------------------------------- 1. the confirmation wording
test("the confirmation fills the task and record counts from the data the screen has", () => {
  const counts = deleteCounts([{ record_count: 2 }, { record_count: 0 }, { record_count: 4 }]);
  assert.deepEqual(counts, { tasks: 3, records: 6 });
  const [name, rest] = deleteBody("Python 개발 기초", counts);
  assert.equal(
    name + rest,
    "Python 개발 기초 학습과 그 과제 3개, 실행 기록 6건, 회고, 학습 인사이트가 모두 지워지고 되돌릴 수 없어요. 켜 둔 타이머도 멈춰요.",
  );
  assert.equal(deleteBody("X", deleteCounts([]))[1].includes("그 과제 0개, 실행 기록 0건"), true, "an empty plan is a known 0");
});

test("a number the screen does not know is left out of the sentence, not guessed", () => {
  assert.deepEqual(deleteCounts(null), { tasks: null, records: null });
  assert.equal(
    deleteBody("영어", deleteCounts(null)).join(""),
    "영어 학습과 그 과제, 실행 기록, 회고, 학습 인사이트가 모두 지워지고 되돌릴 수 없어요. 켜 둔 타이머도 멈춰요.",
  );
  const noRecordField = deleteCounts([{ record_count: 1 }, {}]);
  assert.deepEqual(noRecordField, { tasks: 2, records: null });
  assert.ok(deleteBody("영어", noRecordField)[1].includes("그 과제 2개, 실행 기록,"));
});

test("the dialog: title, bold course, tutor note, cancel first and focused, delete second", () => {
  const html = renderToStaticMarkup(
    createElement(DeleteGoalDialog, { course: "Python 개발 기초", counts: { tasks: 12, records: 6 }, busy: false, error: null, onCancel: noop, onConfirm: noop }),
  );
  assert.ok(html.includes(`<h2 id="delete-goal-title">${DELETE_TITLE}</h2>`) && DELETE_TITLE === "이 학습을 삭제할까요?");
  assert.ok(html.includes("<b>Python 개발 기초</b> 학습과 그 과제 12개, 실행 기록 6건, 회고, 학습 인사이트가 모두 지워지고 되돌릴 수 없어요. 켜 둔 타이머도 멈춰요."));
  assert.ok(html.includes(`<p>${DELETE_TUTOR_NOTE}</p>`) && DELETE_TUTOR_NOTE === "AI 튜터 대화는 학습과 따로 저장되어 지워지지 않아요.");
  assert.match(html, /role="dialog"[^>]*aria-modal="true"[^>]*aria-labelledby="delete-goal-title"/);
  assert.ok(html.indexOf(">취소<") < html.indexOf(">삭제<"), "cancel comes before delete");
  assert.match(html, /<button[^>]*class="btn secondary"[^>]*id="delete-goal-cancel"/);
  assert.match(html, /<button[^>]*class="btn danger"[^>]*id="delete-goal-confirm"/);
  const src = read("../components/DeleteGoalDialog.tsx");
  assert.ok(/id="delete-goal-cancel"[^>]*autoFocus/.test(src.replace(/\s+/g, " ")), "focus starts on cancel");
  assert.ok(src.includes('e.key === "Escape" && !busy') && src.includes("e.target === e.currentTarget && !busy"), "Esc and a click outside cancel (not while deleting)");
});

// ---------------------------------------------------------------- 2. the delete flow
test("a successful delete reloads the list and the current learning afterwards", async () => {
  const calls: string[] = [];
  const outcome = await runGoalDelete(
    async () => void calls.push("delete"),
    async () => void calls.push("reload"),
    () => "x",
  );
  assert.deepEqual(outcome, { ok: true });
  assert.deepEqual(calls, ["delete", "reload"]);
});

test("a failed delete shows the error, reloads nothing and counts as nothing deleted", async () => {
  const calls: string[] = [];
  const outcome = await runGoalDelete(
    async () => {
      calls.push("delete");
      throw new Error("boom");
    },
    async () => void calls.push("reload"),
    () => DELETE_FAILED,
  );
  assert.deepEqual(outcome, { ok: false, error: DELETE_FAILED });
  assert.deepEqual(calls, ["delete"]);
  assert.ok(DELETE_FAILED.includes("아무것도 지워지지 않았어요"));
});

test("a failed reload does not turn a successful delete into an error", async () => {
  const outcome = await runGoalDelete(
    async () => {},
    async () => {
      throw new Error("reload");
    },
    () => "x",
  );
  assert.deepEqual(outcome, { ok: true });
});

test("while deleting the button is disabled and says so; after a failure it offers 다시 시도", () => {
  assert.deepEqual(deleteConfirmButton(false, false), { label: "삭제", disabled: false });
  assert.deepEqual(deleteConfirmButton(true, false), { label: "삭제하는 중…", disabled: true });
  assert.deepEqual(deleteConfirmButton(false, true), { label: "다시 시도", disabled: false });
  const busy = renderToStaticMarkup(
    createElement(DeleteGoalDialog, { course: "A", counts: { tasks: 1, records: 0 }, busy: true, error: null, onCancel: noop, onConfirm: noop }),
  );
  assert.match(busy, /id="delete-goal-confirm"[^>]*disabled=""[^>]*>삭제하는 중…/);
  assert.match(busy, /id="delete-goal-cancel"[^>]*disabled=""/);
  const failed = renderToStaticMarkup(
    createElement(DeleteGoalDialog, { course: "A", counts: { tasks: 1, records: 0 }, busy: false, error: "서버 오류", onCancel: noop, onConfirm: noop }),
  );
  assert.ok(failed.includes('<p class="error" role="alert">서버 오류</p>') && failed.includes(">다시 시도<"));
});

test("no learning left: the screen is the 'no learning' screen; one left: the plan of that learning", () => {
  assert.equal(learningListView(true, false, 0), "none");
  assert.equal(learningListView(true, false, 1), "some");
  assert.equal(learningListView(false, false, 1), "loading");
  const screen = read("../components/WeeklyPlanScreen.tsx");
  assert.ok(screen.includes("진행 중인 학습이 없어요") && screen.includes("학습 경로 설정으로 이동"));
  // after a delete: reload() of the learning list, which also re-reads users.active_goal_id (set by the server)
  assert.match(screen, /\(\) => goalSwitch\.reload\(\)/);
  assert.match(screen, /method: "DELETE"/);
  assert.match(screen, /\/api\/goals\/\$\{encodeURIComponent\(goalId\)\}/);
  assert.match(screen, /status === "ready" && goal && headerActions/);
  assert.ok((screen.match(/\{deleteDialog\}/g) ?? []).length === 2, "the dialog is in the plan view and in the no-task view");
});

// ---------------------------------------------------------------- 3. the save status
test("usually the save status is a text; 저장 중… while saving; a retry button only after a failure", () => {
  assert.deepEqual(saveStatusView({ status: "idle", failedKeys: [] }), { kind: "saved", text: "✓ 변경 내용 자동 저장됨", showRetry: false });
  assert.deepEqual(saveStatusView({ status: "saved", failedKeys: [] }), { kind: "saved", text: "✓ 변경 내용 자동 저장됨", showRetry: false });
  assert.deepEqual(saveStatusView({ status: "saving", failedKeys: [] }), { kind: "saving", text: "저장 중…", showRetry: false });
  const failed = saveStatusView({ status: "error", failedKeys: ["t1"] });
  assert.equal(failed.kind, "error");
  assert.equal(failed.showRetry, true);
  const screen = read("../components/WeeklyPlanScreen.tsx");
  assert.ok(!screen.includes("계획 저장됨 ✓"), "no button-like 'plan saved' any more");
  assert.match(screen, /<span className=\{`save-status\$\{saveView\.kind === "error" \? " error" : ""\}`\} aria-live="polite">/);
  assert.match(screen, /\{saveView\.showRetry && \(\s*<button type="button" className="btn secondary small" onClick=\{\(\) => saverRef\.current!\.retry\(\)\}>\s*다시 시도/);
  assert.match(screen, /className="btn danger small"[\s\S]*이 학습 삭제/);
  assert.ok(screen.indexOf("save-status") < screen.indexOf("이 학습 삭제"), "the status text sits next to (before) the delete button");
  const saver = read("./latestWins.ts");
  assert.ok(saver.includes("class LatestWinsSaver") && saver.includes("retry()"), "the saver is still there");
});

// ---------------------------------------------------------------- 4. the dashboard rows
test("the row label names the learning", () => {
  assert.equal(goalRowLabel("Python 개발 기초"), "Python 개발 기초 학습 실행 기록으로 이동");
});

function fakeOpen(active: string | null | "throws", switchFails = false) {
  const calls: string[] = [];
  const args = {
    goalId: "g2",
    getActiveGoalId: async () => {
      if (active === "throws") throw new Error("profile");
      return active;
    },
    switchGoal: async (id: string) => {
      calls.push(`switch ${id}`);
      if (switchFails) throw new Error("patch");
    },
    errorText: () => "전환 실패",
  };
  return { args, calls };
}

test("a row of another learning switches to it first, then goes on", async () => {
  const { args, calls } = fakeOpen("g1");
  assert.deepEqual(await openGoalExecution(args), { ok: true });
  assert.deepEqual(calls, ["switch g2"]);
});

test("a row of the current learning goes on at once, without a switch", async () => {
  const { args, calls } = fakeOpen("g2");
  assert.deepEqual(await openGoalExecution(args), { ok: true });
  assert.deepEqual(calls, []);
});

test("a failed switch does not go on and says why", async () => {
  const { args } = fakeOpen("g1", true);
  assert.deepEqual(await openGoalExecution(args), { ok: false, error: "전환 실패" });
});

test("when the current learning cannot be read, the switch is tried anyway", async () => {
  const { args, calls } = fakeOpen("throws");
  assert.deepEqual(await openGoalExecution(args), { ok: true });
  assert.deepEqual(calls, ["switch g2"]);
});

test("the row is one button for keyboard and screen readers, with the label, Enter and Space", () => {
  const dash = read("../components/Dashboard.tsx").replace(/\s+/g, " ");
  assert.match(dash, /className="goal-row clickable" role="button" tabIndex=\{0\} aria-label=\{goalRowLabel\(g\.course\)\}/);
  assert.ok(dash.includes('e.key === "Enter" || e.key === " "'));
  assert.ok(dash.includes('role="progressbar" aria-valuenow={g.progress_percentage}'), "the bar and the number stay");
  assert.ok(dash.includes("종합 분석 →"), "the analysis link stays");
  assert.ok(dash.includes("onOpenExecution"));
  assert.match(read("../app/page.tsx"), /onOpenExecution=\{\(\) => go\("execution"\)\}/);
});

// ---------------------------------------------------------------- 5. the style
test("the row highlight: colour, border, 2px up, light shadow; reduced motion keeps only colour and border", () => {
  const css = read("../app/globals.css");
  assert.match(css, /\.goal-row\.clickable \{[^}]*cursor: pointer;[^}]*border: 1px solid transparent;/);
  assert.match(css, /\.goal-row\.clickable:hover \{ background: #f3f5ff; border-color: #c9d1ff; transform: translateY\(-2px\); box-shadow: 0 6px 14px #4c62dc1f; \}/);
  assert.match(css, /\.goal-row\.clickable:focus-visible, \.goal-row\.clickable:active \{[^}]*translateY\(-2px\)/);
  const line = css.split(String.fromCharCode(10)).map((l) => l.replace(String.fromCharCode(13), "")).find((l) => l.startsWith("@media (prefers-reduced-motion: reduce) { .goal-row.clickable"));
  assert.ok(line, "a reduced-motion rule for the rows exists");
  assert.ok(line.includes(".goal-row.clickable { transition: none; }") && line.includes("{ transform: none; }"));
  assert.ok(!line.includes("background") && !line.includes("border"), "colour and border stay in reduced-motion mode");
  assert.ok(css.includes("@media (hover: hover) { .goal-row.clickable:hover"), "touch screens: the effect only while pressed");
});
