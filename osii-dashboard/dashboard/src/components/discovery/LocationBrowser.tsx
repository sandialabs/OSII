import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import { apiJson } from "../../api/client";

export type PickedFile = {
  path: string;
  name: string;
  size_bytes: number | null;
  mime?: string | null;
};
type Page = {
  current_path: string;
  parent_path: string | null;
  cursor: string | null;
  entries: (PickedFile & { type: string; error?: string })[];
};
export function LocationBrowser({
  open,
  initialPath,
  boundaryPath,
  foldersOnly = false,
  singleFile = false,
  selected = [],
  onClose,
  onFolder,
  onFiles,
}: {
  open: boolean;
  initialPath?: string;
  boundaryPath?: string;
  foldersOnly?: boolean;
  singleFile?: boolean;
  selected?: PickedFile[];
  onClose: () => void;
  onFolder?: (path: string) => void;
  onFiles?: (files: PickedFile[]) => void;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [address, setAddress] = useState("");
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [showLocations, setShowLocations] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);
  const cursor = useRef<string | null>(null);
  const addressEdited = useRef(false);
  const roots = useQuery({
    queryKey: ["browse", "roots"],
    queryFn: ({ signal }) =>
      apiJson<{ items: string[] }>("/api/browse/roots", { signal }),
    enabled: open,
  });
  const release = () => {
    pending.current?.abort();
    if (cursor.current)
      void apiJson(`/api/browse/page/${cursor.current}`, {
        method: "DELETE",
      }).catch(() => {});
    cursor.current = null;
  };
  const insideBoundary = (path: string) => {
    const clean = (value: string) => {
      const path = value.replace(/\\/g, "/").replace(/\/+$/, "");
      return /^[A-Za-z]:|^\/\//.test(path) ? path.toLowerCase() : path;
    };
    return (
      !boundaryPath ||
      clean(path) === clean(boundaryPath) ||
      clean(path).startsWith(`${clean(boundaryPath)}/`)
    );
  };
  const load = async (path?: string, next?: string) => {
    if (path && !insideBoundary(path)) {
      setError("Choose another location using Add location.");
      return;
    }
    if (!next) {
      release();
      addressEdited.current = false;
    }
    const controller = new AbortController();
    pending.current = controller;
    setBusy(true);
    setError(null);
    if (!next) setPage(null);
    try {
      const params = new URLSearchParams(
        next ? { cursor: next } : path ? { path } : {},
      );
      const result = await apiJson<Page>(`/api/browse/page?${params}`, {
        signal: controller.signal,
      });
      if (controller.signal.aborted) return;
      cursor.current = result.cursor;
      setPage(result);
      if (!next) setShowLocations(false);
      if (!addressEdited.current) setAddress(result.current_path);
    } catch (e) {
      if (!controller.signal.aborted)
        setError(e instanceof Error ? e.message : String(e));
    } finally {
      if (pending.current === controller) setBusy(false);
    }
  };
  useEffect(() => {
    if (open) {
      setFiles(selected);
      const last = initialPath || (!boundaryPath ? localStorage.getItem("osii:last-folder") : null);
      setAddress(last ?? "");
      setPage(null);
      setShowLocations(!last);
      if (last) void load(last);
    } else release();
    return release;
  }, [open]);
  const total = files.reduce((sum, file) => sum + (file.size_bytes ?? 0), 0);
  const locations = roots.data?.items.filter(insideBoundary) ?? [];
  const toggle = (file: PickedFile) =>
    setFiles((current) =>
      current.some((item) => item.path === file.path)
        ? current.filter((item) => item.path !== file.path)
        : singleFile ? [file] : [...current, file],
    );
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="sm">
      <DialogTitle>
        {foldersOnly ? "Choose a location" : singleFile ? "Select a file" : "Select files"}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1} sx={{ pt: 1 }}>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Button size="small" aria-expanded={showLocations} aria-controls="file-picker-locations"
              onClick={() => setShowLocations(value => !value)}>Locations</Button>
            <Tooltip title="Parent folder">
              <span>
                <IconButton size="small" aria-label="Parent folder"
                  disabled={!page?.parent_path || !insideBoundary(page.parent_path)}
                  onClick={() => void load(page?.parent_path ?? undefined)}>
                  <ArrowUpwardIcon fontSize="small" />
                </IconButton>
              </span>
            </Tooltip>
          </Stack>
          <Stack
            component="form"
            direction="row"
            spacing={1}
            onSubmit={(e) => {
              e.preventDefault();
              void load(address);
            }}
          >
            <TextField
              fullWidth
              size="small"
              label="Folder path"
              value={address}
              inputProps={{ title: address }}
              onChange={(e) => {
                addressEdited.current = true;
                setAddress(e.target.value);
              }}
            />
            <Button type="submit">Go</Button>
          </Stack>
          {showLocations && (
            <List id="file-picker-locations" dense aria-label="Locations"
              sx={{ border: 1, borderColor: "divider", borderRadius: 1, py: 0 }}>
              {locations.map((location, index) => (
                <ListItem key={location} disablePadding divider={index < locations.length - 1}>
                  <ListItemButton selected={location === page?.current_path} onClick={() => void load(location)}>
                    <FolderOutlinedIcon fontSize="small" sx={{ mr: 1 }} />
                    <ListItemText primary={location} sx={{ overflowWrap: "anywhere" }} />
                  </ListItemButton>
                </ListItem>
              ))}
              {!locations.length && <ListItem><ListItemText primary="Enter a folder path above." /></ListItem>}
            </List>
          )}
          {busy && (
            <Stack direction="row" alignItems="center" spacing={1}>
              <LinearProgress sx={{ flex: 1 }} />
              <Button
                onClick={() => {
                  release();
                  setBusy(false);
                }}
              >
                Cancel loading
              </Button>
            </Stack>
          )}
          {error && (
            <Alert
              severity="error"
              action={
                <Button color="inherit" onClick={() => void load(address)}>
                  Retry
                </Button>
              }
            >
              {error}
            </Alert>
          )}
          {page && <List
            dense
            aria-label={foldersOnly ? "Available folders" : "Available files"}
            sx={{ minHeight: 100, maxHeight: 350, overflow: "auto", py: 0, border: 1, borderColor: "divider", borderRadius: 1 }}
          >
            {page?.entries
              .filter((entry) => !foldersOnly || entry.type === "folder")
              .sort((a, b) => Number(b.type === "folder") - Number(a.type === "folder"))
              .map((entry) => (
                <ListItem key={entry.path} disablePadding divider>
                  <ListItemButton
                    selected={files.some((file) => file.path === entry.path)}
                    disabled={
                      !["folder", "file"].includes(entry.type) ||
                      (entry.type === "file" &&
                        (entry.size_bytes === null ||
                          entry.size_bytes > 50 * 1024 ** 2))
                    }
                    onClick={() =>
                      entry.type === "folder"
                        ? void load(entry.path)
                        : toggle(entry)
                    }
                  >
                    {entry.type === "folder" ? (
                      <FolderOutlinedIcon sx={{ mr: 1 }} />
                    ) : (
                      <Checkbox
                        tabIndex={-1}
                        checked={files.some((file) => file.path === entry.path)}
                      />
                    )}
                    <ListItemText sx={{ overflowWrap: "anywhere" }}
                      primary={entry.name}
                      secondary={
                        entry.error ??
                        (entry.type === "file" && entry.size_bytes !== null
                          ? `${(entry.size_bytes / 1024 ** 2).toFixed(1)} MiB${entry.size_bytes > 50 * 1024 ** 2 ? " · exceeds 50 MiB processing limit" : ""}`
                          : entry.type === "link"
                            ? "Symbolic link"
                            : undefined)
                      }
                    />
                  </ListItemButton>
                </ListItem>
              ))}
          </List>}
          {!foldersOnly && !singleFile && page && (
            <Stack direction="row" spacing={1}>
              <Button
                disabled={
                  busy ||
                  !page.entries.some(
                    (entry) =>
                      entry.type === "file" &&
                      entry.size_bytes !== null &&
                      entry.size_bytes <= 50 * 1024 ** 2,
                  )
                }
                onClick={() =>
                  setFiles((current) => [
                    ...new Map(
                      [
                        ...current,
                        ...page.entries.filter(
                          (entry) =>
                            entry.type === "file" &&
                            entry.size_bytes !== null &&
                            entry.size_bytes <= 50 * 1024 ** 2,
                        ),
                      ].map((file) => [file.path, file]),
                    ).values(),
                  ])
                }
              >
                Select shown files
              </Button>
              <Button disabled={!files.length} onClick={() => setFiles([])}>
                Clear selection
              </Button>
            </Stack>
          )}
          {page?.cursor && (
            <Button
              disabled={busy}
              onClick={() => void load(undefined, page.cursor!)}
            >
              Next page
            </Button>
          )}
          {page && !page.entries.length && !page.cursor && (
            <Typography color="text.secondary">No more entries.</Typography>
          )}
          {!foldersOnly && (
            <Typography variant="body2">
              Selected files: {files.length} · {(total / 1024 ** 2).toFixed(1)}{" "}
              MiB
            </Typography>
          )}
          {files.length > 10000 || total > 1024 ** 3 ? (
            <Alert severity="warning">
              Select at most 10,000 files and 1 GiB.
            </Alert>
          ) : null}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        {foldersOnly ? (
          <Button
            variant="contained"
            disabled={!page || busy || Boolean(error)}
            onClick={() => { if (page) { localStorage.setItem("osii:last-folder", page.current_path); onFolder?.(page.current_path); } }}
          >
            Use this location
          </Button>
        ) : (
          <Button
            variant="contained"
            disabled={
              !files.length || files.length > 10000 || total > 1024 ** 3 || busy
            }
            onClick={() => { if (page) localStorage.setItem("osii:last-folder", page.current_path); onFiles?.(files); }}
          >
            Use {files.length} {files.length === 1 ? "file" : "files"}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
