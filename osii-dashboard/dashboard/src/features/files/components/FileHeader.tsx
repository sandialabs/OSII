// src/features/files/components/FileHeader.tsx
import { Chip, Stack, Typography } from "@mui/material";

import type { FileDetailModel } from "../../../domain/files";

type FileHeaderProps = {
  file: FileDetailModel;
};

export function FileHeader({ file }: FileHeaderProps) {
  return (
    <Stack spacing={1}>
      <Stack spacing={0.25}>
        <Typography variant="h5" fontWeight={700}>
          {file.filename}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {file.sourceRelpath}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {file.mime ? <Chip label={file.mime} size="small" variant="outlined" /> : null}
        <Chip label={`${file.textCount} text items`} size="small" variant="outlined" />
        <Chip label={`${file.imageCount} image items`} size="small" variant="outlined" />
        {file.hasSynthesis ? <Chip label="Has synthesis" size="small" /> : null}
        {file.supportsMarkdownRender ? (
          <Chip label="Markdown-capable" size="small" variant="outlined" />
        ) : null}
        {file.sensitivityLabels.map((label) => (
          <Chip key={`sensitivity-${label}`} label={label} size="small" color="warning" />
        ))}
        {file.tags.map((tag) => (
          <Chip key={`tag-${tag}`} label={tag} size="small" variant="outlined" />
        ))}
      </Stack>
    </Stack>
  );
}
