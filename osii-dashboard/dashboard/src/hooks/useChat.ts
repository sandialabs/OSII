// src/hooks/useChat.ts
import { useMutation } from "@tanstack/react-query";

import { chat } from "../api/chat";
import type { ChatRequest, ChatResponse } from "../api/types";

export function useChat() {
  return useMutation<ChatResponse, Error, ChatRequest>({
    mutationFn: chat,
  });
}