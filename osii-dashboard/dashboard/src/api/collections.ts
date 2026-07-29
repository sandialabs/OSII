// src/api/collections.ts
import { apiJson } from "./client";
import type {
  CollectionDetailResponse,
  CollectionEnvelope,
  CollectionListResponse,
  CollectionMemberRemoveResponse,
  CollectionMembersAddRequest,
  CollectionMembersAddResponse,
  CollectionMembersResponse,
  CollectionResource,
  CollectionSynthesesResponse,
} from "./types";

export async function listCollections(): Promise<CollectionListResponse> {
  return apiJson<CollectionListResponse>("/api/collections");
}

export async function createCollection(payload: {
  name: string;
  description?: string | null;
  kind?: string | null;
  color?: string | null;
}): Promise<CollectionEnvelope> {
  return apiJson<CollectionEnvelope>("/api/collections", {
    method: "POST",
    json: payload,
  });
}

export async function getCollection(
  collectionId: string,
): Promise<CollectionDetailResponse> {
  return apiJson<CollectionDetailResponse>(
    `/api/collections/${encodeURIComponent(collectionId)}`,
  );
}

export async function updateCollection(
  collectionId: string,
  payload: Partial<Pick<CollectionResource, "name" | "description" | "kind" | "color">>,
): Promise<CollectionEnvelope> {
  return apiJson<CollectionEnvelope>(
    `/api/collections/${encodeURIComponent(collectionId)}`,
    {
      method: "PATCH",
      json: payload as Record<string, unknown>,
    },
  );
}

export async function deleteCollection(collectionId: string): Promise<{
  collection_id: string;
  deleted: boolean;
}> {
  return apiJson<{ collection_id: string; deleted: boolean }>(
    `/api/collections/${encodeURIComponent(collectionId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function getCollectionMembers(
  collectionId: string,
): Promise<CollectionMembersResponse> {
  return apiJson<CollectionMembersResponse>(
    `/api/collections/${encodeURIComponent(collectionId)}/members`,
  );
}

export async function addCollectionMembers(
  collectionId: string,
  payload: CollectionMembersAddRequest,
): Promise<CollectionMembersAddResponse> {
  return apiJson<CollectionMembersAddResponse>(
    `/api/collections/${encodeURIComponent(collectionId)}/members`,
    {
      method: "POST",
      json: payload,
    },
  );
}

export async function removeCollectionMember(
  collectionId: string,
  fileId: string,
): Promise<CollectionMemberRemoveResponse> {
  return apiJson<CollectionMemberRemoveResponse>(
    `/api/collections/${encodeURIComponent(collectionId)}/members/${encodeURIComponent(fileId)}`,
    {
      method: "DELETE",
    },
  );
}

export async function getCollectionSyntheses(
  collectionId: string,
): Promise<CollectionSynthesesResponse> {
  return apiJson<CollectionSynthesesResponse>(
    `/api/collections/${encodeURIComponent(collectionId)}/syntheses`,
  );
}