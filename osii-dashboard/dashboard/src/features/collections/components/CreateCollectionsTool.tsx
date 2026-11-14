import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";
import {
  Alert,
  Autocomplete,
  Button,
  Checkbox,
  FormControlLabel,
  LinearProgress,
  List,
  ListItemButton,
  ListItemText,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { apiJson } from "../../../api/client";
import { useWorkbenchHome } from "../../../hooks/useWorkbenchHome";
import {
  folderGroups,
  matchingCandidates,
  type CollectionCandidate,
} from "../collectionBuilder";

/** Shared selection/review UI. Product adapters own collection writes. */
export function CreateCollectionsTool({
  create,
}: {
  create: (name: string, ids: string[]) => Promise<void>;
}) {
  const home=useWorkbenchHome();
  const [params] = useSearchParams(),
    client = useQueryClient();
  const [mode, setMode] = useState("files"),
    [query, setQuery] = useState(""),
    [name, setName] = useState("");
  const [selected, setSelected] = useState<Set<string>>(
    () => new Set(params.get("file_id") ? [params.get("file_id")!] : []),
  );
  const [target, setTarget] = useState("");
  const existing = useQuery({
    queryKey: ["collections", "builder"],
    queryFn: () =>
      apiJson<{
        items?: { id: string; name: string; can_manage?: boolean }[];
        collections?: { id: string; name: string }[];
      }>("/api/collections"),
  });
  const choices = (
    existing.data?.items ||
    existing.data?.collections ||
    []
  ).filter((item) => !("can_manage" in item) || item.can_manage);
  const [folders, setFolders] = useState<string[]>([]),
    [separate, setSeparate] = useState(true);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [saved, setSaved] = useState<Set<string>>(new Set());
  const [review, setReview] = useState(false),
    [limit, setLimit] = useState(40);
  const catalog = useQuery({
    queryKey: ["collection-candidates"],
    queryFn: async ({ signal }) => {
      const documents: CollectionCandidate[] = [];
      let cursor: string | null = null;
      const seen = new Set<string>();
      do {
        const result: {
          items: CollectionCandidate[];
          next_cursor: string | null;
        } = await apiJson<{
          items: CollectionCandidate[];
          next_cursor: string | null;
        }>(
          `/api/catalog/files?limit=500${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
          { signal },
        );
        documents.push(...result.items);
        cursor = result.next_cursor;
        if (cursor && seen.has(cursor))
          throw Error(
            "File catalog repeated a page. Retry before creating collections.",
          );
        if (cursor) seen.add(cursor);
      } while (cursor);
      return [...new Map(documents.map((doc) => [doc.file_id, doc])).values()];
    },
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
    staleTime: 30_000,
  });
  const documents = catalog.data || [],
    allowed = useMemo(
      () => new Set(documents.map((doc) => doc.file_id)),
      [documents],
    );
  const groups = useMemo(() => folderGroups(documents), [documents]),
    matches = useMemo(
      () => matchingCandidates(documents, query),
      [documents, query],
    );
  useEffect(() => {
    setReview(false);
    setError("");
  }, [mode, selected, folders, name, separate, target]);
  const ids =
    mode === "folders"
      ? groups
          .filter((group) => folders.includes(group.path))
          .flatMap((group) => group.documents.map((doc) => doc.file_id))
      : [...selected].filter((id) => allowed.has(id));
  const proposals =
    mode === "folders" && separate && !target
      ? groups
          .filter((group) => folders.includes(group.path))
          .map((group) => ({
            name: `${name.trim() ? name.trim() + " · " : ""}${group.label}`,
            ids: group.documents.map((doc) => doc.file_id),
          }))
      : [
          {
            name: target
              ? choices.find((item) => item.id === target)?.name || ""
              : name.trim(),
            ids,
          },
        ];
  const valid =
    proposals.length > 0 &&
    proposals.every(
      (proposal) =>
        proposal.name &&
        proposal.name.length <= 150 &&
        proposal.ids.length > 0 &&
        proposal.ids.length <= 10000,
    );
  const key = (proposal: (typeof proposals)[number]) =>
    JSON.stringify([target, proposal]);
  const remaining = proposals.filter((proposal) => !saved.has(key(proposal)));
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      for (const proposal of remaining) {
        if (target)
          await apiJson(
            `/api/collections/${encodeURIComponent(target)}/members`,
            { method: "POST", json: { file_ids: proposal.ids } },
          );
        else await create(proposal.name, proposal.ids);
        setSaved((previous) => new Set([...previous, key(proposal)]));
      }
      await client.invalidateQueries({ queryKey: ["collections"] });
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Stack spacing={2} sx={{ maxWidth: 1000, mx: "auto" }}>
      <Stack direction="row" justifyContent="space-between">
        <Typography variant="h5" fontWeight={700}>
          Create Collections
        </Typography>
        <Button component={Link} to="/collections">
          View collections
        </Button>
      </Stack>
      <Tabs
        value={mode}
        onChange={(_, value) => setMode(value)}
        aria-label="Collection source"
      >
        <Tab value="files" label="Select files" disabled={busy} />
        <Tab value="folders" label="Folders" disabled={busy} />
        <Tab value="topics" label="Topics" disabled={busy} />
      </Tabs>
      {catalog.isPending && (
        <LinearProgress aria-label="Loading all collection candidates" />
      )}
      {catalog.isError && (
        <Alert
          severity="error"
          action={<Button onClick={() => void catalog.refetch()}>Retry</Button>}
        >
          Could not load the complete file catalog.{" "}
          {(catalog.error as Error).message}
        </Alert>
      )}
      {mode === "topics" ? (
        <Stack spacing={2}>
          <Typography>
            Preview a cluster or draw around related documents, then save them
            as a collection.
          </Typography>
          <Button
            component={Link}
            to="/topics"
            disabled={home.data?.tools.topics?.enabled !== true}
            variant="contained"
            sx={{ alignSelf: "start" }}
          >
            Select a topic cluster
          </Button>
          {home.data?.tools.topics?.enabled !== true && <Typography variant="caption" color="text.secondary">{home.isError ? "Topic readiness unavailable. Retry from the Toolbox." : home.data?.tools.topics?.reason ?? "Checking topic readiness…"}</Typography>}
        </Stack>
      ) : (
        <>
          {mode === "folders" ? (
            <Stack spacing={1}>
              <Autocomplete
                multiple
                options={groups}
                value={groups.filter((group) => folders.includes(group.path))}
                onChange={(_, value) =>
                  setFolders(value.map((group) => group.path))
                }
                getOptionLabel={(group) =>
                  `${group.label} · ${group.documents.length} files`
                }
                isOptionEqualToValue={(a, b) => a.path === b.path}
                filterOptions={(options, state) =>
                  options
                    .filter((option) =>
                      option.label
                        .toLocaleLowerCase()
                        .includes(state.inputValue.toLocaleLowerCase()),
                    )
                    .slice(0, 50)
                }
                disabled={busy || !catalog.isSuccess}
                renderInput={(input) => (
                  <TextField
                    {...input}
                    label="Folders (files directly inside)"
                  />
                )}
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={separate}
                    disabled={busy}
                    onChange={(_, value) => setSeparate(value)}
                  />
                }
                label="Create one collection per selected folder"
                disabled={Boolean(target)}
              />
            </Stack>
          ) : (
            <>
              <TextField
                label="Find files"
                size="small"
                value={query}
                disabled={busy}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setLimit(40);
                }}
              />
              <Stack direction="row" spacing={1} alignItems="center">
                <Typography variant="body2">
                  {selected.size} selected · {matches.length} matching files
                </Typography>
                <Button
                  disabled={busy || !catalog.isSuccess}
                  onClick={() =>
                    setSelected(
                      (current) =>
                        new Set([
                          ...current,
                          ...matches.map((doc) => doc.file_id),
                        ]),
                    )
                  }
                >
                  Select matching
                </Button>
                <Button disabled={busy} onClick={() => setSelected(new Set())}>
                  Clear
                </Button>
              </Stack>
              <List
                dense
                aria-label="Collection file selector"
                sx={{
                  maxHeight: 360,
                  overflow: "auto",
                  border: 1,
                  borderColor: "divider",
                  borderRadius: 1,
                }}
              >
                {matches.slice(0, limit).map((doc) => (
                  <ListItemButton
                    key={doc.file_id}
                    disabled={busy}
                    role="checkbox"
                    aria-checked={selected.has(doc.file_id)}
                    onClick={() =>
                      setSelected((current) => {
                        const next = new Set(current);
                        if (next.has(doc.file_id)) next.delete(doc.file_id);
                        else next.add(doc.file_id);
                        return next;
                      })
                    }
                  >
                    <Checkbox
                      checked={selected.has(doc.file_id)}
                      tabIndex={-1}
                      disableRipple
                      inputProps={{ "aria-hidden": true }}
                    />
                    <ListItemText
                      primary={doc.filename}
                      secondary={doc.source_relpath}
                      primaryTypographyProps={{ noWrap: true }}
                      secondaryTypographyProps={{ noWrap: true }}
                    />
                  </ListItemButton>
                ))}
              </List>
              {limit < matches.length && (
                <Button onClick={() => setLimit(limit + 40)}>
                  Show more matching files
                </Button>
              )}
            </>
          )}
          {catalog.isSuccess && !documents.length && (
            <Alert severity="info">
              Add documents before creating a collection.
            </Alert>
          )}
          <TextField
            select
            label="Save to"
            value={target}
            disabled={busy}
            size="small"
            onChange={(event) => setTarget(event.target.value)}
          >
            <MenuItem value="">New collection</MenuItem>
            {choices.map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.name}
              </MenuItem>
            ))}
          </TextField>
          {!target && (
            <TextField
              label={
                mode === "folders" && separate && !target
                  ? "Optional name prefix"
                  : "Collection name"
              }
              value={name}
              size="small"
              disabled={busy}
              onChange={(event) => setName(event.target.value)}
              inputProps={{ maxLength: 150 }}
            />
          )}
          <Button
            variant="outlined"
            sx={{ alignSelf: "start" }}
            disabled={!valid || !catalog.isSuccess || busy}
            onClick={() => setReview(true)}
          >
            Preview{" "}
            {proposals.length > 1
              ? `${proposals.length} collections`
              : `collection · ${ids.length} files`}
          </Button>
          {ids.length > 10000 && !(mode === "folders" && separate) && (
            <Alert severity="warning">
              A collection supports up to 10,000 document references. Split this
              selection into smaller collections.
            </Alert>
          )}
          {review && (
            <Stack
              spacing={1}
              sx={{ border: 1, borderColor: "divider", borderRadius: 1, p: 2 }}
            >
              <Typography fontWeight={700}>Review collections</Typography>
              <Stack sx={{ maxHeight: 300, overflow: "auto" }}>
                {proposals.map((proposal, index) => (
                  <Typography key={index} variant="body2">
                    {proposal.name} · {proposal.ids.length} files
                    {saved.has(key(proposal)) ? " · Created" : ""}
                  </Typography>
                ))}
              </Stack>
              <Button
                variant="contained"
                disabled={busy || !remaining.length || !valid}
                onClick={() => void save()}
              >
                {busy
                  ? "Saving…"
                  : target
                    ? `Add ${ids.length} files`
                    : `Create ${remaining.length} collection${remaining.length === 1 ? "" : "s"}`}
              </Button>
            </Stack>
          )}
          {error && (
            <Alert severity="error">
              {error} Completed collections are kept; retry creates only the
              remaining ones.
            </Alert>
          )}
          {review && !remaining.length && (
            <Alert
              severity="success"
              action={
                <Button component={Link} to="/collections">
                  Open collections
                </Button>
              }
            >
              {target
                ? "Documents added to the collection."
                : "Collections created."}
            </Alert>
          )}
        </>
      )}
    </Stack>
  );
}
