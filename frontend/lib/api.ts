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
};

export async function apiRequest<T>(path: string, { method = "GET", body, token }: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "NETWORK_ERROR", "서버에 연결할 수 없습니다. 잠시 후 다시 시도해 주세요.");
  }

  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    const code = typeof detail === "object" && detail?.code ? detail.code : "INTERNAL_ERROR";
    const message =
      typeof detail === "object" && detail?.message ? detail.message : "요청을 처리하지 못했습니다. 다시 시도해 주세요.";
    throw new ApiError(response.status, code, message);
  }
  return data as T;
}
