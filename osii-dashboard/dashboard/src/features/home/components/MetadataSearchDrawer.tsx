import { Alert, Button, Checkbox, Drawer, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { emptyFileFilters, type FileFilters } from "../../../domain/fileFilters";

export function MetadataSearchDrawer({ open, onClose, filters, onChange, formats, count, error, helperText }: {
  open: boolean; onClose: () => void; filters: FileFilters; onChange: (filters: FileFilters) => void;
  formats: string[]; count: number; error: string; helperText?: string;
}) {
  const field = (key: keyof FileFilters, value: string | boolean) => onChange({ ...filters, [key]: value });
  return <Drawer anchor="right" open={open} onClose={onClose} PaperProps={{ sx: { width: { xs: "100%", sm: 380 }, p: 3 } }}>
    <Stack spacing={2} role="search" aria-label="File metadata search">
      <Stack direction="row" justifyContent="space-between"><Typography variant="h6">Search file metadata</Typography><Button onClick={onClose}>Close</Button></Stack>
      <Typography variant="body2" color="text.secondary">{helperText || "Search recorded filenames, paths, formats, sizes, dates, and processing status. No model is used. Dates are UTC."}</Typography>
      <TextField label="Filename or path" value={filters.query} onChange={e => field("query", e.target.value)} />
      <TextField select label="File format" value={filters.format} onChange={e => field("format", e.target.value)}>
        <MenuItem value="">All formats</MenuItem>{formats.map(format => <MenuItem key={format} value={format}>{format}</MenuItem>)}
      </TextField>
      <Stack direction="row" spacing={1}>
        <TextField label="Minimum size (MiB)" type="number" inputProps={{ min: 0 }} value={filters.minMb} onChange={e => field("minMb", e.target.value)} />
        <TextField label="Maximum size (MiB)" type="number" inputProps={{ min: 0 }} value={filters.maxMb} onChange={e => field("maxMb", e.target.value)} />
      </Stack>
      <TextField label="Modified on or after" type="date" InputLabelProps={{ shrink: true }} value={filters.after} onChange={e => field("after", e.target.value)} />
      <TextField label="Modified on or before" type="date" InputLabelProps={{ shrink: true }} value={filters.before} onChange={e => field("before", e.target.value)} />
      <TextField select label="Extracted text" value={filters.text} onChange={e => field("text", e.target.value)}>
        <MenuItem value="">Any status</MenuItem><MenuItem value="yes">Available</MenuItem><MenuItem value="no">Missing</MenuItem>
      </TextField>
      <FormControlLabel control={<Checkbox checked={filters.summary} onChange={e => field("summary", e.target.checked)} />} label="Has summary" />
      <FormControlLabel control={<Checkbox checked={filters.enrichment} onChange={e => field("enrichment", e.target.checked)} />} label="Has enrichments" />
      {error ? <Alert severity="warning">{error}</Alert> : <Typography>{count} matching files</Typography>}
      <Button onClick={() => onChange({ ...emptyFileFilters })}>Clear filters</Button>
      <Button variant="contained" onClick={onClose}>Show matching files</Button>
    </Stack>
  </Drawer>;
}
