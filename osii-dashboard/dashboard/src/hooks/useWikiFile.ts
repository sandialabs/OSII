// src/hooks/useWikiFile.ts
import { useQuery } from "@tanstack/react-query";

import { fetchWikiFile } from "../api/wikiFiles";

export function useWikiFile(relpath: string | null) {
  return useQuery<string>({
    queryKey: ["wiki-file", relpath],
    queryFn: () => fetchWikiFile(relpath as string),
    enabled: Boolean(relpath),
  });
}
