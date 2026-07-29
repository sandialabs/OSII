// src/domain/scopes.ts
import type {
  FolderScopeDescriptor,
  ScopeDescribeRequest,
} from "../api/types";

export type BrowsingScope =
  | { kind: "root"; request: { scope_type: "root" } }
  | { kind: "folder"; request: { scope_type: "folder"; folder_id: string }; folder: FolderScopeDescriptor }
  | { kind: "collection"; request: { scope_type: "collection"; collection_id: string }; collectionId: string; label?: string };

export type FolderTreeNode = FolderScopeDescriptor & {
  children: FolderTreeNode[];
};

export function toScopeRequest(scope: BrowsingScope): ScopeDescribeRequest {
  return scope.request;
}

export function buildFolderTree(scopes: FolderScopeDescriptor[]): FolderTreeNode[] {
  const byId = new Map<string, FolderTreeNode>();
  const roots: FolderTreeNode[] = [];

  const sorted = [...scopes].sort((a, b) => a.path.localeCompare(b.path));

  for (const scope of sorted) {
    byId.set(scope.folder_id, {
      ...scope,
      children: [],
    });
  }

  for (const scope of sorted) {
    const node = byId.get(scope.folder_id);
    if (!node) continue;

    if (!scope.path) {
      roots.push(node);
      continue;
    }

    const parentPath = scope.path.split("/").slice(0, -1).join("/");
    const parent = sorted.find((candidate) => candidate.path === parentPath);

    if (parent) {
      const parentNode = byId.get(parent.folder_id);
      if (parentNode) {
        parentNode.children.push(node);
        continue;
      }
    }

    roots.push(node);
  }

  return roots;
}