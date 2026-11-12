// src/domain/textGrounding.ts
import type { ManifestRecord } from "../api/types";

export function findBestMatchingSegment(params: {
  segments: ManifestRecord[];
  charStart: number | null;
  charEnd: number | null;
}): ManifestRecord | null {
  const { segments, charStart, charEnd } = params;

  if (charStart == null || charEnd == null) {
    return null;
  }

  const textSegments = segments.filter(
    (segment) =>
      segment.kind === "text" &&
      typeof segment.span?.char_start === "number" &&
      typeof segment.span?.char_end === "number",
  );

  const containing = textSegments.find((segment) => {
    const start = segment.span!.char_start;
    const end = segment.span!.char_end;
    return charStart >= start && charEnd <= end;
  });

  if (containing) {
    return containing;
  }

  const overlapping = textSegments.find((segment) => {
    const start = segment.span!.char_start;
    const end = segment.span!.char_end;
    return charStart < end && charEnd > start;
  });

  return overlapping ?? null;
}
/** Optional source geometry stays independent of offsets in derived text. */
export function pageBoundingRegions(segments: ManifestRecord[], page: number): Array<{ bbox: [number, number, number, number]; text: string | null; confidence: number | null }> {
  return segments.filter(segment => segment.source_origin?.page === page).flatMap(segment => {
    const origin = segment.source_origin ?? {};
    const entries = Array.isArray(segment.regions) ? segment.regions : Array.isArray(origin.regions) ? origin.regions : Array.isArray(origin.bbox) ? [{ ...origin, text: segment.text }] : [];
    return entries.flatMap(value => {
      if (!value || typeof value !== "object") return [];
      const region = value as Record<string, unknown>;
      if (!Array.isArray(region.bbox) || region.bbox.length !== 4 || !region.bbox.every(c => typeof c === "number" && Number.isFinite(c))) return [];
      const coordinates = [...region.bbox] as number[];
      const space = region.coordinate_space ?? origin.coordinate_space;
      if (space === "page-pixels") {
        const width = region.page_width ?? origin.page_width, height = region.page_height ?? origin.page_height;
        if (typeof width !== "number" || width <= 0 || typeof height !== "number" || height <= 0) return [];
        coordinates[0] /= width; coordinates[2] /= width; coordinates[1] /= height; coordinates[3] /= height;
      } else if (space != null && space !== "normalized-page") return [];
      if (coordinates.some(c => c < 0 || c > 1) || coordinates[2] <= coordinates[0] || coordinates[3] <= coordinates[1]) return [];
      const confidence = region.confidence;
      return [{ bbox: coordinates as [number, number, number, number], text: typeof region.text === "string" ? region.text : null,
        confidence: typeof confidence === "number" && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1 ? confidence : null }];
    });
  });
}
