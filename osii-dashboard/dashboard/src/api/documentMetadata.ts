export type MetadataSuggestion = { value?: string | null; qualifier?: string | null; evidence?: string | null };
export type DocumentMetadata = { schema_version: 1; method: string; model?: string | null; descriptive_title?: MetadataSuggestion; agency?: MetadataSuggestion; document_type?: MetadataSuggestion; title: MetadataSuggestion; author: MetadataSuggestion; date: MetadataSuggestion };
