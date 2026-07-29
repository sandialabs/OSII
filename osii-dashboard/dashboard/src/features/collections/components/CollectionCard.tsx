// src/features/collections/components/CollectionCard.tsx
import { Alert, Button, Card, CardContent, CircularProgress, Stack, Typography } from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import { useNavigate } from "react-router-dom";

import type { CollectionResource } from "../../../api/types";
import { useCollectionMembers } from "../../../hooks/useCollections";
import { useObjectSummariesByIds } from "../../../hooks/useObjectSummariesByIds";
import { buildCollectionRoute } from "../../../utils/routes";
import { CollectionPreviewStrip } from "./CollectionPreviewStrip";

type CollectionCardProps = {
  collection: CollectionResource;
};

export function CollectionCard({ collection }: CollectionCardProps) {
  const navigate = useNavigate();

  const membersQuery = useCollectionMembers(collection.id, true);
  const previewIds = (membersQuery.data?.file_ids ?? []).slice(0, 4);
  const summariesQuery = useObjectSummariesByIds(
    previewIds,
    previewIds.length > 0,
  );

  const previewFiles = summariesQuery.data?.summaries ?? [];

  return (
    <Card
      sx={{
        height: "100%",
        borderLeft: collection.color
          ? `4px solid ${collection.color}`
          : `4px solid rgba(20,184,166,0.35)`,
      }}
    >
      <CardContent>
        <Stack spacing={1.5}>
          <Stack spacing={0.5}>
            <Typography variant="subtitle1" fontWeight={700}>
              {collection.name}
            </Typography>

            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                display: "-webkit-box",
                WebkitLineClamp: 2,
                WebkitBoxOrient: "vertical",
                overflow: "hidden",
                minHeight: "2.8em",
              }}
            >
              {collection.description || "No description"}
            </Typography>

            <Typography variant="caption" color="text.secondary">
              {collection.document_count} file{collection.document_count === 1 ? "" : "s"}
            </Typography>
          </Stack>

          {membersQuery.isLoading ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">
                Loading previews…
              </Typography>
            </Stack>
          ) : membersQuery.isError ? (
            <Alert severity="warning">
              Failed to load collection members.
            </Alert>
          ) : summariesQuery.isLoading && previewIds.length > 0 ? (
            <Stack direction="row" spacing={1} alignItems="center">
              <CircularProgress size={16} />
              <Typography variant="body2" color="text.secondary">
                Loading thumbnails…
              </Typography>
            </Stack>
          ) : summariesQuery.isError ? (
            <Alert severity="warning">
              Failed to load preview files.
            </Alert>
          ) : (
            <CollectionPreviewStrip
              files={previewFiles}
              totalCount={membersQuery.data?.file_ids.length ?? 0}
            />
          )}

          <Button
            variant="contained"
            startIcon={<OpenInNewOutlinedIcon />}
            onClick={() => navigate(buildCollectionRoute(collection.id))}
            sx={{ alignSelf: "flex-start" }}
          >
            Open Collection
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}