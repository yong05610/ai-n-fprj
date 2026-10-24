import assert from "node:assert/strict";
import { test } from "node:test";

import {
  budgetBar,
  continuedLabel,
  dashboardScheduleText,
  overBudgetMessage,
  planSummaryText,
  spanNote,
  taskCountHint,
  taskCountOk,
  weekGroupHeading,
  weeklyPlanHeaderText,
} from "./planText";

test("summary names total, available, weeks and weekly hours", () => {
  assert.equal(planSummaryText(300, 3600, 12, 5), "총 예상 시간 5시간 / 가용 시간 60시간 (12주 × 주 5시간)");
  assert.equal(planSummaryText(95, 420, 1, 7), "총 예상 시간 1시간 35분 / 가용 시간 7시간 (1주 × 주 7시간)");
});

test("the bar is capped at 100 and flags an overrun", () => {
  assert.deepEqual(budgetBar(1800, 3600), { percent: 50, over: false });
  assert.deepEqual(budgetBar(3600, 3600), { percent: 100, over: false });
  assert.deepEqual(budgetBar(4000, 3600), { percent: 100, over: true });
  assert.deepEqual(budgetBar(0, 3600), { percent: 0, over: false });
  assert.deepEqual(budgetBar(10, 0), { percent: 100, over: true });
});

test("the over-budget message names both totals and uses neutral wording", () => {
  const text = overBudgetMessage(3000, 2940);
  assert.ok(text.includes("50시간") && text.includes("49시간") && text.includes("확정할 수 없어요"));
  assert.ok(!/연체|지연|실패/.test(text));
});

test("week heading", () => {
  assert.equal(weekGroupHeading("2026-10-19", 0, 300), "10/19–10/25 · 1주차 · 예정 5시간");
  assert.equal(weekGroupHeading("2026-10-26", 1, 45), "10/26–11/01 · 2주차 · 예정 45분");
});

test("continuation wording", () => {
  assert.equal(spanNote(1), null);
  assert.equal(spanNote(3), "이어서 3주에 걸쳐 진행");
  assert.equal(continuedLabel(60, 150), "이어서 (이번 주 60분 / 총 150분)");
});

test("task count rule 3..60", () => {
  assert.deepEqual([2, 3, 60, 61].map(taskCountOk), [false, true, true, false]);
  assert.equal(taskCountHint(2), "과제는 3~60개예요. 지금 2개입니다.");
});

test("dashboard and weekly plan header texts", () => {
  assert.equal(dashboardScheduleText(300, 90), "이번 주 예정 5시간 · 오늘 예정 1시간 30분");
  assert.equal(dashboardScheduleText(0, 0), "이번 주 예정 0분 · 오늘 예정 0분");
  assert.equal(weeklyPlanHeaderText(600, 1200, 300), "총 소요 시간 10시간 · 가용 20시간 · 이번 주 예정 5시간");
});
