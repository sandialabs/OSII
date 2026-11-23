import { useQuery } from "@tanstack/react-query";
import { Alert, CircularProgress } from "@mui/material";

import { getExtractionText } from "../../../api/objects";
import { useObjectTexts } from "../../../hooks/useObjectTexts";
import { useObjectPreferredText } from "../../../hooks/useObjectPreferredText";
import { FileSourcePanel } from "./FileSourcePanel";
import { GroundedSegmentEditor } from "./GroundedSegmentEditor";
import { SplitFileView } from "./SplitFileView";
import { findBestMatchingSegment } from "../../../domain/textGrounding";
import { ReportPassage } from "../../research/ReportPassage";
import type { DocumentViewMode } from "./DocumentWorkspace";

type ReadingTarget = { page?: number | null; segmentId?: string | null };

export function DocumentReadingPane({
  fileId, mime, versionId, mode, page, segmentId, charStart, charEnd, onPageChange,
  onJumpToSource, onEditingChange, readOnly = false, citedPassage = false,
}: {
  fileId: string;
  mime: string | null;
  versionId?: string;
  mode: DocumentViewMode;
  page: number | null;
  segmentId?: string | null;
  charStart?: number | null;
  charEnd?: number | null;
  onPageChange: (page: number) => void;
  onJumpToSource?: (target: ReadingTarget) => void;
  onEditingChange?: (editing: boolean) => void;
  readOnly?: boolean;
  citedPassage?: boolean;
}) {
  const preferred = useObjectPreferredText(fileId, !versionId && (mode !== "source" || citedPassage));
  const documentText = useObjectTexts(fileId, !versionId && !citedPassage);
  const version = useQuery({
    queryKey: ["objects", fileId, "extractions", versionId, "texts"],
    queryFn: () => getExtractionText(fileId, versionId!),
    enabled: Boolean(versionId),
  });
  const text = versionId ? version.data?.text : preferred.data?.text;
  const segments = (versionId ? version.data?.segments : documentText.data?.segments) ?? [];
  const loading = versionId ? version.isPending : preferred.isPending || documentText.isPending;
  const failed = versionId ? version.isError : preferred.isError || documentText.isError;
  if (citedPassage) return <ReportPassage text={text ?? ""} loading={versionId ? version.isPending : preferred.isPending} />;
  if (mode !== "source" && loading) return <CircularProgress size={24} aria-label="Loading document text" />;
  if (mode !== "source" && failed) return <Alert severity="error">Could not load this text.</Alert>;

  const match = !segmentId && (charStart != null || charEnd != null)
    ? findBestMatchingSegment({ segments, charStart: charStart ?? null, charEnd: charEnd ?? null })
    : null;
  const activeSegmentId = segmentId ?? match?.id ?? null;
  const segmentPage = match?.source_origin?.page;
  const activePage = page ?? (typeof segmentPage === "number" ? segmentPage : 1);

  if (mode === "source") {
    return <FileSourcePanel fileId={fileId} mime={mime} page={activePage} onPageChange={onPageChange} segments={segments} />;
  }

  const props = {
    fileId, segments, canonicalText: text ?? "", activeSegmentId,
    readOnly: readOnly || Boolean(versionId), onEditingChange, onJumpToSource,
  };
  return mode === "text" ? <GroundedSegmentEditor {...props} /> : (
    <SplitFileView {...props} mime={mime} page={activePage} onPageChange={onPageChange} />
  );
}
