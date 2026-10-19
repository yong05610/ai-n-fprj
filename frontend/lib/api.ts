export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8001";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

type RequestOptions = {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  token?: string;
  /** Default 20s; AI endpoints (path/recommend, plan/generate) pass a longer budget. */
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT_MS = 20_000;

async function performRequest(
  path: string,
  { method = "GET", body, token, timeoutMs = DEFAULT_TIMEOUT_MS }: RequestOptions,
): Promise<{ data: unknown; headers: Headers }> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError(0, "REQUEST_TIMEOUT", "요청이 시간 안에 끝나지 않았습니다. 다시 시도해 주세요.");
    }
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  } finally {
    clearTimeout(timer);
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    const code = typeof detail === "object" && detail && "code" in detail ? String((detail as { code: unknown }).code) : "INTERNAL_ERROR";
    const message =
      typeof detail === "object" && detail && "message" in detail
        ? String((detail as { message: unknown }).message)
        : "요청을 처리하지 못했습니다. 다시 시도해 주세요.";
    throw new ApiError(response.status, code, message);
  }
  return { data, headers: response.headers };
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { data } = await performRequest(path, options);
  return data as T;
}

/** Like apiRequest, but also returns response headers (e.g. list-truncation flags). */
export async function apiRequestWithHeaders<T>(path: string, options: RequestOptions = {}): Promise<{ data: T; headers: Headers }> {
  const { data, headers } = await performRequest(path, options);
  return { data: data as T, headers };
}
