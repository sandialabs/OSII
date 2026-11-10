import { useMemo, useRef } from "react";
import {
  Alert,
  Button,
  Chip,
  LinearProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useSearchParams } from "react-router-dom";
import type { ScopeDescribeRequest } from "../../../api/types";
import { listFolderScopes } from "../../../api/scopes";
import {
  createCollection,
  addCollectionMembers,
} from "../../../api/collections";
import { useCollections } from "../../../hooks/useCollections";
import { buildFileRoute } from "../../../utils/routes";
import { SuggestedMetadata } from "../../files/components/SuggestedMetadata";
import { TopicExplorerPanel } from "../components/TopicExplorerPanel";
import { useRelatedDocuments, useTopicMap } from "../useTopics";

export function TopicExplorerPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const client = useQueryClient();
  const pending = useRef<{ key: string; id: string } | null>(null);
  const scope = useMemo<ScopeDescribeRequest>(() => {
    const collection = params.get("collection_id"),
      folder = params.get("folder_id");
    return collection
      ? { scope_type: "collection", collection_id: collection }
      : folder
        ? { scope_type: "folder", folder_id: folder }
        : { scope_type: "root" };
  }, [params]);
  const selectedId = params.get("file_id") ?? "";
  const collections = useCollections();
  const folders = useQuery({
    queryKey: ["scopes", "folders"],
    queryFn: listFolderScopes,
  });
  const map = useTopicMap(scope);
  const related = useRelatedDocuments(scope, selectedId, map.data?.index.id);
  const scopeValue =
    scope.scope_type === "collection"
      ? `collection:${scope.collection_id}`
      : scope.scope_type === "folder"
        ? `folder:${scope.folder_id}`
        : "root";
  const changed = async () => {
    await client.invalidateQueries({ queryKey: ["collections"] });
  };
  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between">
        <Stack>
          <Typography variant="h5">Topic explorer</Typography>
          <Typography color="text.secondary">
            Find groups of documents, inspect their content, and save
            collections.
          </Typography>
        </Stack>
        <Button disabled={map.isFetching} onClick={() => void map.refetch()}>
          Refresh map
        </Button>
      </Stack>
      <TextField
        select
        size="small"
        label="Explore scope"
        value={scopeValue}
        onChange={(e) => {
          const value = e.target.value;
          setParams(
            value === "root"
              ? {}
              : value.startsWith("collection:")
                ? { collection_id: value.slice(11) }
                : { folder_id: value.slice(7) },
          );
        }}
      >
        <MenuItem value="root">All documents</MenuItem>
        {collections.data?.collections.map((c) => (
          <MenuItem key={c.id} value={`collection:${c.id}`}>
            Collection: {c.name}
          </MenuItem>
        ))}
        {folders.data?.scopes.map((f) => (
          <MenuItem key={f.folder_id} value={`folder:${f.folder_id}`}>
            Folder: {f.path || "/"}
          </MenuItem>
        ))}
        {scopeValue !== "root" &&
          !collections.data?.collections.some(
            (c) => scopeValue === `collection:${c.id}`,
          ) &&
          !folders.data?.scopes.some(
            (f) => scopeValue === `folder:${f.folder_id}`,
          ) && (
            <MenuItem value={scopeValue}>Selected scope (unavailable)</MenuItem>
          )}
      </TextField>
      {map.isFetching && <LinearProgress aria-label="Loading embedding map" />}
      {map.isError && <Alert severity="warning">{map.error.message}</Alert>}
      {map.data && !map.isError && (
        <>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Chip
              label={`${map.data.shown_count} of ${map.data.indexed_count} indexed documents mapped`}
            />
            <Chip
              label={`${map.data.unindexed_count} unindexed · ${map.data.stale_count} stale`}
            />
          </Stack>
          {map.data.shown_count < map.data.indexed_count && (
            <Alert severity="info">
              The map displays a stable subset of {map.data.shown_count}{" "}
              documents. Choose a smaller folder or collection to explore the
              rest. Graphical selection and search operate on this displayed
              subset.
            </Alert>
          )}
          {!map.data.index.semantic && (
            <Alert severity="info">
              These are lexical or unverified embeddings. Nearby documents may
              share words rather than meaning.
            </Alert>
          )}
          {map.data.points.length ? (
            <TopicExplorerPanel
              key={`${JSON.stringify(scope)}:${map.data.index.id}`}
              map={map.data}
              related={related.data}
              focusedId={selectedId}
              onFocus={(id) => {
                const next = new URLSearchParams(params);
                next.set("file_id", id);
                setParams(next);
              }}
              onOpen={(id) => navigate(buildFileRoute({ fileId: id }))}
              renderMetadata={(document) => (
                <SuggestedMetadata
                  fileId={document.file_id}
                  metadata={document.document_metadata}
                />
              )}
              collections={{
                collections: (collections.data?.collections ?? []).map((c) => ({
                  id: c.id,
                  name: c.name,
                })),
                create: async (name, ids) => {
                  const key = JSON.stringify([name, [...ids].sort()]);
                  let id =
                    pending.current?.key === key ? pending.current.id : "";
                  if (!id) {
                    const response = await createCollection({ name });
                    if (!response.collection?.id)
                      throw Error(
                        "Collection could not be created. Check its name.",
                      );
                    id = response.collection.id;
                    pending.current = { key, id };
                  }
                  await addCollectionMembers(id, { file_ids: ids });
                  pending.current = null;
                  await changed();
                },
                add: async (id, ids) => {
                  await addCollectionMembers(id, { file_ids: ids });
                  await changed();
                },
              }}
            />
          ) : (
            <Alert severity="info">
              No documents with current embeddings in this scope. Build
              embeddings in Intake or select another scope.
            </Alert>
          )}
          {related.isFetching && selectedId && (
            <LinearProgress aria-label="Finding related documents" />
          )}
          {related.isError && (
            <Alert severity="warning">{related.error.message}</Alert>
          )}
          <details>
            <summary>Index and projection details</summary>
            <Typography variant="caption">
              {map.data.index.model} · {map.data.index.dimensions} dimensions ·
              PCA retains {(map.data.explained_variance * 100).toFixed(1)}% of
              variance. Related ranking uses full document vectors; visual
              neighborhoods are approximate. Viewing and selection do not make
              model calls.
            </Typography>
          </details>
        </>
      )}
    </Stack>
  );
}
