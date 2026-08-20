// src/api/chat.ts
import { apiJson } from "./client";
import type { ChatRequest, ChatResponse } from "./types";

export async function chat(payload: ChatRequest): Promise<ChatResponse> {
  return apiJson<ChatResponse>("/api/chat", {
    method: "POST",
    json: payload,
  });
}
