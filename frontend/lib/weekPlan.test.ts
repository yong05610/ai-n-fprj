import assert from "node:assert/strict";
import { test } from "node:test";

import { addDaysToDateString, daysBetweenDateStrings, mondayOfDateString, mondayOfThisWeekKST } from "./week";
import {
  WEEKDAY_OPTIONS,
  completionCounts,
  formatHoursMinutes,
  listWeekStarts,
  neighborWeek,
  pickInitialWeek,
  tasksOfWeek,
  toWeekday,
  totalMinutes,
  weekOffset,
  weekRangeLabel,
  weekRelationLabel,
} from "./weekPlan";

const THIS_WEEK = "2026-10-19"; // a Monday

test("pickInitialWeek: this week when it has tasks", () => {
  assert.equal(pickInitialWeek(["2026-10-12", "2026-10-19", "2026-10-26"], THIS_WEEK), "2026-10-19");
});

test("pickInitialWeek: no tasks this week -> nearest later week (future first)", () => {
  assert.equal(pickInitialWeek(["2026-10-05", "2026-10-26", "2026-11-09"], THIS_WEEK), "2026-10-26");
});

test("pickInitialWeek: only future weeks", () => {
  assert.equal(pickInitialWeek(["2026-11-02", "2026-11-09"], THIS_WEEK), "2026-11-02");
});

test("pickInitialWeek: only past weeks -> the last one; empty -> null", () => {
  assert.equal(pickInitialWeek(["2026-09-28", "2026-10-05"], THIS_WEEK), "2026-10-05");
  assert.equal(pickInitialWeek([], THIS_WEEK), null);
});

test("pickInitialWeek: boundary - the week before and after this week are not 'this week'", () => {
  assert.equal(pickInitialWeek(["2026-10-12"], THIS_WEEK), "2026-10-12");
  assert.equal(pickInitialWeek(["2026-10-26"], THIS_WEEK), "2026-10-26");
});

test("this week follows the Seoul calendar: Sunday night UTC is already Monday in Seoul", () => {
  // 2026-10-25T16:00:00Z = Monday 2026-10-26 01:00 KST -> a new week has started
  assert.equal(mondayOfThisWeekKST(new Date("2026-10-25T16:00:00Z")), "2026-10-26");
  // 2026-10-25T14:59:00Z = Sunday 2026-10-25 23:59 KST -> still the old week
  assert.equal(mondayOfThisWeekKST(new Date("2026-10-25T14:59:00Z")), "2026-10-19");
  assert.equal(pickInitialWeek(["2026-10-19", "2026-10-26"], mondayOfThisWeekKST(new Date("2026-10-25T16:00:00Z"))), "2026-10-26");
});

test("listWeekStarts: distinct and sorted", () => {
  const tasks = [{ plan_week_start: "2026-10-26" }, { plan_week_start: "2026-10-19" }, { plan_week_start: "2026-10-26" }];
  assert.deepEqual(listWeekStarts(tasks), ["2026-10-19", "2026-10-26"]);
});

test("neighborWeek stays inside the weeks that have tasks", () => {
  const weeks = ["2026-10-19", "2026-10-26", "2026-11-09"];
  assert.equal(neighborWeek(weeks, "2026-10-26", "prev"), "2026-10-19");
  assert.equal(neighborWeek(weeks, "2026-10-26", "next"), "2026-11-09"); // skips the empty week
  assert.equal(neighborWeek(weeks, "2026-10-19", "prev"), null);
  assert.equal(neighborWeek(weeks, "2026-11-09", "next"), null);
  assert.equal(neighborWeek(weeks, "2026-12-01", "next"), null);
});

test("week labels are neutral", () => {
  assert.equal(weekRelationLabel(weekOffset("2026-10-19", THIS_WEEK)), "이번 주");
  assert.equal(weekRelationLabel(weekOffset("2026-10-12", THIS_WEEK)), "지난 주");
  assert.equal(weekRelationLabel(weekOffset("2026-10-26", THIS_WEEK)), "다음 주");
  assert.equal(weekRelationLabel(weekOffset("2026-11-09", THIS_WEEK)), "3주 뒤");
  assert.equal(weekRelationLabel(weekOffset("2026-09-28", THIS_WEEK)), "3주 전");
  for (const offset of [-5, -1, 0, 1, 5]) assert.doesNotMatch(weekRelationLabel(offset), /연체|지연|늦|실패/);
  assert.equal(weekRangeLabel("2026-10-19"), "10/19–10/25");
  assert.equal(weekRangeLabel("2026-12-28"), "12/28–01/03"); // crosses the year end
});

test("date string arithmetic does not depend on the time zone", () => {
  assert.equal(mondayOfDateString("2026-10-25"), "2026-10-19"); // Sunday
  assert.equal(mondayOfDateString("2026-10-19"), "2026-10-19"); // Monday
  assert.equal(mondayOfDateString("2027-01-01"), "2026-12-28");
  assert.equal(addDaysToDateString("2026-10-25", 1), "2026-10-26");
  assert.equal(daysBetweenDateStrings("2026-10-19", "2026-11-09"), 21);
});

test("tasksOfWeek orders by order_index and filters the week", () => {
  const t = (id: string, week: string, order: number) => ({
    id, title: id, description: "", estimated_minutes: 30, suggested_weekday: "none", status: "pending", plan_week_start: week, order_index: order, timeline_start_minutes: 0,
  });
  const tasks = [t("b", "2026-10-19", 1), t("x", "2026-10-26", 0), t("a", "2026-10-19", 0)];
  assert.deepEqual(tasksOfWeek(tasks, "2026-10-19").map((x) => x.id), ["a", "b"]);
  assert.deepEqual(tasksOfWeek(tasks, null), []);
});

test("totals and progress (completed / all, no weighting)", () => {
  assert.equal(formatHoursMinutes(320), "5시간 20분");
  assert.equal(formatHoursMinutes(420), "7시간");
  assert.equal(formatHoursMinutes(45), "45분");
  assert.equal(totalMinutes([{ estimated_minutes: 60 }, { estimated_minutes: 50 }]), 110);
  assert.deepEqual(completionCounts([{ status: "completed" }, { status: "pending" }, { status: "pending" }]), { done: 1, total: 3, percent: 33 });
  assert.deepEqual(completionCounts([]), { done: 0, total: 0, percent: 0 });
});

test("weekday values: the options match the API values and strange input becomes none", () => {
  assert.deepEqual(WEEKDAY_OPTIONS.map((o) => o.value), ["none", "mon", "tue", "wed", "thu", "fri", "sat", "sun"]);
  assert.equal(toWeekday("wed"), "wed");
  assert.equal(toWeekday("monday"), "none");
  assert.equal(toWeekday(""), "none");
});
