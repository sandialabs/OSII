export type TraceEvidence = {
  id?: string; chunk_id?: string; file_id?: string; filename?: string; source_relpath?: string;
  text?: string; text_characters?: number; text_truncated?: boolean; representation?: string;
  rank?: number; score?: number; reason?: string; char_start?: number; char_end?: number;
  source_origin?: Record<string, unknown>;
};

export type TraceStage = {
  id: string; parent_id: string | null; kind: string; label: string; status: string;
  started_seconds: number; duration_seconds: number;
  inputs: Record<string, unknown>; outputs: Record<string, unknown>;
  items: TraceEvidence[]; excluded: TraceEvidence[];
};

export type AgentTrace = {
  schema_version: string; id: string; profile_id: string; created_at: string; elapsed_seconds: number;
  capture_level: "detailed" | "summary"; stages: TraceStage[]; persistence: string;
  corpus_revision?: number; scope?: unknown; query?: string; stop_reason?: string;
  chat_calls?: number; chat_usage?: { model: string; status: string; usage: Record<string, unknown> }[];
  warnings?: string[]; usage_scope?: string; evaluation?: Record<string, unknown>;
};
