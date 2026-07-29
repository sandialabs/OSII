// src/api/enrichments.ts
import { apiJson } from "./client";
import type {
  EnrichmentsListResponse,
  ObjectEnrichmentPayloadResponse,
  ScopeDescribeRequest,
} from "./types";

export async function listEnrichments(
  scope: ScopeDescribeRequest,
): Promise<EnrichmentsListResponse> {
  return apiJson<EnrichmentsListResponse>("/api/enrichments/list", {
    method: "POST",
    json: scope,
  });
}

export async function getObjectEnrichmentPayload(params: {
  fileId: string;
  filename: string;
}): Promise<ObjectEnrichmentPayloadResponse> {
  return apiJson<ObjectEnrichmentPayloadResponse>(
    `/api/enrichments/objects/${encodeURIComponent(params.fileId)}/${encodeURIComponent(params.filename)}`,
  );
}

export async function getScopeEnrichmentPayload(params: {
  scope: ScopeDescribeRequest;
  filename: string;
}): Promise<ObjectEnrichmentPayloadResponse> {
  return apiJson<ObjectEnrichmentPayloadResponse>("/api/enrichments/payload", {
    method: "POST",
    json: params,
  });
}
