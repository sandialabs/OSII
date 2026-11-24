import { useState } from "react";
import { Box, Card, CardActionArea, Stack, Typography } from "@mui/material";
import type { FileCardModel } from "../../../domain/files";
import {
  defaultFileDisplay,
  type FileDisplay,
} from "../../../domain/fileDisplay";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";

export function formatFileSize(sizeBytes: number | null) {
  if (sizeBytes === null || sizeBytes < 0) return null;
  if (sizeBytes < 1024) return `${sizeBytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = sizeBytes / 1024,
    index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index++;
  }
  return `${value < 10 ? value.toFixed(1) : Math.round(value)} ${units[index]}`;
}
export function formatModifiedDate(value: string | null) {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? null
    : date.toLocaleDateString(undefined, {
        year: "numeric",
        month: "short",
        day: "numeric",
      });
}
function Thumbnail({ file }: { file: FileCardModel }) {
  const pdf = file.mime === "application/pdf";
  const { thumbnailUrl } = usePdfThumbnail(
    pdf ? getObjectSourceUrl(file.fileId) : null,
    pdf && file.previewAvailable,
  );
  const [imageFailed, setImageFailed] = useState(false);
  const image = imageFailed
    ? null
    : thumbnailUrl ||
      (file.mime?.startsWith("image/")
        ? getObjectSourceUrl(file.fileId)
        : null);
  return (
    <Box
      aria-label={image ? "Document thumbnail" : "Text thumbnail"}
      sx={{
        height: 180,
        width: "100%",
        overflow: "hidden",
        bgcolor: "#fff",
        borderBottom: 1,
        borderColor: "divider",
      }}
    >
      {image ? (
        <img
          src={image}
          alt={`${file.title} thumbnail`}
          onError={() => setImageFailed(true)}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "contain",
            display: "block",
          }}
        />
      ) : (
        <Box
          aria-hidden
          sx={{
            p: 2.2,
            color: "#334155",
            fontFamily: "Georgia, serif",
            fontSize: 10,
            lineHeight: 1.6,
            whiteSpace: "pre-wrap",
            overflowWrap: "anywhere",
            height: "100%",
            overflow: "hidden",
            background: "linear-gradient(135deg,#fff,#f1f5f9)",
          }}
        >
          {file.textPreview || file.synthesisPreview || "No saved text yet"}
        </Box>
      )}
    </Box>
  );
}
export function FileCard({
  file,
  onOpen,
  compact = false,
  showPath = false,
  display = defaultFileDisplay,
  list = false,
}: {
  file: FileCardModel;
  onOpen: (id: string) => void;
  compact?: boolean;
  showPath?: boolean;
  display?: FileDisplay;
  list?: boolean;
}) {
  const label = display.name_source === "descriptive_title"
    ? file.descriptiveTitle?.trim() || file.title
    : file.title;
  const metadata =
    display.metadata === "path"
      ? file.subtitle
      : display.metadata === "modified"
        ? formatModifiedDate(file.modifiedAt)
        : display.metadata === "format"
          ? file.mime?.split("/").pop()
          : null;
  const details = [
    display.show_size ? formatFileSize(file.sizeBytes) : null,
    metadata,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <Card
      variant="outlined"
      sx={{
        height: "100%",
        position: "relative",
        overflow: "hidden",
        "&:hover .file-hover, &:focus-within .file-hover": {
          opacity: 1,
          transform: "none",
        },
      }}
    >
      <CardActionArea
        onClick={() => onOpen(file.fileId)}
        aria-label={`Open file ${label}`}
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          minHeight: list ? 52 : undefined,
        }}
      >
        {!list && <Thumbnail file={file} />}
        {(display.show_name || list || details) && (
          <Stack spacing={0.25} sx={{ p: 1.2, minWidth: 0 }}>
            {(display.show_name || list) && (
              <Typography
                variant="body2"
                fontWeight={display.show_name ? 600 : 400}
                title={label === file.title ? label : `${label} · ${file.title}`}
                noWrap
              >
                {display.show_name || !list
                  ? label
                  : file.synthesisPreview?.slice(0, 120) ||
                    file.textPreview?.slice(0, 120) ||
                    "Document"}
              </Typography>
            )}
            {details && (
              <Typography variant="caption" color="text.secondary" noWrap>
                {details}
              </Typography>
            )}
          </Stack>
        )}
        {file.synthesisPreview && (
          <Box
            className="file-hover"
            sx={{
              position: "absolute",
              inset: 0,
              display: "flex",
              alignItems: "flex-end",
              p: 1.5,
              background:
                "linear-gradient(to top,rgba(15,23,42,.96),rgba(15,23,42,.8))",
              color: "#fff",
              opacity: 0,
              transform: "translateY(4px)",
              transition: "opacity .15s ease,transform .15s ease",
              pointerEvents: "none",
            }}
          >
            <Stack spacing={0.5}>
              <Typography variant="caption" fontWeight={700}>
                Summary
              </Typography>
              <Typography
                variant="body2"
                sx={{
                  display: "-webkit-box",
                  WebkitLineClamp: list ? 2 : 7,
                  WebkitBoxOrient: "vertical",
                  overflow: "hidden",
                  overflowWrap: "anywhere",
                }}
              >
                {file.synthesisPreview}
              </Typography>
            </Stack>
          </Box>
        )}
      </CardActionArea>
    </Card>
  );
}
