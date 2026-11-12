// src/api/chat.ts
import { apiJson } from "./client";
import type { ChatRequest, ChatResponse } from "./types";
import type { RagComparison, RagProfiles } from "../features/chat/types";

export async function chat(payload: ChatRequest): Promise<ChatResponse> {
  return apiJson<ChatResponse>("/api/chat", {
    method: "POST",
    json: payload,
  });
}

export function getRagProfiles(): Promise<RagProfiles> {
  return apiJson<RagProfiles>("/api/chat/profiles");
}

export function compareRag(payload: ChatRequest & { profile_ids: string[] }): Promise<RagComparison> {
  return apiJson<RagComparison>("/api/chat/compare", { method: "POST", json: payload });
}
