import { useMemo } from "react";

import type { EnrichmentListEntryFile, ScopeDescribeRequest } from "../api/types";
import { useScopeEnrichmentPayload } from "./useScopeEnrichmentPayload";
import { useScopeEnrichments } from "./useScopeEnrichments";

export const KEYWORD_SNAPSHOT_FILENAME = "keywords--noun_adjective_ngrams.json";

export function extractKeywordSuggestions(value: unknown, limit = 6): string[] {
  if (!value || typeof value !== "object") return [];
  const artifact = value as Record<string, unknown>;
  if (artifact.artifact_type !== "table" || !Array.isArray(artifact.rows)) return [];
  const seen = new Set<string>();
  const keywords: string[] = [];
  for (const row of artifact.rows) {
    if (!row || typeof row !== "object") continue;
    const keyword = String((row as Record<string, unknown>).keyword ?? "").trim();
    const key = keyword.toLocaleLowerCase();
    if (!keyword || seen.has(key)) continue;
    seen.add(key);
    keywords.push(keyword);
    if (keywords.length >= limit) break;
  }
  return keywords;
}

export function buildQuestionSuggestions(keywords: string[], scope: ScopeDescribeRequest): string[] {
  const scopeLabel = scope.scope_type === "collection"
    ? "this collection"
    : scope.scope_type === "object"
      ? "this file"
      : scope.scope_type === "folder"
        ? "this folder"
        : "this library";
  if (keywords.length === 0) {
    return [
      `What are the main themes in ${scopeLabel}?`,
      "Which sources are most relevant, and why?",
      "What important disagreements or gaps appear in the sources?",
    ];
  }
  const questions = [
    `What does ${scopeLabel} say about ${keywords[0]}?`,
    `Which sources discuss ${keywords[0]}, and what do they say?`,
  ];
  if (keywords.length > 1) {
    questions.push(`How do the documents relate ${keywords[0]} and ${keywords[1]}?`);
  }
  return questions;
}

export function useScopeKeywordSuggestions(scope: ScopeDescribeRequest, enabled = true) {
  const enrichments = useScopeEnrichments(scope, enabled);
  const entry = (enrichments.data?.enrichments ?? []).find(
    (item): item is EnrichmentListEntryFile => item.kind === "file" && item.name === KEYWORD_SNAPSHOT_FILENAME,
  );
  const payload = useScopeEnrichmentPayload(scope, entry?.name ?? "", enabled && Boolean(entry));
  const keywords = useMemo(() => extractKeywordSuggestions(payload.data?.data), [payload.data?.data]);

  return {
    keywords,
    questions: buildQuestionSuggestions(keywords, scope),
    hasSnapshot: Boolean(entry),
    isLoading: enrichments.isLoading || payload.isLoading,
    isError: enrichments.isError || payload.isError,
    artifactCount: (enrichments.data?.enrichments ?? []).filter(
      (item) => item.kind === "file" && !item.name.endsWith(".meta.json"),
    ).length,
  };
}
