// src/features/files/components/FileSourcePanel.tsx
import { useEffect, useState } from "react";
import { Alert, Box, Button, CircularProgress, Stack, TextField, Typography } from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import ChevronLeftOutlinedIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";

import { usePdfDocument } from "../../../hooks/usePdfDocument";
import { PdfPageViewer } from "./PdfPageViewer";
import { getObjectSourceUrl } from "../../../api/source";

type FileSourcePanelProps = {
  fileId: string;
  mime: string | null;
  page?: number | null;
  onPageChange?: (page: number) => void;
  compact?: boolean;
};

export function FileSourcePanel({
  fileId,
  mime,
  page = null,
  onPageChange,
  compact = false,
}: FileSourcePanelProps) {
  const sourceUrl = getObjectSourceUrl(fileId);

  if (mime === "application/pdf") {
    return (
      <PdfSourcePanel
        sourceUrl={sourceUrl}
        page={page}
        onPageChange={onPageChange}
        compact={compact}
      />
    );
  }

  return (
    <Stack spacing={1.25}>
      <Typography variant="subtitle1" fontWeight={600}>
        Source File
      </Typography>
      <Button
        variant="contained"
        component="a"
        href={sourceUrl}
        target="_blank"
        rel="noreferrer"
        startIcon={<OpenInNewOutlinedIcon />}
        sx={{ alignSelf: "flex-start" }}
      >
        Open Original File
      </Button>
    </Stack>
  );
}

function PdfSourcePanel({
  sourceUrl,
  page,
  onPageChange,
  compact,
}: {
  sourceUrl: string;
  page?: number | null;
  onPageChange?: (page: number) => void;
  compact: boolean;
}) {
  const { pdf, isLoading, error } = usePdfDocument(sourceUrl);
  const [pageInput, setPageInput] = useState("");

  useEffect(() => {
    if (typeof page === "number" && Number.isFinite(page)) {
      setPageInput(String(page));
    }
  }, [page]);

  if (isLoading) {
    return (
      <Stack direction="row" spacing={2} alignItems="center">
        <CircularProgress size={24} />
        <Typography>Loading PDF…</Typography>
      </Stack>
    );
  }

  if (error) {
    return (
      <Alert severity="error">
        Failed to load PDF. {error.message}
      </Alert>
    );
  }

  if (!pdf) {
    return <Alert severity="info">PDF could not be loaded.</Alert>;
  }

  const pageCount = pdf.numPages;
  const currentPage = Math.min(Math.max(page ?? 1, 1), pageCount);

  const handleJumpToPage = () => {
    const parsed = Number(pageInput);
    if (!Number.isFinite(parsed)) return;

    const clamped = Math.min(Math.max(parsed, 1), pageCount);
    onPageChange?.(clamped);
  };

  return (
    <Stack spacing={1.25} sx={{ minWidth: 0 }}>
      <Stack
        direction={{ xs: "column", md: "row" }}
        spacing={1}
        justifyContent="space-between"
        alignItems={{ xs: "flex-start", md: "center" }}
      >
        <Typography variant="subtitle1" fontWeight={600}>
          Source PDF
        </Typography>

        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <Button
            size="small"
            variant="outlined"
            startIcon={<ChevronLeftOutlinedIcon />}
            onClick={() => onPageChange?.(Math.max(currentPage - 1, 1))}
            disabled={currentPage <= 1}
          >
            Prev
          </Button>

          <Typography variant="body2" color="text.secondary">
            Page {currentPage} of {pageCount}
          </Typography>

          <Button
            size="small"
            variant="outlined"
            endIcon={<ChevronRightOutlinedIcon />}
            onClick={() => onPageChange?.(Math.min(currentPage + 1, pageCount))}
            disabled={currentPage >= pageCount}
          >
            Next
          </Button>

          <TextField
            size="small"
            label="Go to page"
            value={pageInput}
            onChange={(event) => setPageInput(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                handleJumpToPage();
              }
            }}
            sx={{ width: 110 }}
          />

          <Button
            size="small"
            variant="contained"
            onClick={handleJumpToPage}
          >
            Go
          </Button>

          <Button
            variant="outlined"
            size="small"
            startIcon={<OpenInNewOutlinedIcon />}
            component="a"
            href={sourceUrl}
            target="_blank"
            rel="noreferrer"
          >
            Open
          </Button>
        </Stack>
      </Stack>

      <Box
        sx={{
          height: compact ? "68vh" : "72vh",
          border: (theme) => `1px solid ${theme.palette.divider}`,
          borderRadius: 1.25,
          overflow: "auto",
          backgroundColor: "#e2e8f0",
        }}
      >
        <PdfPageViewer
          pdf={pdf}
          pageNumber={currentPage}
          width={compact ? 680 : 760}
        />
      </Box>
    </Stack>
  );
}