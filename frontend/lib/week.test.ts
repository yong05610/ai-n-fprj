import assert from "node:assert/strict";
import { test } from "node:test";

import { isMondayDateString, mondayOfThisWeekKST, todayKSTDateString } from "./week";

test("P4-2 repro: Wednesday 03:00 KST (= Tuesday 18:00 UTC) must resolve to that week's Monday, not Sunday", () => {
  // 2026-10-21 is a Wednesday. 03:00 KST on that day is 2026-10-20T18:00:00Z.
  const wednesdayEarlyKST = new Date("2026-10-20T18:00:00Z");
  assert.equal(mondayOfThisWeekKST(wednesdayEarlyKST), "2026-10-19");
});

test("resolves correctly across the full 00:00-09:00 KST window (the previous UTC-day bug range)", () => {
  for (let hour = 0; hour < 9; hour++) {
    const instant = new Date(`2026-10-20T${String(hour).padStart(2, "0")}:00:00Z`); // = 2026-10-21 (hour+9) KST, still Wednesday
    assert.equal(mondayOfThisWeekKST(instant), "2026-10-19", `hour=${hour} UTC`);
  }
});

test("a Monday in KST resolves to itself", () => {
  // 2026-10-19 00:00 KST = 2026-10-18T15:00:00Z
  assert.equal(mondayOfThisWeekKST(new Date("2026-10-18T15:00:00Z")), "2026-10-19");
});

test("a Sunday in KST resolves to the Monday that started that week", () => {
  // 2026-10-25 is a Sunday. Noon KST = 2026-10-25T03:00:00Z.
  assert.equal(mondayOfThisWeekKST(new Date("2026-10-25T03:00:00Z")), "2026-10-19");
});

test("isMondayDateString", () => {
  assert.equal(isMondayDateString("2026-10-19"), true);
  assert.equal(isMondayDateString("2026-10-20"), false);
  assert.equal(isMondayDateString("not-a-date"), false);
});

test("todayKSTDateString matches mondayOfThisWeekKST's own date extraction for the same instant", () => {
  const instant = new Date("2026-10-20T18:00:00Z");
  assert.equal(todayKSTDateString(instant), "2026-10-21");
});

import { todayKSTLabel } from "./week";

test("todayKSTLabel uses the Seoul calendar day, not the UTC day", () => {
  // 2026-10-21T16:00:00Z is already Thursday 2026-10-22 01:00 in Seoul.
  assert.equal(todayKSTLabel(new Date("2026-10-21T16:00:00Z")), "2026년 10월 22일 · 목요일");
  assert.equal(todayKSTLabel(new Date("2026-10-17T03:00:00Z")), "2026년 10월 17일 · 토요일");
});

import { dateTimeKSTLabel, timeKSTLabel } from "./week";

test("message time labels use Asia/Seoul, including across midnight", () => {
  assert.equal(timeKSTLabel("2026-10-22T05:05:00Z"), "14:05");
  assert.equal(dateTimeKSTLabel("2026-10-22T05:05:00Z"), "10/22 14:05");
  // 15:30 UTC is already the next day in Seoul.
  assert.equal(dateTimeKSTLabel("2026-10-21T15:30:00Z"), "10/22 00:30");
});
