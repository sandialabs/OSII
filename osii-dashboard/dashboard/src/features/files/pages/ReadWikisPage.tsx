import { Alert, Button, LinearProgress, List, ListItemButton, ListItemText, Paper, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { listEnrichments } from "../../../api/enrichments";
import { listProcessingRuns } from "../../../api/queue";
import { listCollectionScopes } from "../../../api/scopes";
import type { EnrichmentListEntryFile, ScopeDescribeRequest } from "../../../api/types";
import { ScopePicker } from "../../../components/discovery/ScopePicker";
import { buildWikiRoute, CREATE_WIKI_PATH, READ_WIKIS_PATH, wikiRouteScope, wikiRunRoute } from "../../../utils/routes";
import { WikiProductEditor } from "../components/WikiProductEditor";

function RecentWikis() {
  const runs = useQuery({ queryKey: ["processing-runs"], queryFn: listProcessingRuns });
  const wikis = new Map<string, NonNullable<typeof runs.data>["runs"][number]>();
  for (const run of runs.data?.runs ?? []) {
    const route = wikiRunRoute(run);
    if (route && !wikis.has(route)) wikis.set(route, run);
  }
  const collections = useQuery({
    queryKey: ["scopes", "collections"], queryFn: listCollectionScopes,
    enabled: [...wikis.values()].some(run => run.scope?.scope_type === "collection"),
  });
  if (runs.isPending) return <LinearProgress aria-label="Loading recent wikis" />;
  if (runs.isError) return <Alert severity="warning" action={<Button onClick={() => void runs.refetch()}>Retry</Button>}>Recent wikis could not be loaded.</Alert>;
  if (!wikis.size) return <Typography color="text.secondary">No recent wiki runs. Choose where to look for saved wikis.</Typography>;
  return <Paper variant="outlined">
    <Typography component="h2" variant="subtitle1" fontWeight={700} sx={{ px: 2, pt: 1 }}>Recent wikis</Typography>
    <List dense>
      {[...wikis].slice(0, 10).map(([route, run]) => {
        const scope = run.scope;
        const collection = scope?.scope_type === "collection"
          ? collections.data?.scopes.find(item => item.collection_id === scope.collection_id)?.label
          : undefined;
        const location = collection ?? (scope?.scope_type === "root" ? "Library"
          : scope?.scope_type === "folder" ? "Folder" : scope?.scope_type === "object" ? "Document" : "Collection");
        return <ListItemButton key={route} component={Link} to={route}>
          <ListItemText primary={location} secondary={`${run.tool_label ?? "Wiki"} · ${new Date(run.finished_at ?? run.created_at).toLocaleString()}`} />
        </ListItemButton>;
      })}
    </List>
  </Paper>;
}

function ScopeWikis({ scope, search }: { scope: ScopeDescribeRequest; search: URLSearchParams }) {
  const ready = scope.scope_type === "root" || Boolean(scope.scope_type === "object" ? scope.file_id
    : scope.scope_type === "folder" ? scope.folder_id : scope.collection_id);
  const list = useQuery({
    queryKey: ["enrichments", "scope", scope], queryFn: () => listEnrichments(scope), enabled: ready,
  });
  if (!ready) return null;
  if (list.isPending) return <LinearProgress aria-label="Loading saved wikis" />;
  if (list.isError) return <Alert severity="error" action={<Button onClick={() => void list.refetch()}>Retry</Button>}>Saved wikis could not be loaded.</Alert>;
  const wikis = list.data.enrichments.filter(
    (entry): entry is EnrichmentListEntryFile => entry.kind === "file" && entry.artifact_type === "wiki_markdown",
  );
  const filename = search.get("file");
  const method = search.get("method");
  const selected = filename ? wikis.find(wiki => wiki.name === filename)
    : wikis.find(wiki => wiki.name === `wiki--${method}.json`) ?? (wikis.length === 1 ? wikis[0] : undefined);
  if (!wikis.length) return <Typography color="text.secondary">No saved wikis here.</Typography>;
  return <>
    {filename && !selected && <Alert severity="warning">This wiki is no longer available here.</Alert>}
    {(!selected || wikis.length > 1) && <Paper variant="outlined"><List dense aria-label="Saved wikis">
      {wikis.map(wiki => <ListItemButton key={wiki.name} component={Link} selected={wiki === selected}
        to={buildWikiRoute(READ_WIKIS_PATH, scope, { file: wiki.name })}>
        <ListItemText primary={wiki.title || wiki.name} />
      </ListItemButton>)}
    </List></Paper>}
    {selected && <WikiProductEditor scope={scope} filename={selected.name} />}
  </>;
}

export function ReadWikisPage() {
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const scope = wikiRouteScope(search);
  return <Stack spacing={1.5} sx={{ maxWidth: 960 }}>
    <Stack direction="row" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
      <Typography component="h1" variant="h5" fontWeight={750}>Wikis</Typography>
      <Stack direction="row" spacing={1}>
        {scope && <Button component={Link} to={READ_WIKIS_PATH}>Recent wikis</Button>}
        <Button component={Link} to={buildWikiRoute(CREATE_WIKI_PATH, scope)} variant="outlined">Create a wiki</Button>
      </Stack>
    </Stack>
    <ScopePicker value={scope ?? { scope_type: "collection", collection_id: "" }}
      onChange={next => navigate(buildWikiRoute(READ_WIKIS_PATH, next))} />
    {scope ? <ScopeWikis scope={scope} search={search} /> : <RecentWikis />}
  </Stack>;
}
