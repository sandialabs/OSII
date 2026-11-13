import type { ReactNode } from "react";
// src/features/files/components/SplitFileView.tsx
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
    <Box
      sx={{
        display: "grid",
        gridTemplateColumns: {
          xs: "minmax(0, 1fr)",
          lg: "repeat(2, minmax(0, 1fr))",
        },
        gap: { xs: 2, lg: 1.5 },
        alignItems: "start",
      }}
    >
      <FileSourcePanel
        fileId={fileId}
        mime={mime}
        page={page}
        onPageChange={onPageChange}
        compact
        segments={segments}
      />

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
    </Box>
  );
}
