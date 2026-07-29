// src/domain/browse.ts
import type { FolderScopeDescriptor, ObjectSummary } from "../api/types";

export type FolderTreeNode = FolderScopeDescriptor & {
  children: FolderTreeNode[];
};

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

export function getRootFolder(scopes: FolderScopeDescriptor[]): FolderScopeDescriptor | null {
  return scopes.find((scope) => scope.path === "") ?? scopes[0] ?? null;
}

export function getFolderById(
  scopes: FolderScopeDescriptor[],
  folderId: string,
): FolderScopeDescriptor | null {
  return scopes.find((scope) => scope.folder_id === folderId) ?? null;
}

export function getImmediateChildFolders(
  scopes: FolderScopeDescriptor[],
  parentFolderId: string,
): FolderScopeDescriptor[] {
  const parent = getFolderById(scopes, parentFolderId);
  if (!parent) return [];

  const parentPath = parent.path;
  const parentDepth = parentPath ? parentPath.split("/").length : 0;

  return scopes
    .filter((scope) => {
      if (scope.folder_id === parentFolderId) return false;

      const scopePath = scope.path;
      const scopeDepth = scopePath ? scopePath.split("/").length : 0;

      if (parentPath === "") {
        return scopeDepth === 1;
      }

      return (
        scopePath.startsWith(`${parentPath}/`) &&
        scopeDepth === parentDepth + 1
      );
    })
    .sort((a, b) => a.label.localeCompare(b.label));
}

export function getFolderBreadcrumbs(
  scopes: FolderScopeDescriptor[],
  folderId: string,
): FolderScopeDescriptor[] {
  const current = getFolderById(scopes, folderId);
  if (!current) return [];

  if (!current.path) {
    return [current];
  }

  const parts = current.path.split("/");
  const breadcrumbs: FolderScopeDescriptor[] = [];

  for (let index = 0; index <= parts.length; index += 1) {
    const partialPath = parts.slice(0, index).join("/");
    const match = scopes.find((scope) => scope.path === partialPath);
    if (match) {
      breadcrumbs.push(match);
    }
  }

  return breadcrumbs;
}

export type BrowseFolderItem = {
  kind: "folder";
  folder: FolderScopeDescriptor;
};

export type BrowseFileItem = {
  kind: "file";
  file: ObjectSummary;
};

export type BrowseItem = BrowseFolderItem | BrowseFileItem;