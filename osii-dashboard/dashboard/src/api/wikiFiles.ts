// src/api/wikiFiles.ts
import { apiJson, buildArtifactUrl } from "./client";

export async function fetchWikiFile(relpath: string): Promise<string> {
  const response = await fetch(buildArtifactUrl(relpath));

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
