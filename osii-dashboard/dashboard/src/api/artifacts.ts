// src/api/artifacts.ts
import { buildArtifactUrl } from "./client";

export function getArtifactUrl(relpath: string): string {
  return buildArtifactUrl(relpath);
}