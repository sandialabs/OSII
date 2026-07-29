// src/hooks/useCollections.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  addCollectionMembers,
  createCollection,
  deleteCollection,
  getCollection,
  getCollectionMembers,
  listCollections,
  removeCollectionMember,
  updateCollection,
} from "../api/collections";
import type {
  CollectionDetailResponse,
  CollectionEnvelope,
  CollectionListResponse,
  CollectionMemberRemoveResponse,
  CollectionMembersAddResponse,
  CollectionMembersResponse,
  CollectionResource,
} from "../api/types";

export function useCollections(enabled = true) {
  return useQuery<CollectionListResponse>({
    queryKey: ["collections", "list"],
    queryFn: listCollections,
    enabled,
  });
}

export function useCollection(collectionId: string, enabled = true) {
  return useQuery<CollectionDetailResponse>({
    queryKey: ["collections", "detail", collectionId],
    queryFn: () => getCollection(collectionId),
    enabled: enabled && collectionId.trim().length > 0,
  });
}

export function useCollectionMembers(collectionId: string, enabled = true) {
  return useQuery<CollectionMembersResponse>({
    queryKey: ["collections", collectionId, "members"],
    queryFn: () => getCollectionMembers(collectionId),
    enabled: enabled && collectionId.trim().length > 0,
  });
}

export function useCreateCollection() {
  const queryClient = useQueryClient();

  return useMutation<
    CollectionEnvelope,
    Error,
    {
      name: string;
      description?: string | null;
      kind?: string | null;
      color?: string | null;
    }
  >({
    mutationFn: createCollection,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["collections"],
      });
    },
  });
}

export function useUpdateCollection(collectionId: string) {
  const queryClient = useQueryClient();

  return useMutation<
    CollectionEnvelope,
    Error,
    Partial<Pick<CollectionResource, "name" | "description" | "kind" | "color">>
  >({
    mutationFn: (payload) => updateCollection(collectionId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["collections"] }),
        queryClient.invalidateQueries({
          queryKey: ["collections", "detail", collectionId],
        }),
      ]);
    },
  });
}

export function useDeleteCollection() {
  const queryClient = useQueryClient();

  return useMutation<
    { collection_id: string; deleted: boolean },
    Error,
    string
  >({
    mutationFn: deleteCollection,
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: ["collections"],
      });
    },
  });
}

export function useAddCollectionMembers(collectionId: string) {
  const queryClient = useQueryClient();

  return useMutation<
    CollectionMembersAddResponse,
    Error,
    { file_ids: string[] }
  >({
    mutationFn: (payload) => addCollectionMembers(collectionId, payload),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["collections"] }),
        queryClient.invalidateQueries({
          queryKey: ["collections", collectionId, "members"],
        }),
      ]);
    },
  });
}

export function useRemoveCollectionMember(collectionId: string) {
  const queryClient = useQueryClient();

  return useMutation<
    CollectionMemberRemoveResponse,
    Error,
    string
  >({
    mutationFn: (fileId) => removeCollectionMember(collectionId, fileId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["collections"] }),
        queryClient.invalidateQueries({
          queryKey: ["collections", collectionId, "members"],
        }),
      ]);
    },
  });
}