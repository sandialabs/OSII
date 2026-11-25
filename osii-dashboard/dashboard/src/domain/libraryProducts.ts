export const libraryProducts = {
  source: "Original files",
  text: "Extracted text",
  metadata: "Metadata",
  summaries: "Summaries",
  artifacts: "Saved artifacts",
  index: "Search index & embeddings",
  collections: "Collections",
  runs: "Run history",
} as const;

export type LibraryProduct = keyof typeof libraryProducts;
export type LibraryFlow = {
  reads: readonly LibraryProduct[];
  writes: readonly LibraryProduct[];
};
