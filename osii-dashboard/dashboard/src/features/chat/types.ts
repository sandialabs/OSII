import type { ChatResponse } from "../../api/types";

export type RagProfile = { id: string; name: string; description: string; available: boolean; unavailable_reason: string | null; retrieval: string; strategy: string; rerank: boolean; candidates: number; evidence: number; rounds: number };
export type RagProfiles = { profiles: RagProfile[]; chat_model: string; provider: string };
export type RagTrace = {
  profile_id: string; corpus_check: string; consistency: string; profile: Omit<RagProfile, "available" | "unavailable_reason">;
  result: { stop_reason: string; elapsed_seconds: number; model_calls: number; retrieval_calls: number; steps: { query: string; action: string; added_ids: string[]; model: string; usage: Record<string, unknown> }[]; evidence: { id: string; text: string; file_id: string; source_relpath: string; representation: string; char_start: number | null; char_end: number | null }[] };
  retrieval: { query: string; candidate_ids: string[]; selected_ids: string[]; reranker_called: boolean; ranking: { evidence_id: string; score: number }[] }[];
  actual_retrieval_modes: string[]; chat_calls: number; reranker_calls: number; chat_usage: { model: string; usage: Record<string, unknown> }[]; usage_scope: string; warnings: string[];
};
export type RagComparison = { query: string; scope: unknown; corpus_check: string; model: string; runs: { profile_id: string; status: "ok" | "error"; response: ChatResponse | null; error: string | null }[] };
