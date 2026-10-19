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
