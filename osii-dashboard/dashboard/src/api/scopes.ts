// src/api/scopes.ts
import { apiJson } from "./client";
import type {
  CollectionScopeListResponse,
  FolderScopeListResponse,
  ScopeArtifactsRequest,
  ScopeArtifactsResponse,
  ScopeDescribeRequest,
  ScopeMembersResponse,
  ScopeSummariesRequest,
  ScopeSummariesResponse,
} from "./types";

export async function getRootScope(): Promise<ScopeMembersResponse> {
  return apiJson<ScopeMembersResponse>("/api/scopes/root");
}

export async function listFolderScopes(): Promise<FolderScopeListResponse> {
  return apiJson<FolderScopeListResponse>("/api/scopes/folders");
}

export async function listCollectionScopes(): Promise<CollectionScopeListResponse> {
  return apiJson<CollectionScopeListResponse>("/api/scopes/collections");
}

export async function describeScope(
  scope: ScopeDescribeRequest,
): Promise<ScopeMembersResponse> {
  return apiJson<ScopeMembersResponse>("/api/scopes/describe", {
    method: "POST",
    json: scope,
  });
}

export async function getScopeSummaries(
  request: ScopeSummariesRequest,
): Promise<ScopeSummariesResponse> {
  return apiJson<ScopeSummariesResponse>("/api/scopes/summaries", {
    method: "POST",
    json: request,
  });
}

export async function getScopeArtifacts(
  request: ScopeArtifactsRequest,
): Promise<ScopeArtifactsResponse> {
  return apiJson<ScopeArtifactsResponse>("/api/scopes/artifacts", {
    method: "POST",
    json: request,
  });
}