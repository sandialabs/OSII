import { useState } from "react";
import { Alert, Button, LinearProgress, Stack, TextField, MenuItem, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { getToolCatalog, type ToolMethod } from "../../../api/tools";
import { createProcessingRun } from "../../../api/queue";
import type { ScopeDescribeRequest } from "../../../api/types";
import type { PickedFile } from "../../../components/discovery/LocationBrowser";
import { ScopePicker } from "../../../components/discovery/ScopePicker";
import { LibraryFlow } from "../../../components/workbench/LibraryFlow";
import { PageBreadcrumbs } from "../../../components/workbench/PageBreadcrumbs";
import { useObjectSynthesisJob } from "../../../hooks/useObjectSynthesisJob";
import { buildRunRoute, buildWikiRoute, READ_WIKIS_PATH, wikiRouteScope } from "../../../utils/routes";
import { FileSelectionPanel } from "../../queue/components/FileSelectionPanel";
import { useProcessingFlows } from "../../queue/components/ProcessingFlowSelect";
import { ScopeEnrichmentsPanel } from "../components/ScopeEnrichmentsPanel";
import { SuggestedMetadata } from "../components/SuggestedMetadata";
import { ToolActionPanel } from "../components/ToolActionPanel";

const scopeTypes = ["collection", "folder", "object", "root"] as const;
const toEmptyScope: Record<ScopeDescribeRequest["scope_type"], ScopeDescribeRequest> = {
  collection: { scope_type: "collection", collection_id: "" },
  folder: { scope_type: "folder", folder_id: "" },
  object: { scope_type: "object", file_id: "" },
  root: { scope_type: "root" },
};
const catalogQuery = { queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 };

function ScopeProcess({ title, action, methods, methodId }: {
  title: string; action: string; methods: ToolMethod[]; methodId?: string;
}) {
  const wiki = action === "wiki.write";
  const metadata = action === "metadata.suggest";
  const matchingScopes = scopeTypes.filter(type => methods.some(method => method.scopes.includes(type)));
  const allowed = matchingScopes.length ? matchingScopes : metadata ? ["object" as const] : [...scopeTypes];
  const [search] = useSearchParams();
  const [selection, setSelection] = useState(() => wiki ? wikiRouteScope(search) : undefined);
  const scope = selection && allowed.includes(selection.scope_type) ? selection : toEmptyScope[allowed[0]];
  const ready = scope.scope_type === "root" || Boolean(scope.scope_type === "object" ? scope.file_id
    : scope.scope_type === "collection" ? scope.collection_id : scope.folder_id);

  return <Stack spacing={2} sx={{ maxWidth: 1000 }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" gap={1} flexWrap="wrap">
      <Typography component="h1" variant="h5" fontWeight={750}>{title}</Typography>
      {wiki && <Button component={Link} to={buildWikiRoute(READ_WIKIS_PATH, ready ? scope : undefined)}>Saved wikis</Button>}
    </Stack>
    <LibraryFlow reads={["text"]} writes={metadata ? ["metadata"] : ["artifacts"]} />
    <ScopePicker value={scope} onChange={setSelection} allowedTypes={allowed} />
    {methods.length === 0 && <Alert severity="info" action={<Button component={Link} to="/admin/processors">Setup</Button>}>
      Connect a {wiki ? "wiki" : "metadata"} processor to run this tool.
    </Alert>}
    {ready && methods.length > 0 && <ToolActionPanel key={JSON.stringify(scope)} scope={scope} action={action} methodId={methodId} compact />}
    {ready && metadata && scope.scope_type === "object" && <SuggestedMetadata fileId={scope.file_id} />}
    {ready && methodId && <ScopeEnrichmentsPanel scope={scope} showActions={false}
      filter={product => product.family === "enrichment" && product.filename.endsWith(`--${methodId}.json`)} />}
  </Stack>;
}

function ScopeActionPage({ title, action }: { title: string; action: string }) {
  const catalog = useQuery(catalogQuery);
  if (catalog.isPending) return <LinearProgress aria-label="Loading processors" />;
  if (catalog.isError) return <Alert severity="error" action={<Button onClick={() => void catalog.refetch()}>Retry</Button>}>Could not load processors.</Alert>;
  return <ScopeProcess title={title} action={action}
    methods={catalog.data.methods.filter(method => method.execution === "scope" && method.action === action)} />;
}

export function CreateWikiPage() {
  return <ScopeActionPage title="Create a wiki" action="wiki.write" />;
}

export function SuggestMetadataPage() {
  return <ScopeActionPage title="Suggest metadata" action="metadata.suggest" />;
}

export function ScopeProcessorPage() {
  const { methodId } = useParams();
  const catalog = useQuery(catalogQuery);
  const method = catalog.data?.methods.find(item => item.execution === "scope" && item.id === methodId);
  return <Stack spacing={1.5}>
    <PageBreadcrumbs parents={[{ label: "Toolbox", to: "/tools" }]} current={method?.label ?? "Processor"} />
    {catalog.isPending ? <LinearProgress aria-label="Loading processor" />
      : catalog.isError ? <Alert severity="error" action={<Button onClick={() => void catalog.refetch()}>Retry</Button>}>Could not load the processor.</Alert>
      : method ? <ScopeProcess key={method.id} title={method.label} action={method.action} methods={[method]} methodId={method.id} />
      : <Alert severity="info" action={<Button component={Link} to="/admin/processors">Setup</Button>}>This processor is unavailable.</Alert>}
  </Stack>;
}

export function ReadFilesPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const [files, setFiles] = useState<PickedFile[]>([]);
  const job = useMutation({
    mutationFn: () => createProcessingRun({ queue_paths: files.map(file => file.path), include_subfolders: false,
      run_extraction: true, extract_mode: "missing", build_embeddings: false }),
    onSuccess: run => {
      void client.invalidateQueries({ queryKey: ["processing-runs"] });
      navigate(buildRunRoute(run.id));
    },
  });
  return <Stack spacing={2} sx={{ maxWidth: 900 }}>
    <Typography component="h1" variant="h5" fontWeight={750}>Read files</Typography>
    <LibraryFlow reads={["source"]} writes={["text", "artifacts"]} />
    <FileSelectionPanel files={files} onFiles={setFiles} />
    {job.error && <Alert severity="error">{job.error.message}</Alert>}
    <Button variant="contained" sx={{ alignSelf: "flex-start" }} disabled={!files.length || job.isPending} onClick={() => job.mutate()}>
      {job.isPending ? "Starting…" : files.length ? `Read ${files.length} ${files.length === 1 ? "file" : "files"}` : "Read files"}
    </Button>
  </Stack>;
}

export function SummarizeFilePage() {
  const navigate = useNavigate();
  const [scope, setScope] = useState<ScopeDescribeRequest>(toEmptyScope.object);
  const [selected, setSelected] = useState("");
  const catalog = useQuery(catalogQuery);
  const flows = useProcessingFlows();
  const fileId = scope.scope_type === "object" ? scope.file_id : "";
  const methods = catalog.data?.methods.filter(item => item.action === "summary.write" && item.scopes.includes("object")) ?? [];
  const preferred = flows.data?.flows.find(flow => flow.id === "bundled")?.synthesizer_name;
  const method = methods.find(item => item.id === selected) ?? methods.find(item => item.id === preferred) ?? methods[0];
  const job = useObjectSynthesisJob(fileId);
  return <Stack spacing={2} sx={{ maxWidth: 900 }}>
    <Typography component="h1" variant="h5" fontWeight={750}>Create a summary</Typography>
    <LibraryFlow reads={["text"]} writes={["summaries", "metadata"]} />
    <ScopePicker value={scope} onChange={setScope} allowedTypes={["object"]} />
    {catalog.isPending && <LinearProgress aria-label="Loading summarizers" />}
    {catalog.error && <Alert severity="error">{catalog.error.message}</Alert>}
    {catalog.isSuccess && !method && <Alert severity="info" action={<Button component={Link} to="/admin/processors">Setup</Button>}>
      Connect a summarizer to run this tool.
    </Alert>}
    {method && <Stack direction={{ xs: "column", sm: "row" }} alignItems={{ sm: "center" }} spacing={1}>
      <TextField select size="small" label="Method" value={method.id} onChange={event => setSelected(event.target.value)} sx={{ minWidth: 230 }}>
        {methods.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <Button variant="contained" disabled={!fileId || job.isPending || catalog.data?.permissions?.run === false}
        onClick={() => job.mutate({ synthesizer_name: method.id }, { onSuccess: run => navigate(buildRunRoute(run.run_id)) })}>
        {job.isPending ? "Starting…" : "Create summary"}
      </Button>
    </Stack>}
    {job.error && <Alert severity="error">{job.error.message}</Alert>}
    {fileId && <ScopeEnrichmentsPanel scope={scope} showActions={false} filter={product => product.family === "synthesis"} />}
  </Stack>;
}
