// CR-014: weekly target, all-period card, task description, this-week filter of the execution screen.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { ALL_PERIOD_HINT, NO_TARGET_HINT, NO_WEEK_TASKS, goalStat, taskDescription, visibleTasks, weeklyTargetMinutes } from "./executionView";

const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("weekly target = weekly_hours x 60 (7 hours -> 420), unknown -> null", () => {
  assert.equal(weeklyTargetMinutes(7), 420);
  assert.equal(weeklyTargetMinutes(0.5), 30);
  for (const bad of [undefined, null, 0, -1, NaN, "7"]) assert.equal(weeklyTargetMinutes(bad), null);
});

test("week view: percent of the weekly target, capped at 100, same target in all texts", () => {
  assert.deepEqual(goalStat("week", 185, 420), { percentText: "44", detailText: "185분 / 420분", targetLine: "주 목표 420분" });
  assert.equal(goalStat("week", 0, 420).percentText, "0");
  assert.equal(goalStat("week", 900, 420).percentText, "100");
});

test("all-period view: no percent, a short hint instead", () => {
  const s = goalStat("all", 9999, 420);
  assert.equal(s.percentText, "–");
  assert.equal(s.detailText, ALL_PERIOD_HINT);
  assert.equal(s.targetLine, "전체 기간");
});

test("unknown weekly_hours: no NaN / Infinity anywhere", () => {
  const s = goalStat("week", 50, weeklyTargetMinutes(undefined));
  assert.equal(s.percentText, "–");
  assert.equal(s.detailText, NO_TARGET_HINT);
  assert.ok(!/NaN|Infinity/.test(JSON.stringify(s)));
});

test("description: shown when there is text, no line for empty or blank", () => {
  assert.equal(taskDescription("변수와 자료형"), "변수와 자료형");
  for (const none of ["", "   ", undefined, null]) assert.equal(taskDescription(none), null);
});

const tasks = [
  { id: "a", in_current_week: true },
  { id: "b", in_current_week: false },
  { id: "c", in_current_week: false },
  { id: "d" }, // an older server: no field
];

test("week view: tasks placed this week plus tasks with a record this week", () => {
  const ids = (xs: { id: string }[]) => xs.map((t) => t.id);
  assert.deepEqual(ids(visibleTasks(tasks.slice(0, 3), "week", {})), ["a"]);
  assert.deepEqual(ids(visibleTasks(tasks.slice(0, 3), "week", { c: [{}] })), ["a", "c"]);
  assert.deepEqual(ids(visibleTasks(tasks.slice(0, 3), "week", { b: [] })), ["a"], "an empty record list is no record");
});

test("week view: nothing to show -> empty list (the screen prints the guide text)", () => {
  assert.deepEqual(visibleTasks([{ id: "b", in_current_week: false }], "week", {}), []);
  assert.equal(NO_WEEK_TASKS, "이번 주에 배치된 과제가 없어요. 전체 기간에서 확인하세요");
});

test("all-period view keeps everything; a missing field never hides a task", () => {
  assert.equal(visibleTasks(tasks, "all", {}).length, 4);
  assert.deepEqual(visibleTasks([{ id: "d" }], "week", {}).map((t) => t.id), ["d"]);
});

test("the screen wires the helpers and the description style is 12px, two lines", () => {
  const screen = read("../components/ExecutionScreen.tsx");
  assert.match(screen, /goalStat\(period, weeklyMinutes, weeklyTargetMinutes\(activeGoal\?\.weekly_hours\)\)/);
  assert.match(screen, /visibleTasks\(tasks \?\? \[\], period, logsByTask\)/);
  assert.match(screen, /className="small muted task-desc"/);
  assert.ok(!/reduce\(\(sum, t\) => sum \+ t\.estimated_minutes/.test(screen), "the old denominator is gone");
  const css = read("../app/globals.css");
  const rule = css.split("\n").find((l) => l.startsWith(".task-record-head .task-desc")) ?? "";
  assert.match(rule, /font-size: 12px/);
  assert.match(rule, /-webkit-line-clamp: 2/);
});
