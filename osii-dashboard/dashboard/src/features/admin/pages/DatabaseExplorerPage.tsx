import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, Dialog, DialogContent, DialogTitle, IconButton, LinearProgress, MenuItem, Stack, TextField, Typography } from "@mui/material";
import HelpOutline from "@mui/icons-material/HelpOutline";
import ExpandMore from "@mui/icons-material/ExpandMore";
import { getDatabaseSchema, queryDatabase } from "../../../api/database";
import { EnrichmentArtifactView } from "../../files/components/EnrichmentArtifactView";

const initialSql = "SELECT filename, source_relpath\nFROM documents\nORDER BY source_relpath\nLIMIT 25";

/** Same view in both products; authentication and storage stay at the API edge. */
export function DatabaseExplorerPage() {
  const schema = useQuery({ queryKey: ["database-schema"], queryFn: getDatabaseSchema, retry: false });
  const [sql, setSql] = useState(initialSql);
  const [limit, setLimit] = useState(100);
  const [help, setHelp] = useState(false);
  const [table, setTable] = useState("documents");
  const query = useMutation({ gcTime: 0, mutationFn: (submitted: { sql: string; limit: number }) => queryDatabase(submitted.sql, submitted.limit) });
  const error = query.error ?? schema.error;
  return <Stack spacing={2} sx={{ maxWidth: 1200, mx: "auto" }}>
    <Stack direction="row" alignItems="center" spacing={1}>
      <Typography variant="h4">Database explorer</Typography>
      <IconButton aria-label="About read-only database queries" onClick={() => setHelp(true)}><HelpOutline /></IconButton>
    </Stack>
    <Typography color="text.secondary">Read library records with SQL. Queries cannot change saved data.</Typography>
    {schema.isPending ? <LinearProgress /> : null}
    {error ? <Alert severity="error">{error instanceof Error ? error.message : "Database inspection is unavailable."}</Alert> : null}
    {schema.data && !schema.data.available ? <Alert severity="info">{schema.data.detail}</Alert> : null}
    {schema.data?.available ? <>
      <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
        <TextField select size="small" label="Library table" value={table} onChange={event => setTable(event.target.value)} sx={{ minWidth: 220 }}>
          {schema.data.tables.map(item => <MenuItem key={item.name} value={item.name}>{item.name}</MenuItem>)}
        </TextField>
        <Button disabled={query.isPending} onClick={() => { setSql(`SELECT * FROM "${table}" LIMIT 25`); query.reset(); }}>Use table query</Button>
        <Button onClick={() => void schema.refetch()}>Refresh schema</Button>
      </Stack>
      <Accordion disableGutters variant="outlined">
        <AccordionSummary expandIcon={<ExpandMore />}><Typography>Schema — columns and types</Typography></AccordionSummary>
        <AccordionDetails><Stack spacing={1}>{schema.data.tables.filter(item => item.name === table).map(item => <Stack key={item.name} spacing={0.5}>{item.columns.map(column => <Typography key={column.name} variant="body2" sx={{ fontFamily: "monospace" }}>{column.name} · {column.type}</Typography>)}</Stack>)}</Stack></AccordionDetails>
      </Accordion>
      <TextField label="SELECT query" multiline minRows={6} maxRows={18} value={sql} onChange={event => setSql(event.target.value)} inputProps={{ maxLength: 16000, spellCheck: false }} InputProps={{ sx: { fontFamily: "monospace" } }} />
      <Stack direction="row" spacing={1} alignItems="center">
        <Button variant="contained" disabled={query.isPending || !sql.trim()} onClick={() => { query.reset(); query.mutate({ sql, limit }); }}>{query.isPending ? "Running…" : "Run SELECT"}</Button>
        <TextField select size="small" label="Maximum rows" value={limit} onChange={event => setLimit(Number(event.target.value))} sx={{ minWidth: 140 }}>{[25, 100, 200].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}</TextField>
        <Button onClick={() => { setSql(""); query.reset(); }}>Clear</Button>
      </Stack>
      {query.isPending ? <LinearProgress aria-label="Running read-only query" /> : null}
      {query.data ? <>
        <Typography variant="body2">{query.data.row_count} rows returned · {query.data.elapsed_ms} ms · results are not saved</Typography>
        {query.variables?.sql !== sql ? <Alert severity="info">These results belong to the last submitted query, not the edited text above.</Alert> : null}
        {query.data.limited || query.data.truncated_cells ? <Alert severity="warning">Preview limited{query.data.truncated_cells ? `; ${query.data.truncated_cells} large cells shortened` : ""}. Narrow the query or select shorter fields to inspect more data.</Alert> : null}
        <EnrichmentArtifactView data={{ artifact_type: "table", title: "Read-only query results", columns: query.data.columns, rows: query.data.rows }} />
      </> : null}
    </> : null}
    <Dialog open={help} onClose={() => setHelp(false)} maxWidth="sm" fullWidth>
      <DialogTitle>Read-only library inspection</DialogTitle>
      <DialogContent><Stack spacing={2}>
        <Typography>Use SELECT, joins, filters, non-recursive WITH queries and common aggregates such as COUNT. Only the tables and columns shown in Schema are available. Account/session tables, secrets, configuration and raw job payloads are excluded.</Typography>
        <Typography>Each database statement has a two-second timeout. Results are limited to 200 rows, 32 columns and approximately 1 MB; long cells are visibly shortened. This is a preview, not a bulk export or a database administration console.</Typography>
        <Typography>Queries run only when you press Run SELECT. SQL and results stay in this page’s memory, not browser storage or OSII artifacts. OSII-server permits administrators only and audits a query fingerprint, never SQL text or returned data.</Typography>
        <Button onClick={() => setHelp(false)}>Close</Button>
      </Stack></DialogContent>
    </Dialog>
  </Stack>;
}
