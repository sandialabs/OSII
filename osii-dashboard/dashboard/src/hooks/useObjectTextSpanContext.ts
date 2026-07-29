// src/hooks/useObjectTextSpanContext.ts
import { useQuery } from "@tanstack/react-query";

import { getObjectTextSpanContext } from "../api/objects";
import type { CanonicalSpanContextResponse } from "../api/types";

export function useObjectTextSpanContext(
  params: {
    fileId: string;
    charStart?: number | null;
    charEnd?: number | null;
    contextChars?: number;
  },
  enabled = true,
) {
  return useQuery<CanonicalSpanContextResponse>({
    queryKey: [
      "objects",
      params.fileId,
      "span-context",
      params.charStart ?? null,
      params.charEnd ?? null,
      params.contextChars ?? 180,
    ],
    queryFn: () =>
      getObjectTextSpanContext({
        fileId: params.fileId,
        charStart: params.charStart as number,
        charEnd: params.charEnd as number,
        contextChars: params.contextChars,
      }),
    enabled:
      enabled &&
      params.fileId.trim().length > 0 &&
      params.charStart != null &&
      params.charEnd != null,
  });
}