/**
 * Checks of the deployment settings baked into the build (Phase 7). A production build without a
 * usable API address must say so instead of quietly calling localhost.
 */
export type ApiConfigProblem = "missing" | "insecure";

export const API_CONFIG_MESSAGES: Record<ApiConfigProblem, string> = {
  missing: "배포 설정 오류: API 주소가 없어요. 관리자에게 NEXT_PUBLIC_API_BASE_URL 설정을 확인해 달라고 알려 주세요.",
  insecure: "배포 설정 오류: API 주소가 https 가 아니에요. 브라우저가 http 주소 호출을 막아요. NEXT_PUBLIC_API_BASE_URL 설정을 확인해 주세요.",
};

const DEV_DEFAULT = "http://localhost:8001";

function isLocalHttp(url: string): boolean {
  return /^http:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(url);
}

/** The API address of this build: the setting, or the local default in development only. */
export function resolveApiBase(raw: string | undefined, production: boolean): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");
  if (value) return value;
  return production ? "" : DEV_DEFAULT;
}

/**
 * What is wrong with the API address of a production build (null = fine, and always null in
 * development). http://localhost is allowed so a production build can be tried against a local server.
 */
export function apiConfigProblem(base: string, production: boolean): ApiConfigProblem | null {
  if (!production) return null;
  if (!base) return "missing";
  if (base.toLowerCase().startsWith("http://") && !isLocalHttp(base)) return "insecure";
  return null;
}
