// src/features/files/components/FileSourcePanel.tsx
import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  FormControlLabel,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import ChevronLeftOutlinedIcon from "@mui/icons-material/ChevronLeftOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";

import { usePdfDocument } from "../../../hooks/usePdfDocument";
import type { ManifestRecord } from "../../../api/types";
import { PdfPageViewer, type PdfBoundingRegion } from "./PdfPageViewer";
import { getObjectSourceUrl } from "../../../api/source";

type FileSourcePanelProps = {
  fileId: string;
  mime: string | null;
  page?: number | null;
  onPageChange?: (page: number) => void;
  compact?: boolean;
  segments?: ManifestRecord[];
};

function normalizedPageRegions(
  segments: ManifestRecord[],
  page: number,
): PdfBoundingRegion[] {
  return segments
    .filter((segment) => segment.source_origin?.page === page)
    .flatMap((segment) => {
      const rawRegions = Array.isArray(segment.regions)
        ? segment.regions
        : Array.isArray(segment.source_origin?.regions)
          ? segment.source_origin.regions
          : [];
      return rawRegions.flatMap((value) => {
        if (!value || typeof value !== "object") return [];
        const region = value as Record<string, unknown>;
        const bbox = region.bbox;
        if (
          !Array.isArray(bbox)
          || bbox.length !== 4
          || !bbox.every((coordinate) => (
            typeof coordinate === "number"
            && Number.isFinite(coordinate)
            && coordinate >= 0
            && coordinate <= 1
          ))
        ) {
          return [];
        }
        return [{
          bbox: bbox as [number, number, number, number],
          text: typeof region.text === "string" ? region.text : null,
          confidence: typeof region.confidence === "number" ? region.confidence : null,
        }];
      });
    });
}

export function FileSourcePanel({
  fileId,
  mime,
  page = null,
  onPageChange,
  compact = false,
  segments = [],
}: FileSourcePanelProps) {
  const sourceUrl = getObjectSourceUrl(fileId);

  if (mime === "application/pdf") {
    return (
      <PdfSourcePanel
        sourceUrl={sourceUrl}
        page={page}
        onPageChange={onPageChange}
        compact={compact}
        segments={segments}
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
  segments,
}: {
  sourceUrl: string;
  page?: number | null;
  onPageChange?: (page: number) => void;
  compact: boolean;
  segments: ManifestRecord[];
}) {
  const { pdf, isLoading, error } = usePdfDocument(sourceUrl);
  const [pageInput, setPageInput] = useState("");
  const [showBoundingBoxes, setShowBoundingBoxes] = useState(true);

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
  const regions = normalizedPageRegions(segments, currentPage);

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

          {regions.length ? (
            <FormControlLabel
              control={(
                <Switch
                  size="small"
                  checked={showBoundingBoxes}
                  onChange={(event) => setShowBoundingBoxes(event.target.checked)}
                />
              )}
              label="OCR boxes"
            />
          ) : null}
        </Stack>
      </Stack>

      {regions.length ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip size="small" color="error" variant="outlined" label={`${regions.length} grounded OCR regions`} />
          <Typography variant="caption" color="text.secondary">
            Boxes use normalized source coordinates and resize with the PDF page.
          </Typography>
        </Stack>
      ) : (
        <Typography variant="caption" color="text.secondary">
          No region-level provenance is available for this page.
        </Typography>
      )}

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
          regions={showBoundingBoxes ? regions : []}
        />
      </Box>
    </Stack>
  );
}
