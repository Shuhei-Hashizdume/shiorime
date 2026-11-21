// API を呼ぶ部品。返事の形は docs/design/api.md に合わせる。

export type FieldReason =
  | "required"
  | "too_long"
  | "out_of_range"
  | "invalid_format"
  | "invalid_value"
  | "not_allowed";

export type FieldError = {
  field: string;
  reason: FieldReason;
  limit?: number;
  min?: number;
  max?: number;
};

/** API が断ったとき（api.md 1-3 の形）と、通信できなかったときに投げる。 */
export class ApiError extends Error {
  constructor(
    readonly status: number, // 通信できなかったときは 0
    readonly code: string,
    readonly fields: FieldError[] = [],
    readonly details: Record<string, unknown> = {},
  ) {
    super(code);
  }
}

export const NETWORK_ERROR = "NETWORK_ERROR";

async function request<T>(method: string, path: string, body?: unknown, headers: Record<string, string> = {}): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? headers : { "Content-Type": "application/json", ...headers },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, NETWORK_ERROR);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    // 本文が JSON でない（Caddy の 502 など）
  }

  if (!response.ok) {
    const error = (data as { error?: { code?: string; fields?: FieldError[]; details?: Record<string, unknown> } })
      ?.error;
    throw new ApiError(response.status, error?.code ?? `HTTP_${response.status}`, error?.fields, error?.details);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown, headers?: Record<string, string>) => request<T>("POST", path, body, headers),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  put: <T>(path: string, body?: unknown) => request<T>("PUT", path, body),
  delete: <T>(path: string) => request<T>("DELETE", path),
};

// ---- 自分（api.md 7-1・7-2）----

export type Attribute = "high_school" | "university" | "working" | "homemaker" | "other";

export type Me = {
  id: string;
  email: string;
  attribute: Attribute;
};

export const ATTRIBUTE_LABELS: Record<Attribute, string> = {
  high_school: "高校生",
  university: "大学生・専門学生",
  working: "社会人",
  homemaker: "主婦・主夫",
  other: "その他",
};
