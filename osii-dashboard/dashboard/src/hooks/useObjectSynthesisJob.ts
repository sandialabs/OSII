// src/hooks/useObjectSynthesisJob.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { runObjectSynthesis, type ObjectSynthesisRequest } from "../api/jobs";

export function useObjectSynthesisJob(fileId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: ObjectSynthesisRequest) =>
      runObjectSynthesis(fileId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "syntheses"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "summaries"] }),
        queryClient.invalidateQueries({ queryKey: ["scopes", "summaries"] }),
      ]);
    },
  });
}