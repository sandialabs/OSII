import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import { Alert, Button, Chip, CircularProgress, Paper, Stack, Typography } from "@mui/material";

import type { ScopeDescribeRequest } from "../../api/types";
import { useEnrichmentJob } from "../../hooks/useEnrichmentJob";
import { useScopeKeywordSuggestions } from "../../hooks/useScopeKeywordSuggestions";

export function ScopeSuggestions({
  scope,
  mode = "keywords",
  compact = false,
  onSelect,
}: {
  scope: ScopeDescribeRequest;
  mode?: "keywords" | "questions";
  compact?: boolean;
  onSelect: (value: string) => void;
}) {
  const suggestions = useScopeKeywordSuggestions(scope);
  const enrichment = useEnrichmentJob();
  const values = mode === "questions" ? suggestions.questions : suggestions.keywords;

  const generate = () => enrichment.mutate({
    enricher_name: "noun_adjective_ngrams",
    scope,
    enricher_config: { top_k: 20 },
  });

  return (
    <Paper variant="outlined" sx={{ p: compact ? 1.25 : 2 }}>
      <Stack spacing={1.25}>
        <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" alignItems={{ xs: "flex-start", sm: "center" }} spacing={1}>
          <Stack spacing={0.2}>
            <Typography variant={compact ? "subtitle2" : "subtitle1"} fontWeight={700}>
              {mode === "questions" ? "Suggested questions" : "Explore by keyword"}
            </Typography>
            {!compact ? <Typography variant="body2" color="text.secondary">
              {suggestions.hasSnapshot
                ? "Suggestions come from the saved noun/adjective 2–4-gram snapshot for this scope."
                : "Generate a small, model-free statistical snapshot to reveal recurring subject phrases."}
            </Typography> : null}
          </Stack>
          {!suggestions.hasSnapshot ? (
            <Button size="small" variant="outlined" startIcon={<AutoAwesomeOutlinedIcon />} onClick={generate} disabled={enrichment.isPending}>
              {enrichment.isPending ? "Starting…" : "Generate keyword snapshot"}
            </Button>
          ) : null}
        </Stack>

        {suggestions.isLoading ? <CircularProgress size={18} /> : null}
        <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
          {values.map((value) => (
            <Chip
              key={value}
              icon={mode === "keywords" ? <SearchOutlinedIcon /> : undefined}
              label={value}
              clickable
              variant="outlined"
              onClick={() => onSelect(value)}
              sx={mode === "questions" ? { height: "auto", "& .MuiChip-label": { whiteSpace: "normal", py: 0.75 } } : undefined}
            />
          ))}
        </Stack>
        {mode === "keywords" && values.length === 0 && !suggestions.isLoading ? (
          <Typography variant="body2" color="text.secondary">No keyword snapshot is available yet.</Typography>
        ) : null}
        {enrichment.isSuccess ? <Alert severity="success">Keyword snapshot generation started. Suggestions will appear when processing finishes.</Alert> : null}
        {suggestions.isError ? <Alert severity="warning">Saved keyword suggestions could not be loaded.</Alert> : null}
        {enrichment.isError ? <Alert severity="error">{enrichment.error instanceof Error ? enrichment.error.message : "Could not start keyword generation."}</Alert> : null}
      </Stack>
    </Paper>
  );
}
