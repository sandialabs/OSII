// src/features/files/components/FileCard.tsx
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import NotesOutlinedIcon from "@mui/icons-material/NotesOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import type { FileCardModel } from "../../../domain/files";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";

type FileCardProps = {
  file: FileCardModel;
  onOpen: (fileId: string) => void;
};

function Thumbnail({
  file,
}: {
  file: FileCardModel;
}) {
  const isPdf = file.mime === "application/pdf";
  const sourceUrl = isPdf ? getObjectSourceUrl(file.fileId) : null;
  const shouldGenerate = isPdf && file.previewAvailable;

  const { thumbnailUrl } = usePdfThumbnail(sourceUrl, shouldGenerate);

  if (thumbnailUrl) {
    return (
      <Box
        sx={{
          width: 104,
          height: 104,
          borderRadius: 1.25,
          overflow: "hidden",
          border: (theme) => `1px solid ${theme.palette.divider}`,
          backgroundColor: "#fff",
          flexShrink: 0,
        }}
      >
        <img
          src={thumbnailUrl}
          alt={`${file.title} thumbnail`}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            display: "block",
          }}
        />
      </Box>
    );
  }

  return (
    <Box
      sx={{
        width: 104,
        height: 104,
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

export function FileCard({ file, onOpen }: FileCardProps) {
  return (
    <Card
      sx={{
        height: "100%",
        position: "relative",
        overflow: "hidden",
        "&:hover .file-hover": {
          opacity: 1,
          transform: "translateY(0)",
        },
      }}
    >
      <CardActionArea
        onClick={() => onOpen(file.fileId)}
        sx={{
          height: "100%",
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
        }}
      >
        <Box
          sx={{
            width: "100%",
            display: "flex",
            justifyContent: "center",
            pt: 1.25,
            px: 1.25,
          }}
        >
          <Thumbnail file={file} />
        </Box>

        <CardContent
          sx={{
            width: "100%",
            pt: 1,
            pb: 1.25,
          }}
        >
          <Stack spacing={0.75}>
            <Typography
              variant="subtitle2"
              fontWeight={600}
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                minHeight: "2.6em",
              }}
            >
              {file.title}
            </Typography>

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 1,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                minHeight: "1.25em",
              }}
            >
              {file.subtitle || "No source path"}
            </Typography>

            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {file.hasSynthesis ? (
                <Chip
                  size="small"
                  icon={<AutoAwesomeOutlinedIcon />}
                  label="Synth"
                  variant="outlined"
                />
              ) : null}

              {file.hasPreferredText ? (
                <Chip
                  size="small"
                  icon={<NotesOutlinedIcon />}
                  label="Text"
                  variant="outlined"
                />
              ) : null}
            </Stack>
          </Stack>
        </CardContent>

        <Box
          className="file-hover"
          sx={{
            position: "absolute",
            inset: 0,
            display: "flex",
            alignItems: "flex-end",
            background:
              "linear-gradient(to top, rgba(15,23,42,0.9), rgba(15,23,42,0.5) 58%, rgba(15,23,42,0.06))",
            color: "#fff",
            opacity: 0,
            transform: "translateY(6px)",
            transition: "opacity 0.16s ease, transform 0.16s ease",
            p: 1.25,
          }}
        >
          <Stack spacing={1} sx={{ width: "100%" }}>
            <Typography
              variant="body2"
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 5,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                minHeight: "5.7em",
              }}
            >
              {file.synthesisPreview ?? "No synthesis preview available."}
            </Typography>

            <Stack direction="row" spacing={0.5} alignItems="center" sx={{ alignSelf: "flex-start" }}>
              <OpenInNewOutlinedIcon fontSize="small" />
              <Typography variant="button">Open</Typography>
            </Stack>
          </Stack>
        </Box>
      </CardActionArea>
    </Card>
  );
}
