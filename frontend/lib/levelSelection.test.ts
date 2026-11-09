// CR-012 (2nd): the level combo boxes and the other small changes of the learning-path screen.
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { LevelCombo } from "../components/LevelCombo";
import {
  EMPTY_LEVEL,
  adjustTarget,
  editDescription,
  editName,
  levelProblem,
  nextActiveIndex,
  pickLevel,
  selectionFrom,
  targetOptions,
  type LevelItem,
} from "./levelSelection";

const LEVELS: LevelItem[] = [
  { order: 1, name: "입문자", description: "처음 배움" },
  { order: 2, name: "기초 프로그래머", description: "문법을 안다" },
  { order: 3, name: "실무 개발자", description: "작은 서비스를 만든다" },
  { order: 4, name: "설계자", description: "구조를 설계한다" },
];
const noop = () => {};
const read = (path: string) => readFileSync(new URL(path, import.meta.url), "utf8");

test("picking from the list sets order, name and description; rewriting the name keeps the order", () => {
  const picked = pickLevel(LEVELS, 3);
  assert.deepEqual(picked, { order: 3, name: "실무 개발자", description: "작은 서비스를 만든다" });
  const edited = editName(picked, "백엔드 실무자");
  assert.equal(edited.order, 3, "the order stays the one of the last picked level");
  assert.equal(edited.name, "백엔드 실무자");
  assert.equal(edited.description, "작은 서비스를 만든다");
  assert.equal(editDescription(edited, "내 설명").order, 3);
});

test("pick -> rewrite the name -> the values the plan request carries are the rewritten name and the picked order", () => {
  let current = pickLevel(LEVELS, 1);
  let target = pickLevel(LEVELS, 3);
  current = editName(current, "파이썬 처음 배우는 사람");
  target = editName(target, "작은 도구를 만드는 사람");
  // the wizard sends current_level_order / current_level_name (and the description) from exactly these fields
  assert.deepEqual([current.order, current.name], [1, "파이썬 처음 배우는 사람"]);
  assert.deepEqual([target.order, target.name], [3, "작은 도구를 만드는 사람"]);
  assert.equal(levelProblem(current), null);
  assert.equal(levelProblem(target), null);
  const wizard = read("../components/LearningPathWizard.tsx");
  assert.match(wizard, /current_level_order: currentOrder,\s+current_level_name: currentLevelName,/);
  assert.match(wizard, /target_level_order: targetOrder,\s+target_level_name: targetLevelName,/);
});

test("text typed without ever picking from the list blocks the plan; an empty name blocks it", () => {
  assert.equal(levelProblem(editName(EMPTY_LEVEL, "내가 쓴 수준")), "목록에서 수준을 골라 주세요.");
  assert.equal(levelProblem(EMPTY_LEVEL), "목록에서 수준을 골라 주세요.");
  assert.equal(levelProblem(editName(pickLevel(LEVELS, 2), "")), "수준 이름을 입력해 주세요.");
  assert.equal(levelProblem(editName(pickLevel(LEVELS, 2), "   ")), "수준 이름을 입력해 주세요.");
  assert.match(levelProblem(editName(pickLevel(LEVELS, 2), "가".repeat(101))) ?? "", /100자/);
  assert.equal(levelProblem(editName(pickLevel(LEVELS, 2), "가".repeat(100))), null);
  assert.match(levelProblem(editDescription(pickLevel(LEVELS, 2), "가".repeat(2001))) ?? "", /2000자/);
  assert.equal(levelProblem(editDescription(pickLevel(LEVELS, 2), "가".repeat(2000))), null);
});

test("the target list shows only levels above the current one", () => {
  assert.deepEqual(targetOptions(LEVELS, 2).map((l) => l.order), [3, 4]);
  assert.deepEqual(targetOptions(LEVELS, 4), []);
  assert.deepEqual(targetOptions(LEVELS, null).map((l) => l.order), [1, 2, 3, 4]);
});

test("changing the current level moves a same-or-lower target to the next level, otherwise leaves it", () => {
  const target = pickLevel(LEVELS, 2);
  const higher = adjustTarget(LEVELS, pickLevel(LEVELS, 3), target);
  assert.deepEqual([higher.order, higher.name], [4, "설계자"]);
  const same = adjustTarget(LEVELS, pickLevel(LEVELS, 2), target);
  assert.equal(same.order, 3);
  const kept = adjustTarget(LEVELS, pickLevel(LEVELS, 1), editName(target, "내가 고친 이름"));
  assert.equal(kept.name, "내가 고친 이름", "a still-higher target is not touched, even with a rewritten name");
  const top = adjustTarget(LEVELS, pickLevel(LEVELS, 4), pickLevel(LEVELS, 3));
  assert.deepEqual(top, EMPTY_LEVEL, "no higher level: the target is empty (and blocks the plan)");
  const filled = adjustTarget(LEVELS, pickLevel(LEVELS, 1), EMPTY_LEVEL);
  assert.equal(filled.order, 2, "a target that was never set gets the next level");
  assert.deepEqual(selectionFrom(undefined), EMPTY_LEVEL);
});

test("keyboard moves in the list stay inside it", () => {
  assert.equal(nextActiveIndex("ArrowDown", -1, 4, 2), 2, "the first ArrowDown lands on the picked level");
  assert.equal(nextActiveIndex("ArrowDown", -1, 4, -1), 0);
  assert.equal(nextActiveIndex("ArrowDown", 3, 4, 0), 3);
  assert.equal(nextActiveIndex("ArrowUp", 0, 4, 0), 0);
  assert.equal(nextActiveIndex("ArrowUp", 2, 4, 0), 1);
  assert.equal(nextActiveIndex("ArrowUp", -1, 4, 0), 3);
  assert.equal(nextActiveIndex("ArrowDown", -1, 0, -1), -1);
});

