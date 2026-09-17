import { useMutation, useQueryClient } from "@tanstack/react-query";

import { queueObjectExtraction } from "../api/objects";

export function useObjectExtractionJob(fileId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      extractor_name: string;
      extraction_policy: "make_primary" | "save_variant";
    }) => queueObjectExtraction(fileId, payload),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
    },
  });
}
