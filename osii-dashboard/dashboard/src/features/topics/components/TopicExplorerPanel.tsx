import { Component, useState, type ReactNode } from "react";
import {
  Alert,
  Autocomplete,
  Box,
  Button,
  Checkbox,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { DocumentThumbnail } from "../../../resources/documents/components/DocumentThumbnail";
import type { TopicDocument, TopicMap, RelatedDocuments } from "../types";
import { topicViews } from "./views";
import { updateSelection, type SelectionMode } from "./geometry";
import { searchTopicDocuments, topicLabel } from "./presentation";

type CollectionChoice = { id: string; name: string };
export type TopicCollectionActions = {
  collections: CollectionChoice[];
  create: (name: string, ids: string[]) => Promise<void>;
  add: (id: string, ids: string[]) => Promise<void>;
  privateByDefault?: boolean;
};
export function TopicExplorerPanel({
  map,
  related,
  focusedId,
  onFocus,
  onOpen,
  collections,
  renderMetadata,
}: {
  map: TopicMap;
  related: RelatedDocuments | null | undefined;
  focusedId: string;
  onFocus: (id: string) => void;
  onOpen: (id: string) => void;
  collections: TopicCollectionActions;
  renderMetadata: (document: TopicDocument) => ReactNode;
}) {
  const [resetPreviewToken, setResetPreviewToken] = useState(0);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [preview, setPreview] = useState<string[]>([]);
  const [query, setQuery] = useState("");
  const [viewId, setViewId] = useState(topicViews[0].id);
  const [reviewLimit, setReviewLimit] = useState(24);
  const [name, setName] = useState("");
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const allowed = new Set(map.points.map((point) => point.file_id));
  const relatedIds = new Set(
    related?.results.map((document) => document.file_id) ?? [],
  );
  const focused =
    map.points.find((point) => point.file_id === focusedId) ??
    (related?.document.file_id === focusedId ? related.document : undefined);
  const term = query.trim().toLocaleLowerCase();
  const matches = searchTopicDocuments(map.points, query);
  const select = (ids: string[], mode: SelectionMode) => {
    setSelected((current) => updateSelection(current, ids, mode, allowed));
    setNotice("");
  };
  const reviewIds = preview.length ? preview : [...selected];
  const review = map.points.filter((document) =>
    reviewIds.includes(document.file_id),
  );
  const View = (topicViews.find((view) => view.id === viewId) ?? topicViews[0])
    .View;
  const save = async (create: boolean) => {
    const ids = [...selected];
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (create) await collections.create(name.trim(), ids);
      else await collections.add(target, ids);
      setSelected(
        (current) => new Set([...current].filter((id) => !ids.includes(id))),
      );
      setPreview([]);
      setResetPreviewToken((value) => value + 1);
      setName("");
      setNotice(`${ids.length} documents saved to the collection.`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack spacing={2}>
      <Autocomplete
        forcePopupIcon={false}
        options={matches.slice(0, 50)}
        filterOptions={(options) => options}
        value={
          matches.slice(0, 50).find((point) => point.file_id === focusedId) ??
          null
        }
        inputValue={query}
        onInputChange={(_, value, reason) => {
          if (reason === "input" || reason === "clear") setQuery(value);
        }}
        onChange={(_, document) => {
          if (document) onFocus(document.file_id);
        }}
        getOptionLabel={(document) =>
          `${topicLabel(document, "titles")} · ${document.filename}`
        }
        isOptionEqualToValue={(a, b) => a.file_id === b.file_id}
        noOptionsText={
          term.length < 2
            ? "Type at least two characters to search mapped documents"
            : "No matching mapped documents"
        }
        renderOption={(props, document) => (
          <li {...props} key={document.file_id}>
            <Stack>
              <Typography variant="body2">
                {topicLabel(document, "titles")}
              </Typography>
              <Typography variant="caption">
                {document.source_relpath}
              </Typography>
            </Stack>
          </li>
        )}
        renderInput={(params) => (
          <TextField
            {...params}
            label="Search mapped documents"
            helperText={
              term.length >= 2
                ? `${matches.length} matches · showing up to 50. Search title, filename, path or metadata.`
                : `Search the ${map.shown_count} documents in this map. Narrow the scope to explore documents outside the displayed subset.`
            }
          />
        )}
      />
      {topicViews.length > 1 && (
        <TextField
          select
          size="small"
          label="Explorer view"
          value={viewId}
          onChange={(e) => setViewId(e.target.value)}
        >
          {topicViews.map((view) => (
            <MenuItem key={view.id} value={view.id}>
              {view.label}
            </MenuItem>
          ))}
        </TextField>
      )}
      <ExplorerViewBoundary key={viewId}>
        <View
          resetPreviewToken={resetPreviewToken}
          points={map.points}
          selectedId={focusedId}
          relatedIds={relatedIds}
          selectedIds={selected}
          onSelect={onFocus}
          onSelection={select}
          onPreview={(ids) => {
            setPreview(ids.filter((id) => allowed.has(id)));
            setReviewLimit(24);
          }}
        />
      </ExplorerViewBoundary>
      {preview.length > 0 && (
        <Stack direction="row" spacing={1} alignItems="center">
          <Typography>
            {preview.length} documents in this map neighborhood
          </Typography>
          <Button onClick={() => select(preview, "replace")}>
            Select previewed group
          </Button>
          <Button onClick={() => setPreview([])}>Dismiss preview</Button>
        </Stack>
      )}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography variant="h6">
            Collection selection · {selected.size} documents
          </Typography>
          <Typography variant="body2">
            Draw a circle, preview nearby documents, or use the checkboxes to
            review a group. Documents can overlap in the projection; review the
            files before saving.
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            <Button
              disabled={!focused || !allowed.has(focused.file_id)}
              onClick={() => focused && select([focused.file_id], "add")}
            >
              Add focused document
            </Button>
            <Button
              disabled={!matches.length}
              onClick={() =>
                select(
                  matches.map((document) => document.file_id),
                  "add",
                )
              }
            >
              Select search matches
            </Button>
            <Button
              disabled={!selected.size}
              onClick={() => {
                setSelected(new Set());
                setPreview([]);
                setResetPreviewToken((value) => value + 1);
              }}
            >
              Clear selection
            </Button>
          </Stack>
          {review.length > 0 && (
            <>
              <Box
                role="group"
                aria-label="Review cluster documents"
                sx={{
                  display: "grid",
                  gridTemplateColumns: {
                    xs: "1fr",
                    md: "repeat(3,minmax(0,1fr))",
                  },
                  gap: 1,
                  maxHeight: 420,
                  overflow: "auto",
                }}
              >
                {review.slice(0, reviewLimit).map((document) => (
                  <Stack
                    key={document.file_id}
                    direction="row"
                    spacing={1}
                    sx={{
                      p: 1,
                      border: "1px solid",
                      borderColor: "divider",
                      borderRadius: 1,
                    }}
                  >
                    <Checkbox
                      inputProps={{
                        "aria-label": `Include ${document.filename}`,
                      }}
                      checked={selected.has(document.file_id)}
                      onChange={(e) =>
                        select(
                          [document.file_id],
                          e.target.checked ? "add" : "remove",
                        )
                      }
                    />
                    <Box
                      sx={{
                        flexShrink: 0,
                        "& > div": { width: 50, height: 66 },
                      }}
                    >
                      <DocumentThumbnail
                        fileId={document.file_id}
                        filename={document.filename}
                        mime={
                          document.media_type ||
                          (/\.pdf$/i.test(document.filename)
                            ? "application/pdf"
                            : "application/octet-stream")
                        }
                      />
                    </Box>
                    <Stack sx={{ minWidth: 0 }}>
                      <Typography
                        variant="body2"
                        sx={{ overflowWrap: "anywhere" }}
                      >
                        {topicLabel(document, "titles")}
                      </Typography>
                      <Typography
                        variant="caption"
                        sx={{ overflowWrap: "anywhere" }}
                      >
                        {document.source_relpath}
                      </Typography>
                      <Button
                        size="small"
                        onClick={() => onFocus(document.file_id)}
                      >
                        Inspect
                      </Button>
                    </Stack>
                  </Stack>
                ))}
              </Box>
              {reviewLimit < review.length && (
                <Button onClick={() => setReviewLimit((limit) => limit + 24)}>
                  Show 24 more selected documents
                </Button>
              )}
            </>
          )}
          <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
            <TextField
              label={
                collections.privateByDefault
                  ? "New private collection name"
                  : "New collection name"
              }
              value={name}
              disabled={busy}
              inputProps={{ maxLength: 150 }}
              onChange={(e) => setName(e.target.value)}
            />
            <Button
              variant="contained"
              disabled={busy || !selected.size || !name.trim()}
              onClick={() => void save(true)}
            >
              {busy ? "Saving…" : "Create collection from selection"}
            </Button>
          </Stack>
          {collections.collections.length > 0 && (
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
              <TextField
                select
                label="Existing collection"
                sx={{ minWidth: 230 }}
                value={target}
                disabled={busy}
                onChange={(e) => setTarget(e.target.value)}
              >
                <MenuItem value="">Choose a collection</MenuItem>
                {collections.collections.map((collection) => (
                  <MenuItem key={collection.id} value={collection.id}>
                    {collection.name}
                  </MenuItem>
                ))}
              </TextField>
              <Button
                disabled={busy || !target || !selected.size}
                onClick={() => void save(false)}
              >
                Add selection to collection
              </Button>
            </Stack>
          )}
          {error && (
            <Alert severity="error">{error} Your selection is preserved.</Alert>
          )}
          {notice && <Alert severity="success">{notice}</Alert>}
        </Stack>
      </Paper>
      {focused && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Stack spacing={1}>
            <Typography variant="h6">
              {topicLabel(focused, "titles")}
            </Typography>
            <Typography variant="caption" sx={{ overflowWrap: "anywhere" }}>
              {focused.source_relpath}
            </Typography>
            <Button
              sx={{ alignSelf: "start" }}
              onClick={() => onOpen(focused.file_id)}
            >
              Open document
            </Button>
            <Box component="details">
              <Typography component="summary" sx={{ cursor: "pointer" }}>
                Advanced document metadata
              </Typography>
              <Box sx={{ pt: 1 }}>{renderMetadata(focused)}</Box>
            </Box>
            {related?.document.file_id === focusedId && (
              <>
                <Typography variant="subtitle2">
                  Related by full embedding similarity
                </Typography>
                {related.results.map((document) => (
                  <Stack
                    key={document.file_id}
                    direction="row"
                    spacing={1}
                    alignItems="center"
                  >
                    <Button onClick={() => onFocus(document.file_id)}>
                      {topicLabel(document, "titles")}
                    </Button>
                    <Typography variant="caption">
                      {document.similarity.toFixed(3)}
                    </Typography>
                    <Button
                      size="small"
                      onClick={() => onOpen(document.file_id)}
                    >
                      Open
                    </Button>
                  </Stack>
                ))}
              </>
            )}
          </Stack>
        </Paper>
      )}
    </Stack>
  );
}

class ExplorerViewBoundary extends Component<
  { children: ReactNode },
  { failed: boolean }
> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  render() {
    return this.state.failed ? (
      <Alert severity="error">
        This explorer view could not be displayed. Search and collection
        controls remain available.{" "}
        <Button onClick={() => this.setState({ failed: false })}>
          Retry view
        </Button>
      </Alert>
    ) : (
      this.props.children
    );
  }
}
