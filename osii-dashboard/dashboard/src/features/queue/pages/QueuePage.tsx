import { ChangeEvent, useEffect, useMemo, useState } from "react";
import {
  Alert,
  Button,
  Checkbox,
  Chip,
  Divider,
  FormControlLabel,
  LinearProgress,
  List,
  ListItem,
  ListItemButton,
  ListItemText,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { browseIntake, createProcessingRun, listProcessingRuns, uploadQueueFiles } from "../../../api/queue";

export function QueuePage() {
  const queryClient = useQueryClient();
  const [path, setPath] = useState("");
  const [queuedPaths, setQueuedPaths] = useState<string[]>([]);
  const [includeSubfolders, setIncludeSubfolders] = useState(true);
  const [synthesize, setSynthesize] = useState(true);
  const [embed, setEmbed] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const browse = useQuery({
    queryKey: ["intake", "browse", path],
    queryFn: () => browseIntake(path || undefined),
  });
  const runs = useQuery({
    queryKey: ["processing-runs"],
    queryFn: listProcessingRuns,
    refetchInterval: (query) => query.state.data?.runs.some((run) => ["queued", "pending", "running"].includes(run.status)) ? 1500 : 5000,
  });

  const addPath = (value: string) => {
    if (!value || queuedPaths.includes(value)) return;
    setQueuedPaths((items) => [...items, value]);
  };

  const handleUpload = async (event: ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(event.target.files ?? []);
    if (!files.length) return;
    setUploading(true);
    setMessage(null);
    try {
      const result = await uploadQueueFiles(files);
      setQueuedPaths((items) => [...items, ...result.uploads.map((upload) => upload.path).filter((value) => !items.includes(value))]);
      setMessage(`${result.uploads.length} file(s) uploaded and added to the queue.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Upload failed.");
    } finally {
      setUploading(false);
      event.target.value = "";
    }
  };

  const start = async () => {
    if (!queuedPaths.length) return;
    setStarting(true);
    setMessage(null);
    try {
      const run = await createProcessingRun({
        queue_paths: queuedPaths,
        include_subfolders: includeSubfolders,
        synthesizer_name: synthesize ? "firstN" : null,
        build_embeddings: embed,
      });
      setMessage(`Processing run ${run.id} is queued.`);
      setQueuedPaths([]);
      await queryClient.invalidateQueries({ queryKey: ["processing-runs"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not start processing.");
    } finally {
      setStarting(false);
    }
  };

  const recentRuns = useMemo(() => runs.data?.runs.slice(0, 10) ?? [], [runs.data]);

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Processing queue</Typography>
        <Typography color="text.secondary">
          Add shared-volume folders or one-off uploads, then run extraction, optional synthesis, and optional embeddings.
        </Typography>
      </Stack>

      {message ? <Alert severity={message.includes("failed") || message.includes("Could not") ? "error" : "success"}>{message}</Alert> : null}

      <Stack direction={{ xs: "column", lg: "row" }} spacing={3} alignItems="flex-start">
        <Paper variant="outlined" sx={{ p: 2, flex: 1, width: "100%" }}>
          <Stack spacing={2}>
            <Typography fontWeight={700}>Shared volume</Typography>
            <Stack direction="row" spacing={1}>
              <TextField size="small" fullWidth label="Folder path" value={path} onChange={(event) => setPath(event.target.value)} placeholder="Leave blank for shared root" />
              <Button variant="outlined" onClick={() => setPath("")}>Root</Button>
            </Stack>
            {browse.isLoading ? <LinearProgress /> : null}
            <List dense sx={{ maxHeight: 300, overflow: "auto", border: 1, borderColor: "divider", borderRadius: 1 }}>
              {(browse.data?.entries ?? []).map((entry) => (
                <ListItem key={entry.path} disablePadding secondaryAction={entry.processed ? <Chip size="small" label="Processed" /> : null}>
                  <ListItemButton onClick={() => entry.type === "folder" ? setPath(entry.path) : addPath(entry.path)}>
                    <ListItemText primary={entry.name} secondary={entry.type === "folder" ? entry.display : `${entry.display}${entry.size_bytes ? ` · ${Math.round(entry.size_bytes / 1024)} KB` : ""}`} />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          </Stack>
        </Paper>

        <Paper variant="outlined" sx={{ p: 2, flex: 1, width: "100%" }}>
          <Stack spacing={2}>
            <Typography fontWeight={700}>Queue and upload</Typography>
            <Button component="label" variant="outlined" startIcon={<UploadFileOutlinedIcon />} disabled={uploading}>
              {uploading ? "Uploading…" : "Upload files"}
              <input hidden type="file" multiple onChange={handleUpload} />
            </Button>
            <List dense sx={{ maxHeight: 180, overflow: "auto" }}>
              {queuedPaths.map((item) => (
                <ListItem key={item} secondaryAction={<Button size="small" onClick={() => setQueuedPaths((items) => items.filter((pathItem) => pathItem !== item))}>Remove</Button>}>
                  <ListItemText primary={item.split("/").pop()} secondary={item} />
                </ListItem>
              ))}
              {!queuedPaths.length ? <Typography color="text.secondary" variant="body2">Select shared files/folders or upload files to begin.</Typography> : null}
            </List>
            <Divider />
            <FormControlLabel control={<Checkbox checked={includeSubfolders} onChange={(event) => setIncludeSubfolders(event.target.checked)} />} label="Include subfolders" />
            <FormControlLabel control={<Checkbox checked={synthesize} onChange={(event) => setSynthesize(event.target.checked)} />} label="Create local baseline synthesis" />
            <FormControlLabel control={<Checkbox checked={embed} onChange={(event) => setEmbed(event.target.checked)} />} label="Build embeddings after extraction" />
            <Button variant="contained" startIcon={<PlayArrowOutlinedIcon />} disabled={!queuedPaths.length || starting} onClick={() => void start()}>
              {starting ? "Queueing…" : "Start processing"}
            </Button>
          </Stack>
        </Paper>
      </Stack>

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.5}>
          <Typography fontWeight={700}>Recent processing runs</Typography>
          {recentRuns.map((run) => (
            <Paper key={run.id} variant="outlined" sx={{ p: 1.5 }}>
              <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
                <Stack>
                  <Typography fontWeight={600}>{run.id.slice(0, 12)}</Typography>
                  <Typography variant="body2" color="text.secondary">{run.completed ?? 0} / {run.total ?? 0} files · {run.created_at}</Typography>
                </Stack>
                <Chip color={run.status === "done" ? "success" : run.status === "error" ? "error" : "primary"} label={run.status} />
              </Stack>
              {run.error ? <Alert severity="error" sx={{ mt: 1 }}>{run.error}</Alert> : null}
              {(run.logs ?? []).slice(-2).map((line) => <Typography key={line} variant="caption" display="block" color="text.secondary">{line}</Typography>)}
            </Paper>
          ))}
          {!recentRuns.length ? <Typography color="text.secondary">No processing runs yet.</Typography> : null}
        </Stack>
      </Paper>
    </Stack>
  );
}
