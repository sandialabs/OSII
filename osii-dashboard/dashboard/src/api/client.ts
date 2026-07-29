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

type JsonBody = Record<string, unknown> | Array<unknown> | null;

function buildHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
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
        : `Request failed with status ${response.status}`;
    throw new ApiError(message, response.status, data);
  }

  return data as TResponse;
}