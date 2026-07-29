// src/features/files/components/FileGrid.tsx
import {
  Alert,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";

import type { FileCardModel } from "../../../domain/files";
import { FileCard } from "./FileCard";

type FileGridProps = {
  files: FileCardModel[];
  title?: string;
  subtitle?: string;
  isLoading?: boolean;
  isError?: boolean;
  error?: unknown;
  emptyMessage?: string;
  onOpen: (fileId: string) => void;
};

export function FileGrid({
  files,
  title,
  subtitle,
  isLoading = false,
  isError = false,
  error,
  emptyMessage = "No files found.",
  onOpen,
}: FileGridProps) {
  if (isLoading) {
    return (
      <Stack direction="row" spacing={2} alignItems="center">
        <CircularProgress size={24} />
        <Typography>Loading files…</Typography>
      </Stack>
    );
  }

  if (isError) {
    return (
      <Alert severity="error">
        Failed to load files.
        {error instanceof Error ? ` ${error.message}` : ""}
      </Alert>
    );
  }

  return (
    <Stack spacing={1.5}>
      {title || subtitle ? (
        <Stack spacing={0.25}>
          {title ? (
            <Typography variant="subtitle1" fontWeight={600}>
              {title}
            </Typography>
          ) : null}
          {subtitle ? (
            <Typography variant="caption" color="text.secondary">
              {subtitle}
            </Typography>
          ) : null}
        </Stack>
      ) : null}

      {files.length === 0 ? (
        <Typography color="text.secondary">{emptyMessage}</Typography>
      ) : (
        <Grid container spacing={1.5}>
          {files.map((file) => (
            <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={file.fileId}>
              <FileCard file={file} onOpen={onOpen} />
            </Grid>
          ))}
        </Grid>
      )}
    </Stack>
  );
}