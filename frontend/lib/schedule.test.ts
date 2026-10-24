import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import path from "node:path";
import { test } from "node:test";

import {
  availableMinutes,
  coveragePercent,
  defaultWeekday,
  duplicateTitleIndexes,
  firstWeekDays,
  groupByWeek,
  lastWeekDays,
  lastScheduledWeekIndex,
  normalizedTitle,
  periodDays,
  periodWeeks,
  placeTasks,
  planWeekMondays,
  tasksInWeek,
  weekCount,
  weekIndexOf,
  weekPortions,
} from "./schedule";

// The very same file backend/tests/test_schedule.py reads: both implementations must agree.
const VECTORS = JSON.parse(readFileSync(path.resolve(process.cwd(), "../backend/tests/fixtures/schedule_cases.json"), "utf-8")) as {
  schedule: {
    name: string;
    weekly_minutes: number;
    minutes: number[];
    placements: { timeline_start_minutes: number; start_week_index: number; suggested_weekday: string }[];
    portions: [number, number][][];
  }[];
  week_count: { start_date: string; target_date: string; week_count: number }[];
  available: { name: string; weekly_hours: number; start_date: string; target_date: string; days: number; weeks: number; available_minutes: number }[];
};

test("the shared vectors are there (9 schedules, 7 week counts)", () => {
  assert.equal(VECTORS.schedule.length, 9);
  assert.equal(VECTORS.week_count.length, 7);
});

for (const c of VECTORS.schedule) {
  test(`placements match the shared vector: ${c.name}`, () => {
    assert.deepEqual(placeTasks(c.minutes, c.weekly_minutes), c.placements);
  });
  test(`week portions match the shared vector: ${c.name}`, () => {
    let cursor = 0;
    c.minutes.forEach((minutes, i) => {
      const got = [...weekPortions(cursor, minutes, c.weekly_minutes).entries()].sort((a, b) => a[0] - b[0]);
      assert.deepEqual(got, c.portions[i]);
      assert.equal(got.reduce((sum, [, m]) => sum + m, 0), minutes);
      cursor += minutes;
    });
  });
}

for (const c of VECTORS.week_count) {
  test(`week count ${c.start_date}..${c.target_date}`, () => {
    assert.equal(weekCount(c.start_date, c.target_date), c.week_count);
  });
}

for (const c of VECTORS.available) {
  test(`available minutes match the shared vector: ${c.name}`, () => {
    assert.equal(periodDays(c.start_date, c.target_date), c.days);
    assert.equal(periodWeeks(c.start_date, c.target_date), c.weeks);
    assert.equal(availableMinutes(c.weekly_hours, c.start_date, c.target_date), c.available_minutes);
  });
}

test("the shared vectors include the available-time cases (11)", () => {
  assert.equal(VECTORS.available.length, 11);
});

test("PM case: a Sunday start and 61 days is 2614 minutes, not 10 whole weeks; a Monday-Sunday week is exact", () => {
  assert.equal(availableMinutes(5, "2026-10-25", "2026-12-24"), 2614);
  assert.equal(availableMinutes(5, "2026-10-19", "2026-10-25"), 300);
});

test("partial first and last weeks", () => {
  assert.deepEqual([firstWeekDays("2026-10-19"), firstWeekDays("2026-10-21"), firstWeekDays("2026-10-25")], [7, 5, 1]);
  assert.deepEqual([lastWeekDays("2026-10-25"), lastWeekDays("2026-10-22"), lastWeekDays("2026-10-19")], [7, 4, 1]);
});

test("coverage percent is whole and safe without time", () => {
  assert.equal(coveragePercent(3600, 23400), 15);
  assert.equal(coveragePercent(2, 3), 67);
  assert.equal(coveragePercent(10, 0), 0);
});

test("default weekday boundaries", () => {
  assert.equal(defaultWeekday(299, 300), "sun");
  assert.equal(defaultWeekday(300, 300), "mon");
  assert.equal(defaultWeekday(0, 420), "mon");
});

test("grouping the design example (weekly 300): week 1 holds 3 tasks, week 2 the rest", () => {
  const groups = groupByWeek([120, 90, 150, 240], 300, "2026-10-19");
  assert.equal(groups.length, 2);
  assert.deepEqual([groups[0].weekStart, groups[0].weekEnd, groups[0].scheduledMinutes], ["2026-10-19", "2026-10-25", 300]);
  assert.deepEqual([groups[1].weekStart, groups[1].weekEnd, groups[1].scheduledMinutes], ["2026-10-26", "2026-11-01", 300]);
  const third = groups[0].items[2];
  assert.deepEqual([third.taskIndex, third.weekMinutes, third.startsHere, third.totalMinutes, third.weeksSpanned], [2, 90, true, 150, 2]);
  const continued = groups[1].items[0];
  assert.deepEqual([continued.taskIndex, continued.weekMinutes, continued.startsHere], [2, 60, false]);
  assert.deepEqual(groups[1].items.map((i) => i.taskIndex), [2, 3]);
});

