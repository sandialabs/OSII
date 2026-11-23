import { useEffect, useState } from "react";
import {
  Alert,
  Button,
  Chip,
  LinearProgress,
  Stack,
  Typography,
} from "@mui/material";
import { SuggestedMetadata } from "../files/components/SuggestedMetadata";
import { TopicExplorerPanel } from "../topics/components/TopicExplorerPanel";
import { api, type Scope, type Collection } from "./api";
import type { apiJson } from "../../api/client";
import type { TopicMap, RelatedDocuments } from "../topics/types";
const metadataRequest: typeof apiJson = (path, init) =>
  api(path, init?.method, init?.json);
export function TopicExplorer({
  scope,
  open,
  collections,
  refreshCollections,
  canEdit,
}: {
  scope: Scope;
  open: (id: string) => void;
  collections: Collection[];
  refreshCollections: () => Promise<void>;
  canEdit: boolean;
}) {
  const [map, setMap] = useState<TopicMap | null>(null);
  const [related, setRelated] = useState<RelatedDocuments | null>(null);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [version, setVersion] = useState(0);
  useEffect(() => {
    setSelected("");
    setRelated(null);
    setMap(null);
  }, [scope]);
  useEffect(() => {
    let active = true;
    setBusy(true);
    setError("");
    void api<TopicMap>("/api/topics/map", "POST", { scope })
      .then((value) => {
        if (active) setMap(value);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [scope, version]);
  useEffect(() => {
    let active = true;
    setRelated(null);
    if (selected)
      void api<RelatedDocuments>("/api/topics/related", "POST", {
        scope,
        file_id: selected,
      })
        .then((value) => {
          if (active) setRelated(value);
        })
        .catch((e) => {
          if (active) setError(e.message);
        });
    return () => {
      active = false;
    };
  }, [scope, selected, version]);
  return (
    <Stack spacing={2}>
      <Stack direction="row" justifyContent="space-between">
        <Stack>
          <Typography variant="h5">Topic explorer</Typography>
          <Typography color="text.secondary">
            Find groups of documents, inspect their content, and save private
            collections.
          </Typography>
        </Stack>
        <Button disabled={busy} onClick={() => setVersion((v) => v + 1)}>
          Refresh map
        </Button>
      </Stack>
      {busy && <LinearProgress aria-label="Loading embedding map" />}
      {error && <Alert severity="warning">{error}</Alert>}
      {map && (
        <>
          <Stack direction="row" spacing={1} flexWrap="wrap">
            <Chip
              label={`${map.shown_count} of ${map.indexed_count} indexed documents mapped`}
            />
            <Chip
              label={`${map.unindexed_count} unindexed · ${map.stale_count} stale`}
            />
          </Stack>
          {map.shown_count < map.indexed_count && (
            <Alert severity="info">
              The map displays a stable subset of {map.shown_count} documents.
              Choose a smaller folder or collection to explore the rest.
              Graphical selection and search operate on this displayed subset.
            </Alert>
          )}
          {map.points.length ? (
            <TopicExplorerPanel
              key={`${JSON.stringify(scope)}:${map.index.id}`}
              map={map}
              related={related}
              focusedId={selected}
              onFocus={setSelected}
              onOpen={open}
              renderMetadata={(document) => (
                <SuggestedMetadata
                  metadata={document.document_metadata}
                  fileId={document.file_id}
                  canEdit={canEdit}
                  request={metadataRequest}
                  onSaved={() => setVersion((v) => v + 1)}
                />
              )}
              collections={{
                privateByDefault: true,
                collections: collections
                  .filter((c) => c.can_manage)
                  .map((c) => ({ id: c.id, name: c.name })),
                create: async (name, ids) => {
                  await api("/api/collections", "POST", {
                    name,
                    members: ids,
                    visibility: "private",
                  });
                  await refreshCollections();
                },
                add: async (id, ids) => {
                  const fresh = (
                    await api<{ items: Collection[] }>("/api/collections")
                  ).items.find((c) => c.id === id);
                  if (!fresh || !fresh.can_manage)
                    throw Error("Collection is unavailable or read-only");
                  await api(`/api/collections/${id}`, "PUT", {
                    ...fresh,
                    members: [...new Set([...fresh.members, ...ids])],
                  });
                  await refreshCollections();
                },
              }}
            />
          ) : (
            <Alert severity="info">
              No compatible embeddings in this scope. Choose a different scope
              or process documents in Intake.
            </Alert>
          )}
          <details>
            <summary>Index and projection details</summary>
            <Typography variant="caption">
              {map.index.model} · {map.index.dimensions} dimensions · PCA
              retains {(map.explained_variance * 100).toFixed(1)}% of variance.
              Related ranking uses full document vectors; visual neighborhoods
              are approximate. Viewing and selection do not make model calls.
            </Typography>
          </details>
        </>
      )}
    </Stack>
  );
}
