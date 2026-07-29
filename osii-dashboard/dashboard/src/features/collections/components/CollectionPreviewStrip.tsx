// src/features/collections/components/CollectionPreviewStrip.tsx
import { Box, Chip, Stack, Typography } from "@mui/material";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";

import type { ObjectSummary } from "../../../api/types";
import { getObjectSourceUrl } from "../../../api/source";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";

type CollectionPreviewStripProps = {
  files: ObjectSummary[];
  totalCount: number;
};

function PreviewThumb({
  file,
}: {
  file: ObjectSummary;
}) {
  const filename = file.filename ?? file.file_id;
  const lower = filename.toLowerCase();
  const isPdf = lower.endsWith(".pdf");
  const sourceUrl = isPdf ? getObjectSourceUrl(file.file_id) : null;
  const { thumbnailUrl } = usePdfThumbnail(sourceUrl, Boolean(sourceUrl));

  if (thumbnailUrl) {
    return (
      <img
        src={thumbnailUrl}
        alt={`${filename} thumbnail`}
        style={{
          width: 56,
          height: 56,
          objectFit: "cover",
          borderRadius: 8,
          border: "1px solid rgba(15,23,42,0.12)",
          display: "block",
          flexShrink: 0,
        }}
      />
    );
  }

  return (
    <Box
      sx={{
        width: 56,
        height: 56,
        borderRadius: 1,
        border: (theme) => `1px solid ${theme.palette.divider}`,
        backgroundColor: "background.paper",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {isPdf ? (
        <PictureAsPdfOutlinedIcon color="error" fontSize="small" />
      ) : (
        <DescriptionOutlinedIcon color="action" fontSize="small" />
      )}
    </Box>
  );
}

export function CollectionPreviewStrip({
  files,
  totalCount,
}: CollectionPreviewStripProps) {
  const remainder = Math.max(totalCount - files.length, 0);

  if (files.length === 0) {
    return (
      <Typography variant="body2" color="text.secondary">
        No files in this collection yet.
      </Typography>
    );
  }

  return (
    <Stack spacing={0.75}>
      <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
        {files.map((file) => (
          <PreviewThumb key={file.file_id} file={file} />
        ))}

        {remainder > 0 ? (
          <Chip label={`+${remainder} more`} size="small" variant="outlined" />
        ) : null}
      </Stack>
    </Stack>
  );
}