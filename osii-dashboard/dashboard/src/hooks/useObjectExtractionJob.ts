import { useMutation, useQueryClient } from "@tanstack/react-query";

import { queueObjectExtraction } from "../api/objects";
import { createProcessingRun } from "../api/queue";
import { sourceExtension } from "../domain/fileCompatibility";

export function useObjectExtractionJob(fileId: string, source?: { path: string; name: string }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: {
      extractor_name: string;
      extraction_policy: "make_primary" | "save_variant";
    }) => source ? createProcessingRun({
      queue_paths: [source.path],
      include_subfolders: false,
      workflow: "library",
      run_extraction: true,
      extract_mode: "reprocess",
      extraction_policy: payload.extraction_policy,
      extractor_overrides: { [sourceExtension(source.name) ?? "(no extension)"]: payload.extractor_name },
      build_embeddings: false,
    }) : queueObjectExtraction(fileId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["processing-runs"], exact: true });
    },
  });
}
