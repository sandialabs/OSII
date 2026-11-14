export type CollectionCandidate = {
  file_id: string;
  filename: string;
  source_relpath: string;
};
export function folderGroups(documents: CollectionCandidate[]) {
  const groups = new Map<string, CollectionCandidate[]>();
  for (const doc of documents) {
    const path = doc.source_relpath.replace(/\\/g, "/");
    const folder = path.includes("/")
      ? path.slice(0, path.lastIndexOf("/"))
      : "";
    const group = groups.get(folder) || [];
    group.push(doc);
    groups.set(folder, group);
  }
  return [...groups]
    .sort(([a], [b]) => a.localeCompare(b, undefined, { numeric: true }))
    .map(([path, documents]) => ({ path, label: path || "Root", documents }));
}
export function matchingCandidates(
  documents: CollectionCandidate[],
  query: string,
) {
  const words = query.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
  return documents.filter((doc) =>
    words.every((word) =>
      `${doc.filename} ${doc.source_relpath}`
        .toLocaleLowerCase()
        .includes(word),
    ),
  );
}
