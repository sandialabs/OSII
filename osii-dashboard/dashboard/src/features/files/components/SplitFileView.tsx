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
          xs: "1fr",
          xl: "minmax(0, 0.95fr) minmax(340px, 0.8fr)",
        },
        gap: 1.25,
        alignItems: "start",
      }}
    >
      <FileSourcePanel
        fileId={fileId}
        mime={mime}
        page={page}
        onPageChange={onPageChange}
        compact
      />

      <GroundedSegmentEditor
        fileId={fileId}
        segments={segments}
        canonicalText={canonicalText}
        activeSegmentId={activeSegmentId}
        onJumpToSource={onJumpToSource}
        height="68vh"
        fontSizePx={15}
      />
    </Box>
  );
}