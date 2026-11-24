import { LibraryFlow } from "../../../components/workbench/LibraryFlow";
import type { LibraryProduct } from "../../../domain/libraryProducts";
import { WorkbenchHome } from "../../home/components/WorkbenchHome";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Alert, Button, Card, CardContent, Chip, Divider, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { Link } from "react-router-dom";
import { getToolCatalog } from "../../../api/tools";
import { getDatabaseSchema } from "../../../api/database";
import { ScopePicker } from "../../../components/discovery/ScopePicker";
import { ScopeWikiPanel } from "../components/ScopeWikiPanel";
import { ScopeEnrichmentsPanel } from "../components/ScopeEnrichmentsPanel";
import { ToolActionPanel } from "../components/ToolActionPanel";
import { SEARCH_INDEX_PATH } from "../../../utils/routes";
import type { ScopeDescribeRequest } from "../../../api/types";

const labels: Record<string, string> = { "text.read": "Read text", "summary.write": "Summarize", "metadata.suggest": "Suggest metadata", "wiki.write": "Write a wiki", "embedding.build": "Build embeddings", "topics.model": "Model topics", "topics.project": "Project embeddings", "documents.recommend": "Recommend documents", analyze: "Analyze" };

const outputs: Record<string, LibraryProduct[]> = {
  "text.read": ["text", "artifacts"],
  "summary.write": ["summaries", "metadata"],
  "metadata.suggest": ["metadata"],
  "embedding.build": ["index"],
};

export function ToolsWorkbench() {
  const catalog = useQuery({ queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 });
  const [action, setAction] = useState("wiki.write");
  const [scope, setScope] = useState<ScopeDescribeRequest>({ scope_type: "root" });
  const browsesSavedProducts = action === "wiki.write" || action === "analyze";
  const ready = scope.scope_type === "root" || Boolean(scope.scope_type === "object" ? scope.file_id : scope.scope_type === "collection" ? scope.collection_id : scope.folder_id);
  const methods = catalog.data?.methods.filter(item => item.action === action) ?? [];
  useEffect(() => {
    if (browsesSavedProducts) return;
    const compatible = catalog.data?.methods.filter(item => item.action === action && item.execution === "scope");
    if (!compatible?.length || compatible.some(item => item.scopes.includes(scope.scope_type))) return;
    const kind = compatible[0].scopes[0];
    setScope(kind === "object" ? { scope_type: "object", file_id: "" } : kind === "collection" ? { scope_type: "collection", collection_id: "" } : kind === "folder" ? { scope_type: "folder", folder_id: "" } : { scope_type: "root" });
  }, [action, browsesSavedProducts, catalog.data]);
  return <Stack spacing={3} sx={{ maxWidth: 1100, mx: "auto" }}>
    <Typography component="h1" variant="h4" fontWeight={750}>Library-wide processing</Typography>
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Button component={Link} to="/research" variant="contained">Write a research report ↗</Button>
      <Button component={Link} to="/topics" variant="outlined">Topic explorer ↗</Button>
      <Button component={Link} to="/library-overview" variant="outlined">Library at a glance ↗</Button>
      <Button component={Link} disabled={catalog.data?.permissions?.run === false} to="/admin/processors">＋ Connect a processor</Button>
    </Stack>
    {catalog.isError ? <Alert severity="error">Processors could not be loaded.</Alert> : null}
    <TextField select size="small" label="Operation" value={action} onChange={event => setAction(event.target.value)} sx={{ maxWidth: 340 }}>
      {Object.entries(labels).map(([id, label]) => <MenuItem key={id} value={id}>{label}</MenuItem>)}
    </TextField>
    <LibraryFlow reads={[action === "text.read" ? "source" : "text"]} writes={outputs[action] ?? ["artifacts"]} />
    {browsesSavedProducts || methods.some(item => item.execution === "scope") ? <Card variant="outlined"><CardContent><Stack spacing={2}>
      <Typography variant="h6" fontWeight={700}>{labels[action]}</Typography>
      <ScopePicker value={scope} onChange={setScope} />
      {ready ? <ToolActionPanel key={`${action}:${JSON.stringify(scope)}`} scope={scope} action={action} /> : <Typography color="text.secondary">Choose documents, or run tools directly from a document or collection.</Typography>}
      {ready ? action === "wiki.write" ? <ScopeWikiPanel scope={scope} title="Wiki" showActions={false} /> : <ScopeEnrichmentsPanel scope={scope} showActions={false} /> : null}
    </Stack></CardContent></Card> : action === "embedding.build"
      ? <Button component={Link} to={SEARCH_INDEX_PATH} variant="contained" sx={{ alignSelf: "flex-start" }}>Open search index</Button>
      : <Button component={Link} to="/intake" variant="contained" sx={{ alignSelf: "flex-start" }}>Open Intake</Button>}
    {methods.length > 0 ? <>
      <Divider />
      <Typography variant="h6" fontWeight={700}>Available methods</Typography>
    </> : null}
    {methods.map(method => <Card key={method.id} variant="outlined"><CardContent><Stack spacing={1}>
      <Stack direction="row" justifyContent="space-between" spacing={1}><Typography fontWeight={700}>{method.label}</Typography><Chip size="small" label={method.execution === "scope" ? "Scope tool" : "Intake step"} /></Stack>
      <Typography variant="caption" color="text.secondary">{method.id} · {method.version} · {method.scopes.join(" / ")}</Typography>
      {method.source_types && <Typography variant="body2" color="text.secondary">
        {(method.source_types.file_extensions?.length ? method.source_types.file_extensions : method.source_types.media_types)?.join(", ") || "Source types undeclared"}
      </Typography>}
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>{method.outputs.map(output => <Chip key={output} size="small" label={output.replace(/_/g, " ")} />)}</Stack>
    </Stack></CardContent></Card>)}
    {!browsesSavedProducts && !catalog.isPending && !methods.length ? <Alert severity="info">Connect a compatible method in Setup.</Alert> : null}
  </Stack>;
}

export function ToolsPage() {
  const catalog = useQuery({ queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 });
  const database = useQuery({ queryKey: ["database-schema"], queryFn: getDatabaseSchema, retry: false, enabled: Boolean(catalog.data) && catalog.data?.permissions?.run !== false });
  return <Stack spacing={3} sx={{ maxWidth: 1200, mx: "auto" }}>
    <WorkbenchHome setupPath="/admin/processors" toolsOnly />
    <Card variant="outlined"><CardContent><Stack spacing={1.5}>
      <Typography variant="h6" fontWeight={700}>Library-wide processing</Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button component={Link} to="/tools/workbench" variant="outlined">Open processing workbench</Button>
        <Button component={Link} to={SEARCH_INDEX_PATH} variant="outlined">Search index</Button>
      </Stack>
    </Stack></CardContent></Card>
    {database.data?.available ? <Button component={Link} to="/admin/database" variant="outlined" sx={{ alignSelf: "start" }}>Database explorer — read-only ↗</Button> : null}
  </Stack>;
}
