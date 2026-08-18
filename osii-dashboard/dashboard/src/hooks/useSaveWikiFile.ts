// src/hooks/useSaveWikiFile.ts
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { saveWikiFile } from "../api/wikiFiles";

export function useSaveWikiFile() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: { relpath: string; content: string }) => saveWikiFile(payload),
    onSuccess: async (_data, variables) => {
      await queryClient.invalidateQueries({ queryKey: ["wiki-file", variables.relpath] });
    },
  });
}
