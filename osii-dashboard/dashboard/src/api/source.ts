// src/api/source.ts
export function getObjectSourceUrl(fileId: string): string {
  return `/api/objects/${encodeURIComponent(fileId)}/source`;
}