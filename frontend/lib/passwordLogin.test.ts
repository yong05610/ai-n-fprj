import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";

import { ConsentModal } from "../components/ConsentModal";
import { PasswordCard, PasswordCardView, type PasswordPanel } from "../components/PasswordCard";
import { PasswordLoginForm, PasswordRegisterForm } from "../components/PasswordForms";
import { parsePasswordLoginFlag } from "./modeBanner";
import {
  LOGOUT_CONFIRM_TEXT,
  SWITCH_WARNING_NO_PASSWORD,
  SWITCH_WARNING_WITH_PASSWORD,
  devUidFromToken,
  formatSetAt,
  loginWithPasswordFlow,
  passwordChecks,
  passwordErrorMessage,
  passwordFollowsRules,
  registerBlocker,
} from "./passwordLogin";

const GOOD = "Tb7#kq2Lm";
const noop = () => {};
const noopAsync = async () => {};

// --- rules ---

test("the rule list reports each rule separately", () => {
  const states = (p: string) => Object.fromEntries(passwordChecks(p).map((c) => [c.key, c.ok]));
  assert.deepEqual(states(""), { length: false, letter: false, digit: false, symbol: false, characters: false });
  assert.deepEqual(states("abcdefgh"), { length: true, letter: true, digit: false, symbol: false, characters: true });
  assert.deepEqual(states(GOOD), { length: true, letter: true, digit: true, symbol: true, characters: true });
  assert.equal(states("Tb7# kq2Lm").characters, false); // a space
  assert.equal(states("Tb7#kq2L한").characters, false); // not ASCII
});

test("the password rules match the server's: 8 to 64, letter + digit + symbol, no space, ASCII only", () => {
  assert.equal(passwordFollowsRules(GOOD), true);
  assert.equal(passwordFollowsRules("Ab1#xyz"), false); // 7
  assert.equal(passwordFollowsRules("Tb7#kq2L"), true); // 8
  assert.equal(passwordFollowsRules("Tb7#kq2L" + "m".repeat(56)), true); // 64
  assert.equal(passwordFollowsRules("Tb7#kq2L" + "m".repeat(57)), false); // 65
  for (const bad of ["12345678#!", "Abcdefgh#!", "Abcdefgh12", "Tb7# kq2Lm", "Tb7#kq2L한", "Tb7#kq2L\tm", ""]) {
    assert.equal(passwordFollowsRules(bad), false, JSON.stringify(bad));
  }
});

test("the register button needs the rules, a matching confirmation and the checkbox", () => {
  const ok = { password: GOOD, confirm: GOOD, acknowledged: true, busy: false };
  assert.equal(registerBlocker(ok), null);
  assert.ok(registerBlocker({ ...ok, acknowledged: false }));
  assert.ok(registerBlocker({ ...ok, confirm: GOOD + "x" }));
  assert.ok(registerBlocker({ ...ok, password: "short", confirm: "short" }));
  assert.ok(registerBlocker({ ...ok, busy: true })); // no double press while saving
});

test("error sentences: 401, 429, and the server's own sentence for 409 / 422", () => {
  assert.equal(passwordErrorMessage({ status: 401, message: "x" }, "f"), "암호가 맞지 않아요.");
  assert.equal(passwordErrorMessage({ status: 429, message: "x" }, "f"), "잠시 후 다시 시도해 주세요.");
  assert.equal(passwordErrorMessage({ status: 409, message: "이 암호는 쓸 수 없어요. 다른 암호를 정해 주세요." }, "f"), "이 암호는 쓸 수 없어요. 다른 암호를 정해 주세요.");
  assert.equal(passwordErrorMessage({ status: 422, message: "8자 이상 64자 이하여야 해요." }, "f"), "8자 이상 64자 이하여야 해요.");
  assert.equal(passwordErrorMessage({ status: 500, message: "boom" }, "fallback"), "fallback");
  assert.equal(passwordErrorMessage(null, "fallback"), "fallback");
});

test("only a literal true in /health turns the feature on", () => {
  assert.equal(parsePasswordLoginFlag({ password_login_enabled: true }), true);
  for (const v of [false, "true", 1, null, undefined]) assert.equal(parsePasswordLoginFlag({ password_login_enabled: v }), false);
  assert.equal(parsePasswordLoginFlag({}), false);
  assert.equal(parsePasswordLoginFlag(null), false);
  assert.equal(parsePasswordLoginFlag("x"), false);
});