const comboProps = {
  id: "current-level",
  label: "현재 수준",
  options: LEVELS,
  selectedOrder: 2,
  name: "기초 프로그래머",
  description: "문법을 안다",
  onNameChange: noop,
  onPick: noop,
  onDescriptionChange: noop,
};

test("the combo is one labelled combobox with the name in it and a folded description; no order number", () => {
  const html = renderToStaticMarkup(createElement(LevelCombo, comboProps));
  assert.match(html, /<label for="current-level">현재 수준<\/label>/);
  assert.match(html, /<input[^>]*id="current-level"[^>]*role="combobox"/);
  assert.match(html, /aria-expanded="false"/);
  assert.match(html, /aria-controls="current-level-list"/);
  assert.match(html, /value="기초 프로그래머"/);
  assert.ok(!html.includes('role="listbox"'), "closed at first");
  assert.match(html, /<details class="level-desc"><summary>설명 보기·고치기<\/summary><textarea[^>]*aria-label="현재 수준 설명"/);
  assert.ok(!/id="current-level-name"|수준 이름<\/label>/.test(html), "no separate name input");
  assert.ok(!/>\s*[1-4]\s*</.test(html.replace(/<[^>]+>/g, "><")), "no order number is shown");
});

test("the open list always shows every option (nothing is filtered by the typed text) and marks the picked one", () => {
  const html = renderToStaticMarkup(createElement(LevelCombo, { ...comboProps, name: "완전히 다른 글자", initialOpen: true }));
  assert.match(html, /role="listbox"/);
  assert.match(html, /aria-expanded="true"/);
  for (const l of LEVELS) assert.ok(html.includes(`>${l.name}</li>`), l.name);
  assert.equal((html.match(/role="option"/g) ?? []).length, 4);
  assert.match(html, /role="option"[^>]*aria-selected="true"[^>]*>기초 프로그래머/);
  assert.equal((html.match(/aria-selected="true"/g) ?? []).length, 1);
});

test("a problem is announced and linked to the box; an empty list disables the box", () => {
  const withProblem = renderToStaticMarkup(createElement(LevelCombo, { ...comboProps, problem: "목록에서 수준을 골라 주세요." }));
  assert.match(withProblem, /aria-invalid="true"/);
  assert.match(withProblem, /aria-describedby="current-level-problem"/);
  assert.match(withProblem, /<p class="error" id="current-level-problem" role="alert">목록에서 수준을 골라 주세요\.<\/p>/);
  const disabled = renderToStaticMarkup(createElement(LevelCombo, { ...comboProps, options: [], disabled: true, initialOpen: true }));
  assert.match(disabled, /<input[^>]*disabled/);
  assert.ok(!disabled.includes('role="listbox"'));
});

test("the screen: new button names, helper line, mockup wording, no old level inputs, plan blocked by a level problem", () => {
  const w = read("../components/LearningPathWizard.tsx");
  assert.ok(w.includes("✦ 목표 추천") && w.includes("이 분야에서 많이 목표로 삼는 직무를 추천해요."));
  assert.ok(w.includes('"✦ 과정 다시 추천받기" : "✦ 과정 추천받기"'));
  for (const old of ["✦ 예시 다시 보기", "대표 직무·목표 예시 보기", "✦ 다시 추천받기", "✦ AI 세부 과정·수준 추천"]) {
    assert.ok(!w.includes(old), old);
  }
  assert.ok(w.includes("3. 현재 수준과 목표 수준</label>"));
  assert.ok(w.includes("같은 칸에서 이름을 바로 고쳐 쓰세요. 수준 번호는 표시하지 않습니다."));
  for (const gone of ["current-level-name", "target-level-name", "current-level-desc", "target-level-desc", "<datalist"]) {
    assert.ok(!w.includes(gone), gone);
  }
  assert.match(w, /id="current-level"[\s\S]*id="target-level"/);
  assert.match(w, /Boolean\(currentProblem\) \|\|\s+Boolean\(targetProblem\)/);
  assert.ok(w.includes("if (dateError || currentProblem || targetProblem) return;"));
});

test("the preview tasks: numbered tinted title line, divider, and a small link-style delete button", () => {
  const w = read("../components/LearningPathWizard.tsx");
  assert.match(w, /<div className="task-edit-head">\s*<span className="task-no"[^>]*>\s*\{i \+ 1\}\s*<\/span>\s*<input/);
  assert.match(w, /<button type="button" className="link-btn task-remove" onClick=\{\(\) => removeTask\(i\)\}>\s*과업 삭제/);
  assert.ok(!/className="btn secondary small" onClick=\{\(\) => removeTask/.test(w));
  const css = read("../app/globals.css");
  assert.match(css, /\.task-edit-head \{[^}]*background: var\(--lav\)/);
  assert.match(css, /\.task-no \{/);
  assert.match(css, /\.task-edit-row \{ border-color: #d9dcec; margin-bottom: 12px; \}/);
  // new styles use the existing colour variables only (the one literal grey is the existing row border's own tone)
  const block = css.slice(css.indexOf("/* CR-012 (2nd): one editable combo"), css.indexOf("/* CR-012 (2nd): the preview tasks"));
  assert.ok(!/#[0-9a-f]{3,6}/i.test(block.replace(/#fff\b/gi, "")), "combo styles: no new hard-coded colour");
});
