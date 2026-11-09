import { ToolActionPanel } from "./ToolActionPanel";
import { WikiProductEditor } from "./WikiProductEditor";
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import {
  Alert, Button, Card, CardContent, CircularProgress, Dialog, DialogActions,
  DialogContent, DialogTitle, Stack, Typography,
} from "@mui/material";
import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteScopeEnrichment } from "../../../api/enrichments";
import type { EnrichmentListEntryFile, ScopeDescribeRequest } from "../../../api/types";
import { useScopeEnrichments } from "../../../hooks/useScopeEnrichments";

function WikiArtifactCard({ scope, entry }: {
  scope: ScopeDescribeRequest;
  entry: EnrichmentListEntryFile;
}) {
  const queryClient = useQueryClient();
  const [deleteOpen, setDeleteOpen] = useState(false);

  const remove = useMutation({
    mutationFn: () => deleteScopeEnrichment({ scope, filename: entry.name }),
    onSuccess: async () => {
      setDeleteOpen(false);
      await queryClient.invalidateQueries({ queryKey: ["enrichments"] });
    },
  });

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={1.5}>
          <Stack direction={{ xs: "column", sm: "row" }} justifyContent="space-between" spacing={1}>
            <Stack spacing={0.25}>
              <Typography fontWeight={700}>{entry.title || entry.name.replace(/\.json$/i, "")}</Typography>
              <Typography variant="caption" color="text.secondary">
                Wiki
              </Typography>
            </Stack>
            <Button color="error" size="small" startIcon={<DeleteOutlineOutlinedIcon />} onClick={() => setDeleteOpen(true)} sx={{ alignSelf: "flex-start" }}>
              Delete
            </Button>
          </Stack>
          <WikiProductEditor scope={scope} filename={entry.name} />
          {remove.isError ? <Alert severity="error">The saved wiki could not be deleted.</Alert> : null}
        </Stack>
      </CardContent>
      <Dialog open={deleteOpen} onClose={() => setDeleteOpen(false)} fullWidth maxWidth="xs">
        <DialogTitle>Delete this wiki?</DialogTitle>
        <DialogContent dividers>
          <Typography variant="body2">
            This removes only the selected derived artifact and its metadata. Extracted text,
            collection members, and original files are unchanged.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteOpen(false)}>Keep wiki</Button>
          <Button color="error" variant="contained" disabled={remove.isPending} onClick={() => remove.mutate()}>
            {remove.isPending ? "Deleting…" : "Delete wiki"}
          </Button>
        </DialogActions>
      </Dialog>
    </Card>
  );
}

export function ScopeWikiPanel({ scope, title, showActions = true }: {
  scope: ScopeDescribeRequest;
  title: string;
  showActions?: boolean;
}) {
  const enrichments = useScopeEnrichments(scope);
  const wikiEntries = (enrichments.data?.enrichments ?? []).filter(
    (entry): entry is EnrichmentListEntryFile => entry.kind === "file" && entry.artifact_type === "wiki_markdown",
  );
  return (
    <Stack spacing={2}>
      {showActions ? <ToolActionPanel scope={scope} action="wiki.write" title={title} /> : null}
      {enrichments.isLoading ? <CircularProgress size={22} /> : null}
      {enrichments.isError ? <Alert severity="warning">Saved wikis could not be listed.</Alert> : null}
      {wikiEntries.map((entry) => <WikiArtifactCard key={entry.name} scope={scope} entry={entry} />)}
      {!enrichments.isLoading && wikiEntries.length === 0 ? (
        <Alert severity="info">No wiki yet. Choose a method above to create one.</Alert>
      ) : null}
    </Stack>
  );
}
