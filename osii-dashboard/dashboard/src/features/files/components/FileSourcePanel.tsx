import { pageBoundingRegions } from "../../../domain/textGrounding";
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
import { PdfPageViewer, BoundingRegionOverlay } from "./PdfPageViewer";
import { getObjectSourceUrl } from "../../../api/source";

type FileSourcePanelProps = {
  fileId: string;
  mime: string | null;
  page?: number | null;
  onPageChange?: (page: number) => void;
  compact?: boolean;
  segments?: ManifestRecord[];
};

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

  if (mime?.startsWith("image/")) return <ImageSourcePanel sourceUrl={sourceUrl} segments={segments} />;

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
  const regions = pageBoundingRegions(segments, currentPage);

  const handleJumpToPage = () => {
    const parsed = Number(pageInput);
    if (!Number.isFinite(parsed)) return;

    const clamped = Math.min(Math.max(parsed, 1), pageCount);
    onPageChange?.(clamped);
  };

  return (
    <Stack spacing={1.25} sx={{ minWidth: 0 }}>
      <Stack
        direction={compact ? "column" : { xs: "column", md: "row" }}
        spacing={1}
        justifyContent="space-between"
        alignItems={compact ? "flex-start" : { xs: "flex-start", md: "center" }}
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
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
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

function ImageSourcePanel({ sourceUrl, segments }: { sourceUrl: string; segments: ManifestRecord[] }) {
  const [failed, setFailed] = useState(false);
  useEffect(() => setFailed(false), [sourceUrl]);
  const [boxes, setBoxes] = useState(true);
  const regions = pageBoundingRegions(segments, 1);
  return <Stack spacing={1}>
    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
      <Typography fontWeight={600}>Source image</Typography>
      <Button component="a" href={sourceUrl} target="_blank" rel="noreferrer">Open original</Button>
      {regions.length > 0 && <FormControlLabel label="OCR boxes" control={<Switch size="small" checked={boxes} onChange={event => setBoxes(event.target.checked)} />} />}
    </Stack>
    {failed ? <Alert severity="info">This image format cannot be previewed here. Open the original file.</Alert> : <Box sx={{ overflow: "auto", maxHeight: "68vh" }}>
      <Box sx={{ position: "relative", width: 760, maxWidth: "100%", lineHeight: 0 }}>
        <img src={sourceUrl} alt="Original source" onError={() => setFailed(true)} style={{ display: "block", width: "100%", height: "auto" }} />
        <BoundingRegionOverlay regions={boxes ? regions : []} />
      </Box>
    </Box>}
    <Typography variant="caption" color="text.secondary">{regions.length ? `${regions.length} source regions · hover for recognized text and confidence` : "This text version has no region geometry."}</Typography>
  </Stack>;
}
