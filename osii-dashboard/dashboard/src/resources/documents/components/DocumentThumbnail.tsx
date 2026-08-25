import {
  Box,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";

import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";

type DocumentThumbnailProps = {
  fileId: string;
  mime: string;
  filename: string;
  previewAvailable?: boolean;
};

export function DocumentThumbnail({
  fileId,
  mime,
  filename,
  previewAvailable = true,
}: DocumentThumbnailProps) {
  const isPdf = mime === "application/pdf";
  const shouldGenerate = isPdf && previewAvailable;
  const sourceUrl = shouldGenerate ? getObjectSourceUrl(fileId) : null;

  const { thumbnailUrl, isLoading } = usePdfThumbnail(sourceUrl, shouldGenerate);

  if (thumbnailUrl) {
    return (
      <Box
        sx={{
          width: 92,
          height: 120,
          border: (theme) => `1px solid ${theme.palette.divider}`,
          borderRadius: 1,
          overflow: "hidden",
          flexShrink: 0,
          backgroundColor: "#fff",
        }}
      >
        <img
          src={thumbnailUrl}
          alt={`${filename} thumbnail`}
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
        width: 92,
        height: 120,
        border: (theme) => `1px solid ${theme.palette.divider}`,
        borderRadius: 1,
        flexShrink: 0,
        backgroundColor: "background.paper",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        px: 1,
      }}
    >
      {isLoading ? (
        <CircularProgress size={20} />
      ) : (
        <Stack spacing={1} alignItems="center">
          {isPdf ? (
            <PictureAsPdfOutlinedIcon color="error" />
          ) : (
            <DescriptionOutlinedIcon color="action" />
          )}
          <Typography
            variant="caption"
            color="text.secondary"
            textAlign="center"
            sx={{
              lineHeight: 1.2,
              wordBreak: "break-word",
            }}
          >
            {isPdf ? "PDF" : "File"}
          </Typography>
        </Stack>
      )}
    </Box>
  );
}
