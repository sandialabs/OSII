import { useState } from "react";
import { Box, Button, Link, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { Link as RouterLink } from "react-router-dom";
import type { LibraryMetadataOverview } from "../../api/types";

const fieldNames = {
  author: "Authors",
  agency: "Agencies",
  document_type: "Document types",
  date: "Document dates",
  title: "Document titles",
} as const;
const PAGE_SIZE = 8;

export function LibraryMetadataPanel({ data, fileCount }: { data: LibraryMetadataOverview; fileCount: number }) {
  const [field, setField] = useState<keyof typeof fieldNames>("author");
  const [query, setQuery] = useState("");
  const [visible, setVisible] = useState(PAGE_SIZE);
  const [visibleLocations, setVisibleLocations] = useState(PAGE_SIZE);
  const facet = data.document_fields[field];
  const matching = facet.rows.filter(row => row.label.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
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
          <Typography id="library-metadata-title" component="h3" variant="subtitle1" fontWeight={700}>Document metadata</Typography>
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
          {matching.slice(0, visible).map(row => (
            <Stack key={row.label} direction="row" spacing={1} justifyContent="space-between" sx={rowStyle}>
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{row.label}</Typography>
              <Typography variant="body2" color="text.secondary">{row.count.toLocaleString()}</Typography>
            </Stack>
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
    </Box>
  );
}
