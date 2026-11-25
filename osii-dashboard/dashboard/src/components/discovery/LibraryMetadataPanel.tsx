import { useState } from "react";
import { Box, Button, ButtonBase, Dialog, DialogActions, DialogContent, DialogTitle, IconButton, Link, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import HelpOutlineIcon from "@mui/icons-material/HelpOutline";
import { Link as RouterLink } from "react-router-dom";
import type { LibraryMetadataOverview, LibraryMetadataSource } from "../../api/types";

const fieldNames = {
  author: "Authors",
  agency: "Agencies",
  document_type: "Document types",
  date: "Document dates",
  title: "Document titles",
} as const;
const PAGE_SIZE = 8;
const processorNames: Record<string, string> = {
  "core.document-metadata": "Suggest metadata",
  "openai.synthesizer": "OpenAI-compatible synthesis",
  "ollama.synthesizer": "Ollama synthesis",
};
type MetadataRow = LibraryMetadataOverview["document_fields"][keyof typeof fieldNames]["rows"][number];

function sourceLabel({ kind, processor }: LibraryMetadataSource) {
  if (kind === "file") return "File metadata";
  if (kind === "edited") return "Edited";
  if (kind === "ai") return "Inferred · " + (processor ? processorNames[processor] ?? processor : "Process unrecorded");
  return "Source unrecorded";
}

export function LibraryMetadataPanel({ data, fileCount }: { data: LibraryMetadataOverview; fileCount: number }) {
  const [field, setField] = useState<keyof typeof fieldNames>("author");
  const [query, setQuery] = useState("");
  const [dialog, setDialog] = useState<"help" | MetadataRow | null>(null);
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [visibleLocations, setVisibleLocations] = useState(PAGE_SIZE);
  const facet = data.document_fields[field];
  const matching = facet.rows.filter(row => row.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const shown = matching.slice(0, visible);
  const includesInferred = shown.some(row => row.sources?.some(source => source.kind === "ai"));
  const selected = dialog === "help" ? null : dialog;
  const sources = selected?.sources ?? (selected ? [{ kind: "unknown" as const, processor: null, count: selected.count }] : []);
  const rowStyle = { py: 0.65, borderBottom: 1, borderColor: "divider" };

  return (
    <Box sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", lg: "repeat(2, minmax(0, 1fr))" }, gap: 2 }}>
      <Paper component="section" variant="outlined" aria-labelledby="library-locations-title" sx={{ p: 1.5, minWidth: 0 }}>
        <Stack spacing={1}>
          <Typography id="library-locations-title" component="h3" variant="subtitle1" fontWeight={700}>File locations</Typography>
          <Stack spacing={0.25}>
            <Typography variant="caption" color="text.secondary">Configured source folder</Typography>
            <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{data.source_root}</Typography>
          </Stack>
          {data.locations.slice(0, visibleLocations).map(row => (
            <Stack key={JSON.stringify([row.label, row.browse_path])} direction="row" spacing={1} justifyContent="space-between" sx={rowStyle}>
              {row.label === "Location not recorded" ? <Typography variant="body2">{row.label}</Typography> : (
                <Link component={RouterLink} to={"/browse?" + new URLSearchParams({ path: row.browse_path })}
                  variant="body2" sx={{ overflowWrap: "anywhere" }}>{row.label}</Link>
              )}
              <Typography variant="body2" color="text.secondary">{row.count.toLocaleString()}</Typography>
            </Stack>
          ))}
          {!data.locations.length && <Typography variant="body2" color="text.secondary">No file locations recorded yet.</Typography>}
          {visibleLocations < data.locations.length && <Button size="small" onClick={() => setVisibleLocations(value => value + PAGE_SIZE)} sx={{ alignSelf: "start" }}>More locations</Button>}
          {data.location_count > data.locations.length && <Typography variant="caption" color="text.secondary">
            Showing the {data.locations.length.toLocaleString()} largest folders.
          </Typography>}
        </Stack>
      </Paper>

      <Paper component="section" variant="outlined" aria-labelledby="library-metadata-title" sx={{ p: 1.5, minWidth: 0 }}>
        <Stack spacing={1}>
          <Stack>
            <Stack direction="row" alignItems="center" spacing={0.5}>
              <Typography id="library-metadata-title" component="h3" variant="subtitle1" fontWeight={700}>Document metadata</Typography>
              <IconButton size="small" aria-label="About metadata sources" onClick={() => setDialog("help")}><HelpOutlineIcon fontSize="small" /></IconButton>
            </Stack>
            {includesInferred && <Typography variant="caption" color="text.secondary">Includes AI-inferred values</Typography>}
          </Stack>
          <Stack direction="row" alignItems="center" flexWrap="wrap" spacing={1} useFlexGap>
            <TextField select size="small" label="Group by" value={field}
              onChange={event => { setField(event.target.value as keyof typeof fieldNames); setQuery(""); setVisible(PAGE_SIZE); }}>
              {Object.entries(fieldNames).map(([value, label]) => <MenuItem key={value} value={value}>{label}</MenuItem>)}
            </TextField>
            <TextField size="small" label={"Filter " + fieldNames[field].toLocaleLowerCase()} value={query}
              onChange={event => { setQuery(event.target.value); setVisible(PAGE_SIZE); }} sx={{ flex: "1 1 140px" }} />
          </Stack>
          <Typography variant="caption" role="status" color="text.secondary">
            {facet.recorded_count.toLocaleString()} of {fileCount.toLocaleString()} files with a value
          </Typography>
          {shown.map(row => (
            <ButtonBase key={row.label} onClick={() => setDialog(row)} aria-haspopup="dialog"
              aria-label={`${row.label}, ${row.count.toLocaleString()} ${row.count === 1 ? "file" : "files"}, view sources`}
              sx={{ ...rowStyle, gap: 1, justifyContent: "space-between", textAlign: "left",
                "&:hover, &.Mui-focusVisible": { bgcolor: "action.hover" } }}>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere", minWidth: 0 }}>{row.label}</Typography>
              <Typography variant="body2" color="text.secondary">{row.count.toLocaleString()}</Typography>
            </ButtonBase>
          ))}
          {!matching.length && <Typography variant="body2" color="text.secondary">
            {query ? "No matching values." : "No values saved yet."}
          </Typography>}
          {visible < matching.length && <Button size="small" onClick={() => setVisible(value => value + PAGE_SIZE)} sx={{ alignSelf: "start" }}>Show more</Button>}
          {facet.distinct_count > facet.rows.length && <Typography variant="caption" color="text.secondary">
            Showing the {facet.rows.length.toLocaleString()} most frequent values.
          </Typography>}
        </Stack>
      </Paper>
      <Dialog open={dialog !== null} onClose={() => setDialog(null)} fullWidth maxWidth="xs" aria-labelledby="metadata-sources-title">
        <DialogTitle id="metadata-sources-title">{selected ? `Sources for ${selected.label}` : "Metadata sources"}</DialogTitle>
        <DialogContent>
          {selected ? <Stack spacing={1}>
            {sources.map(source => (
              <Stack key={JSON.stringify([source.kind, source.processor])} direction="row" spacing={1} justifyContent="space-between">
                <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{sourceLabel(source)}</Typography>
                <Typography variant="body2" color="text.secondary">{source.count.toLocaleString()}</Typography>
              </Stack>
            ))}
          </Stack> : <Stack spacing={1}>
            <Typography variant="body2">Select a value to see how many files share it and which processes supplied it.</Typography>
            <Typography variant="body2"><strong>Edited</strong> values come from saved corrections. <strong>File metadata</strong> comes from properties recorded during extraction. <strong>Inferred</strong> values are suggestions saved by Suggest metadata or AI synthesis.</Typography>
          </Stack>}
        </DialogContent>
        <DialogActions><Button onClick={() => setDialog(null)}>Close</Button></DialogActions>
      </Dialog>
    </Box>
  );
}
