import { useRef, useState, useId, type ReactNode } from "react";
import { Box } from "@mui/material";

import type { ManifestRecord } from "../../../api/types";
import { FileSourcePanel } from "./FileSourcePanel";
import { GroundedSegmentEditor } from "./GroundedSegmentEditor";

type SplitFileViewProps = {
  fileId: string;
  readOnly?: boolean;
  textControls?: ReactNode;
  expectedExtractionId?: string;
  showEdits?: boolean;
  onEditingChange?: (editing: boolean) => void;
  mime: string | null;
  canonicalText: string;
  segments: ManifestRecord[];
  activeSegmentId?: string | null;
  page?: number | null;
  onPageChange?: (page: number) => void;
  onJumpToSource?: (params: { page?: number | null; segmentId?: string | null }) => void;
};

export function SplitFileView({
  fileId,
  readOnly = false,
  textControls,
  expectedExtractionId,
  showEdits = false,
  onEditingChange,
  mime,
  canonicalText,
  segments,
  activeSegmentId = null,
  page = null,
  onPageChange,
  onJumpToSource,
}: SplitFileViewProps) {
  return (
    <DocumentSplitPane source={<FileSourcePanel fileId={fileId} mime={mime} page={page}
      onPageChange={onPageChange} compact segments={segments} />}>
      <GroundedSegmentEditor
        readOnly={readOnly}
        controls={textControls}
        expectedExtractionId={expectedExtractionId}
        showEdits={showEdits}
        onEditingChange={onEditingChange}
        fileId={fileId}
        segments={segments}
        canonicalText={canonicalText}
        activeSegmentId={activeSegmentId}
        onJumpToSource={onJumpToSource}
        height="68vh"
        fontSizePx={15}
        compact
      />
    </DocumentSplitPane>
  );
}

export function DocumentSplitPane({ source, children }: { source: ReactNode; children: ReactNode }) {
  const container = useRef<HTMLDivElement>(null);
  const sourceId = useId(), textId = useId();
  const [percent, setPercent] = useState(() => { try { const value = Number(localStorage.getItem("osii.document.split") || 50); return Number.isFinite(value) ? Math.max(25, Math.min(75, value)) : 50; } catch { return 50; } });
  const resize = (value: number) => { const next = Math.max(25, Math.min(75, value)); setPercent(next); try { localStorage.setItem("osii.document.split", String(next)); } catch { /* Optional preference. */ } };
  return (
    <Box ref={container}
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          lg: `minmax(0, ${percent}fr) 12px minmax(0, ${100-percent}fr)`,
        },
        gap: { xs: 2, lg: 0 },
        alignItems: "start",
      }}
    >
      <Box id={sourceId} sx={{ minWidth: 0 }}>{source}</Box>
      <Box role="separator" aria-label="Resize document panes" aria-orientation="vertical" aria-valuemin={25} aria-valuemax={75} aria-valuenow={Math.round(percent)} aria-controls={`${sourceId} ${textId}`} tabIndex={0}
        onPointerDown={event => event.currentTarget.setPointerCapture(event.pointerId)}
        onPointerMove={event => { if (event.currentTarget.hasPointerCapture(event.pointerId) && container.current) { const rect = container.current.getBoundingClientRect(); resize((event.clientX - rect.left) / rect.width * 100); } }}
        onPointerUp={event => { if(event.currentTarget.hasPointerCapture(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
        onDoubleClick={() => resize(50)}
        onKeyDown={event => { const value = event.key === "ArrowLeft" ? percent-5 : event.key === "ArrowRight" ? percent+5 : event.key === "Home" ? 25 : event.key === "End" ? 75 : null; if(value !== null) { event.preventDefault(); resize(value); } }}
        sx={{ display: { xs: "none", lg: "block" }, cursor: "col-resize", touchAction: "none", mx: "4px", bgcolor: "divider", borderRadius: 2, minHeight: "68vh", "&:hover, &:focus-visible": { bgcolor: "secondary.main", outline: "2px solid", outlineColor: "secondary.main" } }} />
      <Box id={textId} sx={{ minWidth: 0 }}>{children}</Box>
    </Box>
  );
}
