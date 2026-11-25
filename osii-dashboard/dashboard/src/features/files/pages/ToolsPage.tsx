import { Alert, Button, Card, CardActionArea, CardContent, LinearProgress, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getDatabaseSchema } from "../../../api/database";
import { getToolCatalog } from "../../../api/tools";
import { buildScopeProcessorRoute, READ_FILES_PATH, SEARCH_INDEX_PATH, SUGGEST_METADATA_PATH, SUMMARIZE_FILE_PATH } from "../../../utils/routes";
import { WorkbenchHome } from "../../home/components/WorkbenchHome";

const processingTools = [
  { label: "Read files", path: READ_FILES_PATH },
  { label: "Create a summary", path: SUMMARIZE_FILE_PATH },
  { label: "Suggest metadata", path: SUGGEST_METADATA_PATH },
  { label: "Search index", path: SEARCH_INDEX_PATH },
];

export function ToolsPage() {
  const catalog = useQuery({ queryKey: ["tool-catalog"], queryFn: getToolCatalog, staleTime: 30_000 });
  const database = useQuery({ queryKey: ["database-schema"], queryFn: getDatabaseSchema, retry: false,
    enabled: Boolean(catalog.data) && catalog.data?.permissions?.run !== false });
  const discovered = (catalog.data?.methods ?? []).filter(method =>
    method.execution === "scope" && !["wiki.write", "metadata.suggest"].includes(method.action))
    .map(method => ({ label: method.label, path: buildScopeProcessorRoute(method.id) }));
  return <Stack spacing={2.5} sx={{ maxWidth: 1200, mx: "auto" }}>
    <WorkbenchHome setupPath="/intake" toolsOnly />
    <Stack component="section" spacing={1} aria-labelledby="processing-tools">
      <Typography id="processing-tools" component="h2" variant="h6" fontWeight={700}>Processing tools</Typography>
      <Stack sx={{ display: "grid", gridTemplateColumns: { xs: "1fr", sm: "repeat(auto-fit, minmax(220px, 1fr))" } }} gap={1}>
        {[...processingTools, ...discovered].map(tool => <Card key={tool.path} variant="outlined">
          <CardActionArea component={Link} to={tool.path} sx={{ height: "100%" }}>
            <CardContent sx={{ py: 1.25 }}><Typography fontWeight={650}>{tool.label}</Typography></CardContent>
          </CardActionArea>
        </Card>)}
      </Stack>
      {catalog.isPending && <LinearProgress aria-label="Loading processor tools" />}
      {catalog.isError && <Alert severity="warning" action={<Button onClick={() => void catalog.refetch()}>Retry</Button>}>Could not load registered processors.</Alert>}
    </Stack>
    {database.data?.available && <Button component={Link} to="/admin/database" variant="outlined" sx={{ alignSelf: "start" }}>Database explorer</Button>}
  </Stack>;
}