test("a long task shows in every week it touches and no week is over the weekly minutes", () => {
  const groups = groupByWeek([100, 800, 100], 300, "2026-10-19");
  assert.deepEqual(groups.map((g) => g.index), [0, 1, 2, 3]);
  assert.ok(groups.every((g) => g.scheduledMinutes <= 300));
  assert.deepEqual(groups.map((g) => g.items.filter((i) => i.taskIndex === 1).map((i) => i.weekMinutes)), [[200], [300], [300], []]);
});

test("a task whose minutes were cleared stays listed (so it can be edited) and takes no time", () => {
  const groups = groupByWeek([60, 0, Number.NaN, 60], 300, "2026-10-19");
  assert.equal(groups.length, 1);
  assert.deepEqual(groups[0].items.map((i) => [i.taskIndex, i.weekMinutes]), [[0, 60], [1, 0], [2, 0], [3, 60]]);
});

test("editing minutes re-places the later tasks at once", () => {
  const before = groupByWeek([120, 90, 150, 240], 300, "2026-10-19");
  const after = groupByWeek([200, 90, 150, 240], 300, "2026-10-19"); // task 1 grows by 80
  assert.deepEqual(before[1].items.map((i) => i.taskIndex), [2, 3]);
  // 200 + 90 = 290 -> task 2 (150) starts at 290: 10 in week 1, 140 in week 2; task 3 (240) starts at 440: 160 + 80
  assert.deepEqual(after[0].items.map((i) => [i.taskIndex, i.weekMinutes]), [[0, 200], [1, 90], [2, 10]]);
  assert.deepEqual(after[1].items.map((i) => [i.taskIndex, i.weekMinutes]), [[2, 140], [3, 160]]);
  assert.deepEqual(after[2].items.map((i) => [i.taskIndex, i.weekMinutes, i.startsHere]), [[3, 80, false]]);
  assert.equal(placeTasks([200, 90, 150, 240], 300)[3].timeline_start_minutes, 440);
});

test("deleting a task pulls the following tasks forward", () => {
  const minutes = [120, 90, 150, 240];
  const without = minutes.filter((_, i) => i !== 0);
  assert.deepEqual(placeTasks(without, 300).map((p) => p.timeline_start_minutes), [0, 90, 240]);
});

test("one empty plan has no groups", () => {
  assert.deepEqual(groupByWeek([], 300, "2026-10-19"), []);
});

test("duplicate titles ignore case and extra spaces; blanks are not duplicates", () => {
  assert.equal(normalizedTitle("  Python   Basics "), "python basics");
  assert.deepEqual(duplicateTitleIndexes(["A b", "c", "a  B", "", "", "C"]), [2, 5]);
  assert.deepEqual(duplicateTitleIndexes(["x", "y"]), []);
});


const stored = (id: string, order: number, minutes: number, start: number) => ({ id, order_index: order, estimated_minutes: minutes, timeline_start_minutes: start });

test("stored tasks of a week: the start week and the continued share (design example)", () => {
  const tasks = [stored("d", 3, 240, 360), stored("a", 0, 120, 0), stored("c", 2, 150, 210), stored("b", 1, 90, 120)];
  const w0 = tasksInWeek(tasks, 300, 0);
  const w1 = tasksInWeek(tasks, 300, 1);
  assert.deepEqual(w0.map((e) => [e.task.id, e.weekMinutes, e.startsHere, e.totalMinutes, e.weeksSpanned]), [["a", 120, true, 120, 1], ["b", 90, true, 90, 1], ["c", 90, true, 150, 2]]);
  assert.deepEqual(w1.map((e) => [e.task.id, e.weekMinutes, e.startsHere]), [["c", 60, false], ["d", 240, true]]);
  assert.deepEqual(tasksInWeek(tasks, 300, 2), []);
  assert.equal(w0.reduce((s, e) => s + e.weekMinutes, 0), 300);
});

test("the last scheduled week and the list of week mondays", () => {
  const tasks = [stored("a", 0, 120, 0), stored("b", 1, 480, 120)]; // 600 minutes, weekly 300 -> weeks 0..1
  assert.equal(lastScheduledWeekIndex(tasks, 300), 1);
  assert.equal(lastScheduledWeekIndex([], 300), -1);
  // the plan spans 4 weeks although the tasks end in week 2: every week of the plan is listed
  assert.deepEqual(planWeekMondays("2026-10-19", 4, 1), ["2026-10-19", "2026-10-26", "2026-11-02", "2026-11-09"]);
  // tasks reaching beyond the period (hand-made later tasks) extend the list
  assert.equal(planWeekMondays("2026-10-19", 2, 4).length, 5);
  assert.equal(planWeekMondays("2026-10-19", 0, -1).length, 1);
  assert.equal(weekIndexOf("2026-10-19", "2026-11-02"), 2);
});
