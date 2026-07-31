// src/features/files/components/FileGrid.tsx
import {
  Alert,
  Button,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";

import type { FileCardModel } from "../../../domain/files";
import { FileCard } from "./FileCard";

const FILES_PER_PAGE = 48;

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
  const [visibleCount, setVisibleCount] = useState(FILES_PER_PAGE);
  const visibleFiles = useMemo(
    () => files.slice(0, visibleCount),
    [files, visibleCount],
  );

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
          {visibleFiles.map((file) => (
            <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={file.fileId}>
              <FileCard file={file} onOpen={onOpen} />
            </Grid>
          ))}
        </Grid>
      )}

      {files.length > FILES_PER_PAGE ? (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
          <Typography variant="caption" color="text.secondary">
            Showing {Math.min(visibleCount, files.length)} of {files.length} files
          </Typography>
          {visibleCount < files.length ? (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setVisibleCount((count) => count + FILES_PER_PAGE)}
            >
              Load {Math.min(FILES_PER_PAGE, files.length - visibleCount)} more
            </Button>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}
