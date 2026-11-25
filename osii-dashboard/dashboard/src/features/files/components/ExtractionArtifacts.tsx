import { Alert, Button, CircularProgress, Paper, Stack, Typography } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { getArtifactUrl } from "../../../api/artifacts";
import { getObjectExtractionArtifacts } from "../../../api/objects";
import { ExtractionCopyEditor } from "./ExtractionCopyEditor";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";

export function ExtractionArtifacts({ fileId, variantId, artifactId }: { fileId: string; variantId: string; artifactId?: string }) {
  const artifacts = useQuery({
    queryKey: ["objects", fileId, "extractions", variantId, "artifacts"],
    queryFn: () => getObjectExtractionArtifacts(fileId, variantId),
  });
  if (artifacts.isPending) return <CircularProgress size={20} aria-label="Loading extraction artifacts" />;
  if (artifacts.isError) return <Alert severity="warning" action={<Button onClick={() => void artifacts.refetch()}>Retry</Button>}>Could not load extraction artifacts.</Alert>;
  const entries = artifactId ? artifacts.data.artifacts.filter(artifact => artifact.id === artifactId) : artifacts.data.artifacts;
  if (!entries.length) return artifactId ? <Alert severity="info">This extraction artifact is unavailable.</Alert> : null;

  return (
    <Stack spacing={1.5} component="section" aria-label="Extraction artifacts">
      {!artifactId && <Typography variant="subtitle1" fontWeight={700}>Extraction artifacts</Typography>}
      {entries.map(artifact => (
        <Paper key={artifact.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack spacing={1}>
            <Stack direction="row" spacing={1} justifyContent="space-between" alignItems="center">
              <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>{artifact.filename} · {artifact.kind}</Typography>
              {artifact.relpath && <Button component="a" href={getArtifactUrl(artifact.relpath)} download size="small">Download</Button>}
            </Stack>
            {typeof artifact.source_origin.page === "number" && <Typography variant="caption" color="text.secondary">Source page {artifact.source_origin.page}</Typography>}
            {artifact.data != null && <>
              <EnrichmentArtifactView data={artifact.data} />
              <ExtractionCopyEditor fileId={fileId} variantId={variantId} artifactId={artifact.id} />
            </>}
          </Stack>
        </Paper>
      ))}
    </Stack>
  );
}
