import type { FolderScopeDescriptor, ObjectSummary } from "../../api/types";
import type { FileCardModel } from "../../domain/files";

export type BrowseSort = "name-asc" | "name-desc" | "modified-desc" | "size-desc";

export function normalizeFolderPath(path: string): string {
  return path.replace(/\\/g, "/").split("/").filter((part) => part && part !== ".").join("/");
}

export function folderName(folder: FolderScopeDescriptor): string {
  return normalizeFolderPath(folder.path).split("/").pop() || "Root";
}

export function compareNames(left: string, right: string): number {
  return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
}

export function immediateFolders(scopes: FolderScopeDescriptor[], parent: FolderScopeDescriptor): FolderScopeDescriptor[] {
  const path = normalizeFolderPath(parent.path);
  return scopes.filter((folder) => {
    const candidate = normalizeFolderPath(folder.path);
    return candidate !== path && candidate.split("/").slice(0, -1).join("/") === path;
  }).sort((a, b) => compareNames(folderName(a), folderName(b)));
}

export function immediateFiles(summaries: ObjectSummary[], folderPath: string): ObjectSummary[] {
  const path = normalizeFolderPath(folderPath);
  return summaries.filter((file) => {
    const source = normalizeFolderPath(file.source_file_relpath || file.source_relpath || "");
    const parent = source.split("/").slice(0, -1).join("/");
    if (parent === path) return true;
    const [namespace, ...relative] = source.split("/");
    if (!["source", "my_data", "uploaded_data"].includes(namespace)) return false;
    return relative.slice(0, -1).join("/") === path;
  });
}

export function compareBrowseFiles(left: FileCardModel, right: FileCardModel, sort: BrowseSort): number {
  const nameOrder = compareNames(left.title, right.title) || compareNames(left.fileId, right.fileId);
  if (sort === "name-asc") return nameOrder;
  if (sort === "name-desc") return -nameOrder;
  const value = (file: FileCardModel) => sort === "size-desc"
    ? file.sizeBytes
    : file.modifiedAt ? Date.parse(file.modifiedAt) : null;
  const a = value(left);
  const b = value(right);
  const validA = a != null && Number.isFinite(a) && a >= 0;
  const validB = b != null && Number.isFinite(b) && b >= 0;
  if (!validA) return validB ? 1 : nameOrder;
  if (!validB) return -1;
  return b - a || nameOrder;
}
