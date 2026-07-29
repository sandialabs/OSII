// src/features/browse/components/FolderTile.tsx
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Stack,
  Typography,
} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";

import type { FolderScopeDescriptor } from "../../../api/types";
import { useFolderArtifactSummary } from "../../../hooks/useFolderArtifactSummary";

type FolderTileProps = {
  folder: FolderScopeDescriptor;
  selected?: boolean;
  onOpen: () => void;
};

export function FolderTile({
  folder,
  selected = false,
  onOpen,
}: FolderTileProps) {
  const { data } = useFolderArtifactSummary(folder, true);
  const memberCount = data?.artifact_summary.member_count ?? null;
  const synthesisPreview = data?.artifact_summary.synthesis_preview ?? null;

  return (
    <Card
      sx={{
        height: "100%",
        position: "relative",
        overflow: "hidden",
        borderColor: selected ? "primary.main" : undefined,
        backgroundColor: selected ? "rgba(20, 184, 166, 0.04)" : undefined,
        "&:hover .folder-hover": {
          opacity: 1,
          transform: "translateY(0)",
        },
      }}
    >
      <CardActionArea
        onClick={onOpen}
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
          <Box
            sx={{
              width: 104,
              height: 104,
              borderRadius: 1.25,
              border: (theme) => `1px solid ${theme.palette.divider}`,
              backgroundColor: "background.paper",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              gap: 0.5,
            }}
          >
            <FolderOutlinedIcon color="primary" sx={{ fontSize: 34 }} />
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              {memberCount != null ? `${memberCount} files` : "Folder"}
            </Typography>
          </Box>
        </Box>

        <CardContent sx={{ pt: 1, pb: 1.25 }}>
          <Stack spacing={0.5}>
            <Typography
              variant="subtitle2"
              fontWeight={600}
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                minHeight: "2.5em",
              }}
            >
              {folder.label.split("/").slice(-1)[0]}
            </Typography>

            <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
              {memberCount != null ? (
                <Chip
                  label={`${memberCount} files`}
                  size="small"
                  variant="outlined"
                />
              ) : null}
            </Stack>
          </Stack>
        </CardContent>

        <Box
          className="folder-hover"
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
              {synthesisPreview ?? "Open folder"}
            </Typography>

            <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
              <OpenInNewOutlinedIcon sx={{ fontSize: 16 }} />
              <Typography variant="caption" sx={{ color: "#fff" }}>
                Open folder
              </Typography>
            </Box>
          </Stack>
        </Box>
      </CardActionArea>
    </Card>
  );
}