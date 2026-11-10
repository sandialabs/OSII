import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Alert,
  Breadcrumbs,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import { apiJson } from "../../api/client";

export type PickedFile = {
  path: string;
  name: string;
  size_bytes: number | null;
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
  selected = [],
  onClose,
  onFolder,
  onFiles,
}: {
  open: boolean;
  initialPath?: string;
  boundaryPath?: string;
  foldersOnly?: boolean;
  selected?: PickedFile[];
  onClose: () => void;
  onFolder?: (path: string) => void;
  onFiles?: (files: PickedFile[]) => void;
}) {
  const [page, setPage] = useState<Page | null>(null);
  const [address, setAddress] = useState("");
  const [files, setFiles] = useState<PickedFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const pending = useRef<AbortController | null>(null);
  const cursor = useRef<string | null>(null);
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
    if (!next) release();
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
      setAddress(result.current_path);
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
      setAddress(initialPath ?? "");
      void load(initialPath);
    } else release();
    return release;
  }, [open]);
  const total = files.reduce((sum, file) => sum + (file.size_bytes ?? 0), 0);
  const breadcrumbs =
    page?.current_path.replace(/\\/g, "/").split("/").filter(Boolean) ?? [];
  const toggle = (file: PickedFile) =>
    setFiles((current) =>
      current.some((item) => item.path === file.path)
        ? current.filter((item) => item.path !== file.path)
        : [...current, file],
    );
  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>
        {foldersOnly ? "Choose a location" : "Select files"}
      </DialogTitle>
      <DialogContent>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
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
              onChange={(e) => setAddress(e.target.value)}
            />
            <Button type="submit">Go</Button>
          </Stack>
          <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
            {roots.data?.items.filter(insideBoundary).map((root) => (
              <Button key={root} size="small" onClick={() => void load(root)}>
                {root}
              </Button>
            ))}
          </Stack>
          <Breadcrumbs aria-label="Folder breadcrumbs">
            <Button
              size="small"
              disabled={!page?.parent_path || !insideBoundary(page.parent_path)}
              onClick={() => void load(page?.parent_path ?? undefined)}
            >
              ↑ Parent
            </Button>
            {breadcrumbs.map((part, index) => {
              const target = `${page?.current_path.replace(/\\/g, "/").startsWith("//") ? "//" : page?.current_path.startsWith("/") ? "/" : ""}${breadcrumbs.slice(0, index + 1).join("/")}${/^[A-Za-z]:$/.test(part) ? "/" : ""}`;
              return (
                <Button
                  size="small"
                  disabled={!insideBoundary(target)}
                  key={target}
                  onClick={() => void load(target)}
                >
                  {part}
                </Button>
              );
            })}
          </Breadcrumbs>
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
          <List
            dense
            aria-label={foldersOnly ? "Available folders" : "Available files"}
            sx={{ maxHeight: 350, overflow: "auto" }}
          >
            {page?.entries
              .filter((entry) => !foldersOnly || entry.type === "folder")
              .map((entry) => (
                <ListItem key={entry.path} disablePadding>
                  <ListItemButton
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
                    <ListItemText
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
          </List>
          {!foldersOnly && page && (
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
            onClick={() => page && onFolder?.(page.current_path)}
          >
            Use this location
          </Button>
        ) : (
          <Button
            variant="contained"
            disabled={
              !files.length || files.length > 10000 || total > 1024 ** 3 || busy
            }
            onClick={() => onFiles?.(files)}
          >
            Use {files.length} {files.length === 1 ? "file" : "files"}
          </Button>
        )}
      </DialogActions>
    </Dialog>
  );
}
