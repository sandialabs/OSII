import type { ChatResponse } from "../../api/types";

export type RagProfile = { id: string; name: string; description: string; retrieval: string; strategy: string; rerank: boolean; candidates: number; evidence: number; rounds: number; available: boolean; unavailable_reason: string | null; coarse_fulltext: boolean };
export type RagProfiles = { profiles: RagProfile[]; chat_model: string; provider: string; can_inspect_trace: boolean };
export type RagComparison = { query: string; scope: unknown; corpus_revision: number; model: string; runs: { profile_id: string; response: ChatResponse }[] };
