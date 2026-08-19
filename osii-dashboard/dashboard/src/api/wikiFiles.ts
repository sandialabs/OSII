// src/api/wikiFiles.ts
import { apiJson, buildArtifactUrl } from "./client";

export async function fetchWikiFile(relpath: string): Promise<string> {
  // Revalidate rather than serve from cache: pages change on save and on
  // regeneration, and a stale copy looks like the write silently failed.
  const response = await fetch(buildArtifactUrl(relpath), { cache: "no-cache" });

  if (!response.ok) {
    throw new Error(`Could not load ${relpath} (status ${response.status})`);
  }

  return response.text();
}

export async function saveWikiFile(params: {
  relpath: string;
  content: string;
}): Promise<{ relpath: string; bytes_written: number; updated_utc: string }> {
  return apiJson("/api/enrichments/bundle-file", {
    method: "PUT",
    json: params,
  });
}
