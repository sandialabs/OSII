// src/api/chat.ts
import { apiJson } from "./client";
import type { ChatRequest, ChatResponse } from "./types";
import type { RagComparison, RagProfiles } from "../features/chat/types";

export const getRagProfiles = () => apiJson<RagProfiles>("/api/chat/profiles");
export const compareRag = (payload: ChatRequest & { profile_ids: string[] }) =>
  apiJson<RagComparison>("/api/chat/compare", { method: "POST", json: payload });

export async function chat(payload: ChatRequest): Promise<ChatResponse> {
  return apiJson<ChatResponse>("/api/chat", {
    method: "POST",
    json: payload,
  });
}
