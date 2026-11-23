import type { SavedProduct } from "../api/tools";
import type { EnrichmentListEntry } from "../api/types";

const visible = (name: string) =>
  !name.endsWith(".meta.json") && name.split("/").every(part => !part.startsWith("."));

export function documentProducts(saved: readonly SavedProduct[], enrichments: readonly EnrichmentListEntry[]) {
  const products = new Map<string, SavedProduct & { id: string; relpath?: string; editable: boolean }>();
  for (const entry of enrichments) {
    const files = entry.kind === "file" ? [{ ...entry, filename: entry.name }]
      : entry.files.filter(file => !file.is_dir).map(file => ({ ...file, filename: `${entry.name}/${file.name}`, title: file.name, artifact_type: undefined }));
    for (const file of files) {
      if (!visible(file.filename)) continue;
      const id = `enrichment:${file.filename}`;
      products.set(id, { ...file, id, family: "enrichment", title: file.title || file.filename, editable: /\.(json|txt|md)$/i.test(file.filename) });
    }
  }

  for (const item of saved) {
    if (!visible(item.filename) || (item.family !== "synthesis" && item.family !== "enrichment")) continue;
    const id = `${item.family}:${item.filename}`;
    products.set(id, { ...products.get(id), ...item, id, title: item.title || item.filename, editable: true });
  }
  return [...products.values()];
}
