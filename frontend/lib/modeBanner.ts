/**
 * Which running mode the app shows in its top band (ops fix). Pure functions; the component reads
 * GET /health once and the NEXT_PUBLIC_AUTH_MODE of this build. Shown for development modes only:
 * a Firebase/Firestore server with a Firebase frontend shows nothing.
 */
export type HealthModes = { auth_mode: string; store_backend: string };
export type HealthState = { status: "loading" } | { status: "failed" } | { status: "ok"; modes: HealthModes };

const MODE_NAME = /^[a-z]{1,20}$/;

/** The two mode names of a /health body, or null when the body is not what the server sends. */
export function parseHealth(data: unknown): HealthModes | null {
  if (typeof data !== "object" || data === null) return null;
  const { auth_mode, store_backend } = data as Record<string, unknown>;
  if (typeof auth_mode !== "string" || typeof store_backend !== "string") return null;
  if (!MODE_NAME.test(auth_mode) || !MODE_NAME.test(store_backend)) return null;
  return { auth_mode, store_backend };
}

/** CR-005: whether the server offers password login. Anything but a literal true means off. */
export function parsePasswordLoginFlag(data: unknown): boolean {
  return typeof data === "object" && data !== null && (data as Record<string, unknown>).password_login_enabled === true;
}

/** The lines of the band; an empty list means the band is not shown at all. */
export function modeBannerLines(health: HealthState, frontendDev: boolean): string[] {
  const lines: string[] = [];
  if (health.status === "ok") {
    const { auth_mode, store_backend } = health.modes;
    const label = `${auth_mode} / ${store_backend}`;
    if (store_backend === "memory") {
      lines.push(`개발 모드예요. 서버를 끄면 데이터가 사라져요. (${label})`);
    } else if (auth_mode === "dev") {
      lines.push(`개발용 인증 모드예요. 가짜 토큰으로 접속돼요. (${label})`);
    }
  }
  if (frontendDev) {
    const mismatch =
      health.status === "ok" && health.modes.auth_mode !== "dev"
        ? ` 서버 인증은 ${health.modes.auth_mode} 예요. 서로 맞는지 확인해 주세요.`
        : "";
    lines.push(`프론트가 dev 인증 모드예요.${mismatch}`);
  }
  return lines;
}
