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