test("dev custom tokens: only dev-<uid> is accepted", () => {
  assert.equal(devUidFromToken("dev-alice-uid-001"), "alice-uid-001");
  for (const bad of ["alice-uid-001", "dev-", "dev-ab", "dev-a b c d e f", "Bearer dev-alice-uid-001", "dev-alice/../x"]) {
    assert.equal(devUidFromToken(bad), null, bad);
  }
});

test("the registered date is shown in Seoul time", () => {
  assert.equal(formatSetAt("2026-10-27T16:00:00Z"), "2026-10-28"); // 01:00 KST the next day
  assert.equal(formatSetAt(null), "");
  assert.equal(formatSetAt("not a date"), "");
});

// --- the login flow ---

function deps(over: Partial<Parameters<typeof loginWithPasswordFlow<{ uid: string }>>[1]> = {}) {
  const calls: string[] = [];
  const d = {
    requestToken: async (p: string) => {
      calls.push(`token:${p === GOOD ? "pw" : "other"}`);
      return "custom";
    },
    signInWithToken: async (t: string) => {
      calls.push(`signIn:${t}`);
      return { uid: "alice-uid-001" };
    },
    consentIsCurrent: async () => {
      calls.push("consent?");
      return true;
    },
    clearLocalDraft: () => calls.push("clear-draft"),
    markConsentStored: () => calls.push("store-consent"),
    ...over,
  };
  return { d, calls };
}

test("the password path: token, sign in, current consent -> ready, no consent window", async () => {
  const { d, calls } = deps();
  const result = await loginWithPasswordFlow(GOOD, d);
  assert.deepEqual(result, { session: { uid: "alice-uid-001" }, consent: "current" });
  assert.deepEqual(calls, ["token:pw", "signIn:custom", "clear-draft", "consent?", "store-consent"]);
});

test("a different terms version asks for consent again and does not store the old flag", async () => {
  const { d, calls } = deps({ consentIsCurrent: async () => false });
  assert.equal((await loginWithPasswordFlow(GOOD, d)).consent, "needed");
  assert.ok(!calls.includes("store-consent"));
});

test("a wrong password stops before any sign-in or local change", async () => {
  const { d, calls } = deps({
    requestToken: async () => {
      throw Object.assign(new Error("x"), { status: 401 });
    },
  });
  await assert.rejects(() => loginWithPasswordFlow("bad", d));
  assert.deepEqual(calls, []);
});

test("the login flow and the session code never create an anonymous UID", () => {
  const provider = readFileSync(new URL("../components/AuthProvider.tsx", import.meta.url), "utf8");
  const start = provider.indexOf("const loginWithPassword");
  const end = provider.indexOf("const logout");
  assert.ok(start > 0 && end > start);
  const body = provider.slice(start, end);
  assert.ok(!body.includes("startAnonymousSession") && !body.includes("signInAnonymously"));
  const flow = readFileSync(new URL("./passwordLogin.ts", import.meta.url), "utf8");
  assert.ok(!flow.includes("Anonymous"));
  const session = readFileSync(new URL("./session.ts", import.meta.url), "utf8");
  const fn = session.slice(session.indexOf("export async function signInWithPasswordToken"), session.indexOf("export async function endSession"));
  assert.ok(fn.includes("signInWithCustomToken") && !fn.includes("signInAnonymously"));
});

test("the password is never written to a browser storage", () => {
  for (const file of ["../lib/passwordLogin.ts", "../components/PasswordForms.tsx", "../components/PasswordCard.tsx"]) {
    const source = readFileSync(new URL(file, import.meta.url), "utf8");
    assert.ok(!/localStorage|sessionStorage|indexedDB|saveWizardDraft|document\.cookie/.test(source), file);
  }
});

// --- screens ---

const view = (over: Partial<Parameters<typeof PasswordCardView>[0]> = {}) =>
  renderToStaticMarkup(
    createElement(PasswordCardView, {
      registered: false,
      setAt: null,
      panel: "none" as PasswordPanel,
      busy: false,
      message: null,
      onOpen: noop,
      onRegister: noopAsync,
      onDisable: noop,
      onLogout: noop,
      onSwitchLogin: noopAsync,
      ...over,
    }),
  );

