import assert from "node:assert/strict";
import { test } from "node:test";

import { splitAnswer } from "./richText";

test("plain text stays one piece", () => {
  assert.deepEqual(splitAnswer("그냥 문장입니다."), [{ kind: "text", text: "그냥 문장입니다." }]);
});

test("inline code is split out", () => {
  assert.deepEqual(splitAnswer("`append` 로 추가해요"), [
    { kind: "inline", text: "append" },
    { kind: "text", text: " 로 추가해요" },
  ]);
});

test("a fenced block keeps its lines and drops the fence and language", () => {
  const out = splitAnswer("예시입니다.\n```python\na = [1]\na.append(2)\n```\n끝");
  assert.deepEqual(out, [
    { kind: "text", text: "예시입니다.\n" },
    { kind: "block", text: "a = [1]\na.append(2)" },
    { kind: "text", text: "\n끝" },
  ]);
});

test("an unclosed fence or lone backtick is left as text, and markup is never interpreted", () => {
  assert.deepEqual(splitAnswer("```python\n열린 채"), [{ kind: "text", text: "```python\n열린 채" }]);
  assert.deepEqual(splitAnswer("<b>굵게</b> `x`"), [
    { kind: "text", text: "<b>굵게</b> " },
    { kind: "inline", text: "x" },
  ]);
});
