// src/api/client.ts
export class ApiError extends Error {
  public readonly status: number;
  public readonly data: unknown;

  constructor(message: string, status: number, data: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

type ApiPolicy = { headers?: () => HeadersInit; unauthorized?: () => void };
let policy: ApiPolicy = {};
export function configureApiClient(value: ApiPolicy) { policy = value; }

type JsonBody = Record<string, unknown> | Array<unknown> | null;

function buildHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(policy.headers?.());
  new Headers(init).forEach((value, key) => headers.set(key, value));
  headers.set("Accept", "application/json");
  return headers;
}

export function buildApiUrl(path: string): string {
  return path;
}

export function buildArtifactUrl(relpath: string): string {
  return `/artifact/${relpath
    .split("/")
    .map((segment) => encodeURIComponent(segment))
    .join("/")}`;
}

export async function apiJson<TResponse>(
  path: string,
  init?: RequestInit & { json?: JsonBody },
): Promise<TResponse> {
  const headers = buildHeaders(init?.headers);

  let body = init?.body;
  if (init?.json !== undefined) {
    headers.set("Content-Type", "application/json");
    body = JSON.stringify(init.json);
  }

  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers,
    body,
  });

  if (response.status === 401) policy.unauthorized?.();
  const contentType = response.headers.get("Content-Type") ?? "";
  const isJson = contentType.includes("application/json");

  const data = isJson ? await response.json() : await response.text();

  if (!response.ok) {
    const message =
      typeof data === "object" &&
      data !== null &&
      "error" in data &&
      typeof (data as { error?: unknown }).error === "string"
        ? (data as { error: string }).error
        : typeof data === "object" &&
            data !== null &&
            "detail" in data &&
            typeof (data as { detail?: unknown }).detail === "string"
          ? (data as { detail: string }).detail
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, data);
  }

  return data as TResponse;
}
