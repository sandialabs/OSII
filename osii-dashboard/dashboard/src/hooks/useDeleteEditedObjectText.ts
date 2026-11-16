// src/hooks/useDeleteEditedObjectText.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteEditedObjectText } from "../api/editedText";
import type { EditedTextDeleteResponse } from "../api/types";

export function useDeleteEditedObjectText(fileId: string) {
  const queryClient = useQueryClient();

  return useMutation<EditedTextDeleteResponse, Error, { expected_revision?: string | null; expected_state?: string } | undefined>({
    mutationFn: (version) => deleteEditedObjectText(fileId, version),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["workbench-home"] }),
        queryClient.invalidateQueries({ queryKey: ["scopes", "overview"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "edited-text"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "texts"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "summaries"] }),
        queryClient.invalidateQueries({ queryKey: ["scopes", "summaries"] }),
        queryClient.invalidateQueries({ queryKey: ["search"] }),
      ]);
    },
  });
}