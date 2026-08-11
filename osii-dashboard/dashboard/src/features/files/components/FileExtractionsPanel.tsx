import { Alert, Button, Chip, LinearProgress, Paper, Stack, Typography } from "@mui/material";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { getObjectExtractions, makeObjectExtractionPrimary } from "../../../api/objects";


export function FileExtractionsPanel({ fileId }: { fileId: string }) {
  const queryClient = useQueryClient();
  const extractions = useQuery({
    queryKey: ["objects", fileId, "extractions"],
    queryFn: () => getObjectExtractions(fileId),
  });
  const promote = useMutation({
    mutationFn: (variantId: string) => makeObjectExtractionPrimary(fileId, variantId),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "extractions"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", "detail", fileId] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "texts"] }),
        queryClient.invalidateQueries({ queryKey: ["objects", fileId, "preferred-text"] }),
      ]);
    },
  });

  if (extractions.isLoading) return <LinearProgress />;
  if (extractions.isError) return <Alert severity="error">Could not load extraction versions.</Alert>;

  return (
    <Stack spacing={1.5}>
      <Alert severity="info">
        The primary extraction supplies text to browsing and future chunking, embeddings, summaries, and enrichments. Changing it preserves every previous extraction and marks dependent search artifacts stale.
      </Alert>
      {(extractions.data?.variants ?? []).map((variant) => (
        <Paper key={variant.id} variant="outlined" sx={{ p: 1.5 }}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1.5}>
            <Stack spacing={0.25} minWidth={0}>
              <Stack direction="row" spacing={0.75} alignItems="center" flexWrap="wrap" useFlexGap>
                <Typography fontWeight={700}>{variant.extractor.name}</Typography>
                <Chip size="small" label={`v${variant.extractor.version}`} variant="outlined" />
                {variant.primary ? <Chip size="small" label="Primary" color="success" /> : null}
              </Stack>
              <Typography variant="caption" color="text.secondary">
                {variant.created_utc} · {variant.text_chars.toLocaleString()} characters · {variant.manifest_records} grounded segments
              </Typography>
              <Typography variant="caption" color="text.secondary" noWrap>{variant.id}</Typography>
            </Stack>
            {!variant.primary ? (
              <Button
                variant="outlined"
                disabled={promote.isPending}
                onClick={() => promote.mutate(variant.id)}
              >
                Make primary
              </Button>
            ) : null}
          </Stack>
        </Paper>
      ))}
      {!extractions.data?.variants.length ? <Typography color="text.secondary">No extraction is available.</Typography> : null}
      {promote.isError ? <Alert severity="error">Could not change the primary extraction.</Alert> : null}
    </Stack>
  );
}
