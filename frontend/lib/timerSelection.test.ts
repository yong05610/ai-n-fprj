import assert from "node:assert/strict";
import { test } from "node:test";

import { taskToSelectForTimer, timerLocation } from "./timerSelection";

const running = { active: true, task_id: "t2", goal_id: "g1" };
const idle = { active: false, task_id: null, goal_id: null };

test("after a refresh the running timer's task is auto-selected when it belongs to the shown learning", () => {
  assert.equal(taskToSelectForTimer(running, "g1", ["t1", "t2"]), "t2");
});

test("switching away and back: the same rule selects the timer's task again", () => {
  assert.equal(taskToSelectForTimer(running, "g2", ["x1"]), null); // while viewing another learning
  assert.equal(taskToSelectForTimer(running, "g1", ["t1", "t2"]), "t2"); // after coming back
});

test("nothing is selected for an idle timer, no timer, or a task not in the loaded list", () => {
  assert.equal(taskToSelectForTimer(idle, "g1", ["t1", "t2"]), null);
  assert.equal(taskToSelectForTimer(null, "g1", ["t1", "t2"]), null);
  assert.equal(taskToSelectForTimer(running, "g1", ["t1"]), null);
});

test("timer from another learning is never auto-selected", () => {
  assert.equal(taskToSelectForTimer(running, null, ["t2"]), null);
});

test("timerLocation tells where the running timer is", () => {
  assert.equal(timerLocation(null, "g1", "t2"), "none");
  assert.equal(timerLocation(idle, "g1", "t2"), "none");
  assert.equal(timerLocation(running, "g1", "t2"), "selected-task");
  assert.equal(timerLocation(running, "g1", "t1"), "other-task-same-goal");
  assert.equal(timerLocation(running, "g1", null), "other-task-same-goal");
  assert.equal(timerLocation(running, "g2", "t2"), "other-goal");
});
