/**
 * CR-005: continue on another device with a password. Pure helpers and the login flow with its
 * dependencies passed in (so a test can prove that the password path never creates an anonymous
 * UID). The password lives in component state only: nothing here writes it to any storage.
 */
export const PASSWORD_MIN = 8;
export const PASSWORD_MAX = 64;

export type PasswordCheck = { key: "length" | "letter" | "digit" | "symbol" | "characters"; label: string; ok: boolean };

const PRINTABLE_ASCII = /^[\x21-\x7e]*$/; // no space, no control characters, no non-ASCII

/** The rules shown under the input, each with its own state (the screen writes the state in words too, not only in colour). */
export function passwordChecks(password: string): PasswordCheck[] {
  return [
    { key: "length", label: `${PASSWORD_MIN}자 이상 ${PASSWORD_MAX}자 이하`, ok: password.length >= PASSWORD_MIN && password.length <= PASSWORD_MAX },
    { key: "letter", label: "영문 포함", ok: /[A-Za-z]/.test(password) },
    { key: "digit", label: "숫자 포함", ok: /[0-9]/.test(password) },
    { key: "symbol", label: "특수문자 포함", ok: /[^A-Za-z0-9]/.test(password) && PRINTABLE_ASCII.test(password) },
    { key: "characters", label: "공백 없이 영문·숫자·특수문자만", ok: password.length > 0 && PRINTABLE_ASCII.test(password) },
  ];
}

export function passwordFollowsRules(password: string): boolean {
  return passwordChecks(password).every((c) => c.ok);
}

export type RegisterForm = { password: string; confirm: string; acknowledged: boolean; busy: boolean };

/** Why the [등록] button is still off, or null when it may be pressed. */
export function registerBlocker(form: RegisterForm): string | null {
  if (form.busy) return "처리하는 중이에요.";
  if (!passwordFollowsRules(form.password)) return "암호 규칙을 모두 채워 주세요.";
  if (form.confirm !== form.password) return "암호 확인이 암호와 달라요.";
  if (!form.acknowledged) return "안내를 확인했다는 표시를 체크해 주세요.";
  return null;
}

export const ACKNOWLEDGE_TEXT =
  "암호를 잊으면 되찾을 수 없고, 이 암호를 아는 사람은 내 학습 기록을 볼 수 있다는 것을 이해했어요. 다른 사이트에서 쓰는 암호는 쓰지 않을게요.";

export const LOGOUT_CONFIRM_TEXT = "로그아웃하면 이 기기에서는 암호로 다시 들어와야 해요.";
export const SWITCH_WARNING_NO_PASSWORD = "지금 이 기기의 학습 기록은 암호를 등록하지 않았다면 다시 볼 수 없어요. 계속할까요?";
export const SWITCH_WARNING_WITH_PASSWORD = "지금 기록은 이 암호로 다시 들어올 수 있어요. 다른 기록으로 들어갈까요?";

type ErrorLike = { status?: number; code?: string; message?: string } | null | undefined;

/** The sentence under the form for a failed call. A 409 and a 422 show the server's own sentence. */
export function passwordErrorMessage(error: ErrorLike, fallback: string): string {
  if (!error) return fallback;
  if (error.status === 401) return "암호가 맞지 않아요.";
  if (error.status === 429) return "잠시 후 다시 시도해 주세요.";
  if ((error.status === 409 || error.status === 422) && error.message) return error.message;
  if (error.status === 0 && error.message) return error.message; // network / timeout sentences from the api layer
  return fallback;
}

export type LoginDeps<S> = {
  /** POST /api/auth/password/login -> custom token. Needs no session. */
  requestToken: (password: string) => Promise<string>;
  /** Signs in with the custom token (Firebase signInWithCustomToken, or the dev UID). */
  signInWithToken: (customToken: string) => Promise<S>;
  /** GET /api/user/profile with that session: whether the stored consent is for the current terms. */
  consentIsCurrent: (session: S) => Promise<boolean>;
  /** Forget what belongs to the previous record on this device (wizard draft). */
  clearLocalDraft: () => void;
  markConsentStored: () => void;
};

export type LoginResult<S> = { session: S; consent: "current" | "needed" };

/**
 * The password path. There is no call to create an anonymous session here by design: the signed-in
 * UID is the one the server found. Consent is not asked again when the stored one is current.
 */
export async function loginWithPasswordFlow<S>(password: string, deps: LoginDeps<S>): Promise<LoginResult<S>> {
  const customToken = await deps.requestToken(password);
  const session = await deps.signInWithToken(customToken);
  deps.clearLocalDraft();
  if (await deps.consentIsCurrent(session)) {
    deps.markConsentStored();
    return { session, consent: "current" };
  }
  return { session, consent: "needed" };
}

/** A dev-mode custom token is "dev-<uid>"; anything else is refused before it can be stored. */
export function devUidFromToken(token: string): string | null {
  const match = /^dev-([A-Za-z0-9_-]{6,128})$/.exec(token);
  return match ? match[1] : null;
}

/** "2026-10-27 14:05" style date for the "등록됨" line, from the UTC ISO time the server stores (shown in Asia/Seoul). */
export function formatSetAt(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  const parts = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
  return parts;
}
