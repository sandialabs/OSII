// src/features/search/components/SearchResultCard.tsx
import {
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Divider,
  Stack,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";

import type { SearchResultModel } from "../../../domain/search";
import { getObjectSourceUrl } from "../../../api/source";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";

type SearchResultCardProps = {
  result: SearchResultModel;
  onOpen: (result: SearchResultModel) => void;
};

function ResultVisual({
  fileId,
  filename,
}: {
  fileId: string;
  filename: string;
}) {
  const lower = filename.toLowerCase();
  const isPdf = lower.endsWith(".pdf");
  const sourceUrl = isPdf ? getObjectSourceUrl(fileId) : null;
  const { thumbnailUrl } = usePdfThumbnail(sourceUrl, Boolean(sourceUrl));

  if (thumbnailUrl) {
    return (
      <img
        src={thumbnailUrl}
        alt={`${filename} thumbnail`}
        style={{
          width: 92,
          height: 92,
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
        width: 92,
        height: 92,
        borderRadius: 1.25,
        border: (theme) => `1px solid ${theme.palette.divider}`,
        backgroundColor: "background.paper",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {isPdf ? (
        <PictureAsPdfOutlinedIcon color="error" />
      ) : (
        <DescriptionOutlinedIcon color="action" />
      )}
    </Box>
  );
}

export function SearchResultCard({
  result,
  onOpen,
}: SearchResultCardProps) {
  return (
    <Card>
      <CardActionArea onClick={() => onOpen(result)}>
        <CardContent>
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1.25} alignItems="flex-start">
              <ResultVisual
                fileId={result.fileId}
                filename={result.filename}
              />

              <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1 }}>
                <Stack
                  direction={{ xs: "column", md: "row" }}
                  spacing={1}
                  justifyContent="space-between"
                  alignItems={{ xs: "flex-start", md: "center" }}
                >
                  <Stack spacing={0.25} sx={{ minWidth: 0 }}>
                    <Typography variant="subtitle1" fontWeight={600}>
                      {result.filename}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {result.sourceRelpath}
                    </Typography>
                  </Stack>

                  <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                    {result.mode ? (
                      <Chip label={result.mode} size="small" variant="outlined" />
                    ) : null}
                    {result.page != null ? (
                      <Chip label={`Page ${result.page}`} size="small" variant="outlined" />
                    ) : null}
                    {result.chunkMethod ? (
                      <Chip
                        label={result.chunkMethod === "sentence_window" ? "Sentence window" : result.chunkMethod}
                        size="small"
                        variant="outlined"
                      />
                    ) : null}
                    <Chip label={`Score ${result.score.toFixed(3)}`} size="small" />
                  </Stack>
                </Stack>

                <Box
                  sx={{
                    p: 1.25,
                    borderRadius: 1.25,
                    backgroundColor: "rgba(20, 184, 166, 0.08)",
                    border: "1px solid rgba(20, 184, 166, 0.18)",
                  }}
                >
                  <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>
                    Matched chunk{result.overlapWithPrevious ? ` · ${result.overlapWithPrevious} shared characters` : ""}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      whiteSpace: "pre-wrap",
                      wordBreak: "break-word",
                      lineHeight: 1.6,
                    }}
                  >
                    {result.snippet ?? "No matched chunk text was returned for this result."}
                  </Typography>
                </Box>
              </Stack>
            </Stack>

            <Divider />

            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1}
              justifyContent="space-between"
              alignItems={{ xs: "flex-start", md: "center" }}
            >
              <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
                {result.collections.map((collection) => (
                  <Chip
                    key={collection.id}
                    label={collection.name}
                    size="small"
                    variant="outlined"
                  />
                ))}
              </Stack>

              <Button
                variant="contained"
                size="small"
                startIcon={<OpenInNewOutlinedIcon />}
                onClick={(event) => {
                  event.stopPropagation();
                  onOpen(result);
                }}
              >
                Open Match
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </CardActionArea>
    </Card>
  );
}
