import { useQuery } from "@tanstack/react-query";
import { apiJson } from "../../../api/client";
import type { DocumentMetadata } from "../../../api/documentMetadata";
// src/features/files/components/FileHeader.tsx
import { Chip, Stack, Typography } from "@mui/material";

import type { FileDetailModel } from "../../../domain/files";

type FileHeaderProps = {
  file: FileDetailModel;
};

export function FileHeader({ file }: FileHeaderProps) {
  const metadata = useQuery({ queryKey: ["objects", file.fileId, "metadata"], queryFn: () => apiJson<{ document_metadata?: DocumentMetadata | null }>(`/api/objects/${encodeURIComponent(file.fileId)}/metadata`) });
  const record = metadata.data?.document_metadata;
  const title = record?.descriptive_title?.value || record?.title?.value;
  return (
    <Stack spacing={1}>
      <Stack spacing={0.25}>
        <Typography variant="h5" fontWeight={700}>
          {title || file.filename}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {title ? `${file.filename} · ${file.sourceRelpath}` : file.sourceRelpath}
        </Typography>
      </Stack>

      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        {file.mime ? <Chip label={file.mime} size="small" variant="outlined" /> : null}
        <Chip label={`${file.textCount} text items`} size="small" variant="outlined" />
        <Chip label={`${file.imageCount} image items`} size="small" variant="outlined" />
        {file.hasSynthesis ? <Chip label="Has synthesis" size="small" /> : null}
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