test("before registering: explanation, two password inputs, rules in words, checkbox, a disabled button, no logout", () => {
  const html = view();
  assert.ok(html.includes("다른 기기에서 이어 쓰기"));
  assert.ok(html.includes("암호를 등록하면 다른 PC·휴대폰에서 암호만으로 이 학습 기록을 이어 쓸 수 있어요"));
  assert.equal((html.match(/type="password"/g) ?? []).length, 2);
  assert.equal((html.match(/autoComplete="new-password"/g) ?? html.match(/autocomplete="new-password"/g) ?? []).length, 2);
  assert.ok(html.includes('for="pw-new"') && html.includes('for="pw-confirm"'));
  assert.ok(html.includes("8자 이상 64자 이하") && html.includes("영문 포함") && html.includes("숫자 포함") && html.includes("특수문자 포함"));
  assert.ok(html.includes("필요") && !html.includes("충족"), "unmet rules are worded, not only coloured");
  assert.ok(html.includes("암호를 잊으면 되찾을 수 없고"));
  assert.match(html, /<button[^>]*id="pw-submit"[^>]*disabled/);
  assert.ok(!html.includes("로그아웃"), "no logout while the record has no password");
  assert.ok(html.includes("다른 기기에서 등록한 암호로 로그인"));
});

test("after registering: the date, change, switch off and logout", () => {
  const html = view({ registered: true, setAt: "2026-10-27T03:00:00Z" });
  assert.ok(html.includes("등록됨 (2026-10-27)"));
  for (const label of ["암호 바꾸기", "암호 로그인 끄기", "로그아웃"]) assert.ok(html.includes(label), label);
  assert.ok(!html.includes('id="pw-submit"'), "the register form is not shown while registered");
});

test("changing shows the same form with its own button and a cancel", () => {
  const html = view({ registered: true, panel: "change" });
  assert.ok(html.includes('id="pw-submit"') && html.includes("암호 바꾸기") && html.includes("취소"));
});

test("confirmation texts", () => {
  assert.ok(view({ registered: true, panel: "logout" }).includes(LOGOUT_CONFIRM_TEXT));
  assert.ok(view({ registered: true, panel: "disable" }).includes("암호 로그인을 끌까요?"));
  assert.ok(view({ registered: false, panel: "switch-warning" }).includes(SWITCH_WARNING_NO_PASSWORD));
  assert.ok(view({ registered: true, panel: "switch-warning" }).includes(SWITCH_WARNING_WITH_PASSWORD));
  const login = view({ panel: "switch-login" });
  assert.ok(login.includes("autoComplete=\"current-password\"") || login.includes('autocomplete="current-password"'));
  assert.ok(login.includes("두 기록을 합치지 않아요"));
});

test("a server message and the card message are shown as text", () => {
  const html = view({ message: "<b>x</b>" });
  assert.ok(html.includes("&lt;b&gt;x&lt;/b&gt;") && !html.includes("<b>x"));
});

test("the card is not rendered at all while the server has password login off", () => {
  assert.equal(renderToStaticMarkup(createElement(PasswordCard)), "");
});

test("the register and login forms have labelled password inputs", () => {
  const reg = renderToStaticMarkup(createElement(PasswordRegisterForm, { submitLabel: "등록", busyLabel: "…", onSubmit: noopAsync }));
  assert.ok(reg.includes("암호 확인"));
  const login = renderToStaticMarkup(createElement(PasswordLoginForm, { onSubmit: noopAsync }));
  assert.ok(login.includes('for="pw-login"') && login.includes("등록한 암호"));
  assert.match(login, /<button[^>]*id="pw-login-submit"[^>]*disabled/); // empty input: nothing to send
});

test("the consent window offers the login link only when the server has it on", () => {
  const props = { busy: false, errorMessage: null, onAccept: noop, onDecline: noop };
  const off = renderToStaticMarkup(createElement(ConsentModal, props));
  assert.ok(!off.includes("이미 암호를 등록했어요"));
  const on = renderToStaticMarkup(createElement(ConsentModal, { ...props, onPasswordLogin: noopAsync }));
  assert.ok(on.includes("이미 암호를 등록했어요(사용자 인증)"));
  assert.ok(on.includes("동의하고 시작하기"), "the consent flow itself is unchanged");
});

test("the consent text and the terms version are unchanged", () => {
  const consent = readFileSync(new URL("./consent.ts", import.meta.url), "utf8");
  assert.ok(consent.includes('TERMS_VERSION = "v1.1"'));
});
