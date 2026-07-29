// src/features/collections/components/CollectionFileGrid.tsx
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  CircularProgress,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import { useNavigate } from "react-router-dom";

import { useScopeSummaries } from "../../../hooks/useScopeSummaries";
import { useRemoveCollectionMember } from "../../../hooks/useCollections";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";
import { buildFileRoute } from "../../../utils/routes";
import type { ObjectSummary } from "../../../api/types";

type CollectionFileGridProps = {
  collectionId: string;
};

function CollectionFileCard({
  file,
  onOpen,
  onRemove,
  removing,
}: {
  file: ObjectSummary;
  onOpen: () => void;
  onRemove: () => void;
  removing: boolean;
}) {
  const filename = file.filename ?? file.file_id;
  const isPdf = filename.toLowerCase().endsWith(".pdf");
  const sourceUrl = isPdf ? getObjectSourceUrl(file.file_id) : null;
  const { thumbnailUrl } = usePdfThumbnail(sourceUrl, Boolean(sourceUrl));

  return (
    <Card
      sx={{
        height: "100%",
        position: "relative",
        overflow: "hidden",
        "&:hover .collection-file-hover": {
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
          {thumbnailUrl ? (
            <img
              src={thumbnailUrl}
              alt={`${filename} thumbnail`}
              style={{
                width: 104,
                height: 104,
                objectFit: "cover",
                borderRadius: 8,
                border: "1px solid rgba(15,23,42,0.12)",
                display: "block",
              }}
            />
          ) : (
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
              }}
            >
              {isPdf ? (
                <PictureAsPdfOutlinedIcon color="error" />
              ) : (
                <DescriptionOutlinedIcon color="action" />
              )}
            </Box>
          )}
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
              {filename}
            </Typography>

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 1,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {file.source_relpath ?? "No source path"}
            </Typography>
          </Stack>
        </CardContent>

        <Box
          className="collection-file-hover"
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
                WebkitLineClamp: 4,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
              }}
            >
              {file.synthesis_preview ?? "No synthesis preview available."}
            </Typography>

            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                variant="contained"
                startIcon={<OpenInNewOutlinedIcon />}
                onClick={(event) => {
                  event.stopPropagation();
                  onOpen();
                }}
              >
                Open
              </Button>

              <Button
                size="small"
                color="error"
                variant="contained"
                startIcon={<DeleteOutlineOutlinedIcon />}
                onClick={(event) => {
                  event.stopPropagation();
                  onRemove();
                }}
                disabled={removing}
              >
                Remove
              </Button>
            </Stack>
          </Stack>
        </Box>
      </CardActionArea>
    </Card>
  );
}

export function CollectionFileGrid({ collectionId }: CollectionFileGridProps) {
  const navigate = useNavigate();

  const summariesQuery = useScopeSummaries({
    scope_type: "collection",
    collection_id: collectionId,
  });

  const removeMutation = useRemoveCollectionMember(collectionId);

  const handleRemove = async (fileId: string) => {
    await removeMutation.mutateAsync(fileId);
    await summariesQuery.refetch();
  };

  if (summariesQuery.isLoading) {
    return (
      <Stack direction="row" spacing={2} alignItems="center">
        <CircularProgress size={24} />
        <Typography>Loading files…</Typography>
      </Stack>
    );
  }

  if (summariesQuery.isError) {
    return (
      <Alert severity="error">
        Failed to load collection files.
        {summariesQuery.error instanceof Error ? ` ${summariesQuery.error.message}` : ""}
      </Alert>
    );
  }

  const files = summariesQuery.data?.summaries ?? [];

  if (files.length === 0) {
    return (
      <Typography color="text.secondary">
        No files were found in this collection.
      </Typography>
    );
  }

  return (
    <Grid container spacing={1.5}>
      {files.map((file) => (
        <Grid item xs={12} sm={6} md={4} lg={3} xl={2} key={file.file_id}>
          <CollectionFileCard
            file={file}
            removing={removeMutation.isPending}
            onOpen={() => navigate(buildFileRoute({ fileId: file.file_id }))}
            onRemove={() => void handleRemove(file.file_id)}
          />
        </Grid>
      ))}
    </Grid>
  );
}