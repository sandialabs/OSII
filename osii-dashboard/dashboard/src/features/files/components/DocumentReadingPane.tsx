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
  onJumpToSource, onEditingChange, editable = false, showEdits = false, citedPassage = false,
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
  editable?: boolean;
  showEdits?: boolean;
  citedPassage?: boolean;
}) {
  const preferred = useObjectPreferredText(fileId, !versionId && citedPassage);
  const documentText = useObjectTexts(fileId, !versionId && mode === "source");
  const extraction = versionId ?? "canonical";
  const version = useQuery({
    queryKey: ["objects", fileId, "extractions", extraction, "texts"],
    queryFn: () => getExtractionText(fileId, extraction),
    enabled: Boolean(versionId) || (!citedPassage && mode !== "source"),
  });
  const text = citedPassage && !versionId ? preferred.data?.text : version.data?.text;
  const segments = version.data?.segments ?? documentText.data?.segments ?? [];
  if (citedPassage) return <ReportPassage text={text ?? ""} loading={versionId ? version.isPending : preferred.isPending} />;
  if (mode !== "source" && version.isPending) return <CircularProgress size={24} aria-label="Loading document text" />;
  if (mode !== "source" && version.isError) return <Alert severity="error">Could not load this text.</Alert>;

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
    readOnly: !editable, showEdits, expectedExtractionId: versionId, onEditingChange, onJumpToSource,
  };
  return mode === "text" ? <GroundedSegmentEditor {...props} /> : (
    <SplitFileView {...props} mime={mime} page={activePage} onPageChange={onPageChange} />
  );
}
