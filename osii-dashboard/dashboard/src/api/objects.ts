// src/api/objects.ts
import { apiJson } from "./client";
import type {
  CanonicalSpanContextResponse,
  CanonicalSpanResponse,
  ObjectAggregate,
  ObjectManifestResponse,
  ObjectSummariesRequest,
  ObjectSummariesResponse,
  ObjectSynthesesResponse,
  ObjectTextsResponse,
  PreferredTextResponse,
} from "./types";

export async function getObject(fileId: string): Promise<ObjectAggregate> {
  return apiJson<ObjectAggregate>(`/api/objects/${encodeURIComponent(fileId)}`);
}

export async function getObjectSummaries(
  request: ObjectSummariesRequest,
): Promise<ObjectSummariesResponse> {
  return apiJson<ObjectSummariesResponse>("/api/objects/summaries", {
    method: "POST",
    json: request,
  });
}

export async function getObjectManifest(
  fileId: string,
): Promise<ObjectManifestResponse> {
  return apiJson<ObjectManifestResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/manifest`,
  );
}

export async function getObjectTexts(fileId: string): Promise<ObjectTextsResponse> {
  return apiJson<ObjectTextsResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/texts`,
  );
}

export async function getPreferredObjectText(
  fileId: string,
): Promise<PreferredTextResponse> {
  return apiJson<PreferredTextResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/texts/preferred`,
  );
}

export async function getObjectSyntheses(
  fileId: string,
): Promise<ObjectSynthesesResponse> {
  return apiJson<ObjectSynthesesResponse>(
    `/api/objects/${encodeURIComponent(fileId)}/syntheses`,
  );
}

export async function getObjectTextSpan(params: {
  fileId: string;
  charStart: number;
  charEnd: number;
}): Promise<CanonicalSpanResponse> {
  const search = new URLSearchParams({
    char_start: String(params.charStart),
    char_end: String(params.charEnd),
  });

  return apiJson<CanonicalSpanResponse>(
    `/api/text/objects/${encodeURIComponent(params.fileId)}/span?${search.toString()}`,
  );
}

export async function getObjectTextSpanContext(params: {
  fileId: string;
  charStart: number;
  charEnd: number;
  contextChars?: number;
}): Promise<CanonicalSpanContextResponse> {
  const search = new URLSearchParams({
    char_start: String(params.charStart),
    char_end: String(params.charEnd),
  });

  if (params.contextChars !== undefined) {
    search.set("context_chars", String(params.contextChars));
  }

  return apiJson<CanonicalSpanContextResponse>(
    `/api/text/objects/${encodeURIComponent(params.fileId)}/span/context?${search.toString()}`,
  );
}