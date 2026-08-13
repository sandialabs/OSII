import type { ScopeDescribeRequest, SearchMode } from "../api/types";

export const ACTIVITY_HISTORY_KEY = "osii.activity-history.v1";
export const ACTIVITY_HISTORY_LIMIT = 20;
export const ACTIVITY_HISTORY_EVENT = "osii:activity-history-changed";

export type ActivityHistoryKind = "search" | "chat_prompt";

export type ActivityHistoryEntry = {
  id: string;
  kind: ActivityHistoryKind;
  text: string;
  timestamp: string;
  scope: ScopeDescribeRequest;
  mode?: SearchMode;
};

type ActivityHistoryStore = {
  version: 1;
  searches: ActivityHistoryEntry[];
  chat_prompts: ActivityHistoryEntry[];
};

const EMPTY_STORE: ActivityHistoryStore = {
  version: 1,
  searches: [],
  chat_prompts: [],
};

function validScope(value: unknown): value is ScopeDescribeRequest {
  if (!value || typeof value !== "object") return false;
  const scope = value as Record<string, unknown>;
  if (scope.scope_type === "root") return true;
  if (scope.scope_type === "folder") return typeof scope.folder_id === "string";
  if (scope.scope_type === "collection") return typeof scope.collection_id === "string";
  if (scope.scope_type === "object") return typeof scope.file_id === "string";
  return false;
}

function validEntry(value: unknown, kind: ActivityHistoryKind): value is ActivityHistoryEntry {
  if (!value || typeof value !== "object") return false;
  const entry = value as Record<string, unknown>;
  return (
    entry.kind === kind &&
    typeof entry.id === "string" &&
    typeof entry.text === "string" &&
    entry.text.trim().length > 0 &&
    typeof entry.timestamp === "string" &&
    validScope(entry.scope) &&
    (kind !== "search" || ["semantic", "lexical", "hybrid"].includes(String(entry.mode)))
  );
}

function parseStore(value: string | null): ActivityHistoryStore {
  if (!value) return { ...EMPTY_STORE };
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    if (parsed.version !== 1) return { ...EMPTY_STORE };
    const searches = Array.isArray(parsed.searches)
      ? parsed.searches.filter((entry) => validEntry(entry, "search")).slice(0, ACTIVITY_HISTORY_LIMIT)
      : [];
    const chatPrompts = Array.isArray(parsed.chat_prompts)
      ? parsed.chat_prompts.filter((entry) => validEntry(entry, "chat_prompt")).slice(0, ACTIVITY_HISTORY_LIMIT)
      : [];
    return { version: 1, searches, chat_prompts: chatPrompts };
  } catch {
    return { ...EMPTY_STORE };
  }
}

export function readActivityHistory(): ActivityHistoryStore {
  if (typeof window === "undefined") return { ...EMPTY_STORE };
  try {
    return parseStore(window.localStorage.getItem(ACTIVITY_HISTORY_KEY));
  } catch {
    return { ...EMPTY_STORE };
  }
}

function writeActivityHistory(store: ActivityHistoryStore): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(ACTIVITY_HISTORY_KEY, JSON.stringify(store));
    window.dispatchEvent(new Event(ACTIVITY_HISTORY_EVENT));
  } catch {
    // History is convenience state. Storage restrictions must never block Search or Chat.
  }
}

function scopeKey(scope: ScopeDescribeRequest): string {
  if (scope.scope_type === "root") return "root";
  if (scope.scope_type === "folder") return `folder:${scope.folder_id}`;
  if (scope.scope_type === "collection") return `collection:${scope.collection_id}`;
  return `object:${scope.file_id}`;
}

function newId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

export function addActivityHistoryEntry(input: {
  kind: ActivityHistoryKind;
  text: string;
  scope: ScopeDescribeRequest;
  mode?: SearchMode;
}): void {
  const text = input.text.trim();
  if (!text) return;
  const store = readActivityHistory();
  const key = input.kind === "search" ? "searches" : "chat_prompts";
  const normalizedText = text.toLocaleLowerCase();
  const normalizedScope = scopeKey(input.scope);
  const retained = store[key].filter((entry) => !(
    entry.text.trim().toLocaleLowerCase() === normalizedText &&
    scopeKey(entry.scope) === normalizedScope
  ));
  const entry: ActivityHistoryEntry = {
    id: newId(),
    kind: input.kind,
    text,
    timestamp: new Date().toISOString(),
    scope: input.scope,
    ...(input.kind === "search" ? { mode: input.mode ?? "semantic" } : {}),
  };
  store[key] = [entry, ...retained].slice(0, ACTIVITY_HISTORY_LIMIT);
  writeActivityHistory(store);
}

export function removeActivityHistoryEntry(kind: ActivityHistoryKind, id: string): void {
  const store = readActivityHistory();
  const key = kind === "search" ? "searches" : "chat_prompts";
  store[key] = store[key].filter((entry) => entry.id !== id);
  writeActivityHistory(store);
}

export function clearActivityHistory(kind: ActivityHistoryKind): void {
  const store = readActivityHistory();
  if (kind === "search") store.searches = [];
  else store.chat_prompts = [];
  writeActivityHistory(store);
}

export function entriesForKind(store: ActivityHistoryStore, kind: ActivityHistoryKind): ActivityHistoryEntry[] {
  return kind === "search" ? store.searches : store.chat_prompts;
}
