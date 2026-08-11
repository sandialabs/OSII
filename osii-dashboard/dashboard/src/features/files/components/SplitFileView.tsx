// src/features/files/components/SplitFileView.tsx
import { Box } from "@mui/material";

import type { ManifestRecord } from "../../../api/types";
import { FileSourcePanel } from "./FileSourcePanel";
import { GroundedSegmentEditor } from "./GroundedSegmentEditor";

type SplitFileViewProps = {
  fileId: string;
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
