// src/domain/files.ts
import type { ObjectAggregate, ObjectSummary } from "../api/types";

export type FileCardModel = {
  fileId: string;
  title: string;
  subtitle: string;
  mime: string | null;
  sourceFileRelpath: string | null;
  synthesisPreview: string | null;
  previewAvailable: boolean;
  hasPreferredText: boolean;
  hasSynthesis: boolean;
  hasEnrichments: boolean;
  supportsMarkdownRender: boolean;
};

export function toFileCardModel(summary: ObjectSummary): FileCardModel {
  return {
    fileId: summary.file_id,
    title: summary.filename ?? summary.file_id,
    subtitle: summary.source_relpath ?? "",
    mime: summary.mime ?? null,
    sourceFileRelpath: summary.source_file_relpath ?? null,
    synthesisPreview: summary.synthesis_preview ?? null,
    previewAvailable: summary.preview_available,
    hasPreferredText: summary.has_preferred_text,
    hasSynthesis: summary.has_synthesis,
    hasEnrichments: summary.has_enrichments,
    supportsMarkdownRender: Boolean(
      summary.processing.capabilities?.supports_markdown_render,
    ),
  };
}

export type FileDetailModel = {
  fileId: string;
  filename: string;
  sourceRelpath: string;
  mime: string | null;
  textCount: number;
  imageCount: number;
  hasSynthesis: boolean;
  collections: Array<{ id: string; name: string; kind: string | null }>;
  supportsMarkdownRender: boolean;
};

export function toFileDetailModel(object: ObjectAggregate): FileDetailModel {
  return {
    fileId: object.file_id,
    filename: object.meta.file.filename,
    sourceRelpath: object.meta.file.source_relpath,
    mime: object.meta.file.mime,
    textCount: object.overview.text_count,
    imageCount: object.overview.image_count,
    hasSynthesis: object.overview.has_synth,
    collections: object.collections.map((collection) => ({
      id: collection.id,
      name: collection.name,
      kind: collection.kind,
    })),
    supportsMarkdownRender: Boolean(
      object.processing.capabilities?.supports_markdown_render,
    ),
  };
}