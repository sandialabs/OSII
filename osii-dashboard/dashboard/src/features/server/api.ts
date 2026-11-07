export type User = { id: string; username: string; role: "reader" | "curator" | "admin"; active: boolean; must_change_password: boolean };
export type Doc = { file_id: string; filename: string; source_relpath: string; text?: string; media_type?: string; size_bytes?: number; updated_at?: string };
export type Hit = Doc & { chunk_id: string; snippet: string; char_start: number; char_end: number; source_origin: unknown; score?: number };
export type Model = { id: string; name: string; capabilities: string[] };

export async function api<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  const csrf = document.cookie.split("; ").find(value => value.startsWith("osii_csrf="))?.split("=").slice(1).join("=") ?? "";
  const response = await fetch(path, { method, credentials: "same-origin", headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf) }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) {
    if (response.status === 401 && path !== "/api/auth/login") window.dispatchEvent(new Event("osii-session-expired"));
    throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${response.status})`);
  }
  return data as T;
}

export type Scope = { scope_type: string; collection_id?: string; folder_id?: string; file_id?: string };
export type Collection = { id: string; name: string; description: string; members: string[]; owner_id: string | null; visibility: "private" | "shared"; can_manage: boolean };
