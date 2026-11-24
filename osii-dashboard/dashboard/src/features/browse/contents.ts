export function normalizeFolderPath(path: string): string {
  return path.replace(/\\/g, "/").split("/").filter(part => part && part !== ".").join("/");
}

export function folderLabel(path: string): string {
  if (!path) return "Library";
  if (path === "external") return "Other locations";
  return path.slice(path.lastIndexOf("/") + 1);
}

export function folderBreadcrumbs(path: string) {
  const parts = normalizeFolderPath(path).split("/").filter(Boolean);
  return ["", ...parts.map((_, index) => parts.slice(0, index + 1).join("/"))]
    .map(path => ({ path, label: folderLabel(path) }));
}
