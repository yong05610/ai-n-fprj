import assert from "node:assert/strict";
import { test } from "node:test";

import {
  budgetBar,
  continuedLabel,
  coverageHint,
  coverageText,
  partialWeekNote,
  dashboardScheduleText,
  overBudgetMessage,
  planSummaryText,
  spanNote,
  taskCountHint,
  taskCountOk,
  weekGroupHeading,
  weeklyPlanHeaderText,
} from "./planText";

test("summary names total, available, real days with weeks, and weekly hours", () => {
  assert.equal(planSummaryText(300, 2614, 61, 8.7, 5), "총 예상 시간 5시간 / 가용 시간 43시간 34분 (총 61일(약 8.7주), 주 5시간)");
  assert.equal(planSummaryText(95, 420, 7, 1, 7), "총 예상 시간 1시간 35분 / 가용 시간 7시간 (총 7일(약 1.0주), 주 7시간)");
});

test("partial week note names the first and the last partial week, nothing for whole weeks", () => {
  assert.equal(partialWeekNote(7, 7), null);
  assert.equal(partialWeekNote(1, 7), "첫 주는 1일만 남아 있어요");
  assert.equal(partialWeekNote(7, 4), "마지막 주는 4일까지예요");
  assert.equal(partialWeekNote(5, 3), "첫 주는 5일만 남아 있어요 · 마지막 주는 3일까지예요");
});

test("coverage hint appears below 40 percent in a neutral tone and never above", () => {
  assert.equal(coverageHint(15), "이 계획은 가용 시간의 15% 예요. 더 깊게 배우려면 목표 수준이나 기간을 조정해 보세요.");
  assert.equal(coverageHint(39) !== null, true);
  assert.equal(coverageHint(40), null);
  assert.equal(coverageHint(92), null);
  assert.ok(!/경고|위험|부족|미달|실패/.test(coverageHint(5) ?? ""));
  assert.equal(coverageText(77), "가용 시간의 77% 사용");
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
