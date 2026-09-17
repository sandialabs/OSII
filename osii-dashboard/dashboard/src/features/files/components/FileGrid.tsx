// src/features/files/components/FileGrid.tsx
import {
  Alert,
  Button,
  CircularProgress,
  Grid,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import { useEffect, useMemo, useState } from "react";

import type { FileCardModel } from "../../../domain/files";
import { FileCard } from "./FileCard";

const FILES_PER_PAGE = 48;

type FileSort =
  | "name-asc"
  | "name-desc"
  | "modified-desc"
  | "modified-asc"
  | "size-desc"
  | "size-asc";

const SORT_OPTIONS: Array<{ value: FileSort; label: string }> = [
  { value: "name-asc", label: "Alphabetical (A–Z)" },
  { value: "name-desc", label: "Alphabetical (Z–A)" },
  { value: "modified-desc", label: "Most recently modified" },
  { value: "modified-asc", label: "Oldest modified" },
  { value: "size-desc", label: "Largest first" },
  { value: "size-asc", label: "Smallest first" },
];

function compareText(left: string, right: string) {
  return left.localeCompare(right, undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function timestamp(value: string | null) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

function compareOptionalNumbers(
  left: number | null,
  right: number | null,
  direction: "asc" | "desc",
) {
  if (left === null && right === null) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return direction === "asc" ? left - right : right - left;
}

function compareFiles(left: FileCardModel, right: FileCardModel, sort: FileSort) {
  let result = 0;
  if (sort === "name-asc" || sort === "name-desc") {
    result = compareText(left.title, right.title);
    if (sort === "name-desc") result *= -1;
  } else if (sort === "modified-desc" || sort === "modified-asc") {
    result = compareOptionalNumbers(
      timestamp(left.modifiedAt),
      timestamp(right.modifiedAt),
      sort === "modified-asc" ? "asc" : "desc",
    );
  } else {
    result = compareOptionalNumbers(
      left.sizeBytes,
      right.sizeBytes,
      sort === "size-asc" ? "asc" : "desc",
    );
  }

  return result || compareText(left.title, right.title) || compareText(left.fileId, right.fileId);
}

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
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState<FileSort>("name-asc");
  const filteredFiles = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase();
    const matchingFiles = normalizedQuery
      ? files.filter((file) =>
          [file.title, file.subtitle, file.mime ?? ""].some((value) =>
            value.toLocaleLowerCase().includes(normalizedQuery),
          ),
        )
      : files;

    return [...matchingFiles].sort((left, right) => compareFiles(left, right, sort));
  }, [files, query, sort]);
  const visibleFiles = useMemo(
    () => filteredFiles.slice(0, visibleCount),
    [filteredFiles, visibleCount],
  );

  useEffect(() => {
    setVisibleCount(FILES_PER_PAGE);
  }, [files, query, sort]);

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

      {files.length > 0 ? (
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ sm: "center" }}
        >
          <TextField
            size="small"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Filter by filename, path, or file type"
            aria-label="Filter files"
            InputProps={{
              startAdornment: <SearchOutlinedIcon fontSize="small" sx={{ mr: 1, color: "text.secondary" }} />,
            }}
            sx={{ flex: 1, minWidth: { sm: 280 } }}
          />
          <TextField
            select
            size="small"
            label="Sort files"
            value={sort}
            onChange={(event) => setSort(event.target.value as FileSort)}
            sx={{ minWidth: 220 }}
          >
            {SORT_OPTIONS.map((option) => (
              <MenuItem key={option.value} value={option.value}>
                {option.label}
              </MenuItem>
            ))}
          </TextField>
        </Stack>
      ) : null}

      {files.length === 0 ? (
        <Typography color="text.secondary">{emptyMessage}</Typography>
      ) : filteredFiles.length === 0 ? (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
          <Typography color="text.secondary">No files match “{query.trim()}”.</Typography>
          <Button size="small" onClick={() => setQuery("")}>Clear filter</Button>
        </Stack>
      ) : (
        <Stack spacing={1}>
          {query.trim() ? (
            <Typography variant="caption" color="text.secondary">
              {filteredFiles.length} of {files.length} files match
            </Typography>
          ) : null}
          <Grid container spacing={1.5}>
            {visibleFiles.map((file) => (
              <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={file.fileId}>
                <FileCard file={file} onOpen={onOpen} />
              </Grid>
            ))}
          </Grid>
        </Stack>
      )}

      {filteredFiles.length > FILES_PER_PAGE ? (
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
          <Typography variant="caption" color="text.secondary">
            Showing {Math.min(visibleCount, filteredFiles.length)} of {filteredFiles.length} matching files
          </Typography>
          {visibleCount < filteredFiles.length ? (
            <Button
              size="small"
              variant="outlined"
              onClick={() => setVisibleCount((count) => count + FILES_PER_PAGE)}
            >
              Load {Math.min(FILES_PER_PAGE, filteredFiles.length - visibleCount)} more
            </Button>
          ) : null}
        </Stack>
      ) : null}
    </Stack>
  );
}
