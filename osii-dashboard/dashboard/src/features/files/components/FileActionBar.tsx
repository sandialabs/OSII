// src/features/files/components/FileActionBar.tsx
import { useState } from "react";
import {
  Alert,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import PsychologyOutlinedIcon from "@mui/icons-material/PsychologyOutlined";
import CollectionsBookmarkOutlinedIcon from "@mui/icons-material/CollectionsBookmarkOutlined";
import LocalOfferOutlinedIcon from "@mui/icons-material/LocalOfferOutlined";

import { useObjectSynthesisJob } from "../../../hooks/useObjectSynthesisJob";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";
import { getObjectSourceUrl } from "../../../api/source";
import { AddFileToCollectionDialog } from "../../collections/components/AddFileToCollectionDialog";
import { ManualKeywordsDialog } from "./ManualKeywordsDialog";

type FileActionBarProps = {
  fileId: string;
};

export function FileActionBar({ fileId }: FileActionBarProps) {
  const synthesisJob = useObjectSynthesisJob(fileId);
  const enrichmentJob = useEnrichmentJob();

  const [synthesizerName, setSynthesizerName] = useState("firstN");
  const [enricherName, setEnricherName] = useState("stats_keywords");
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);
  const [keywordsDialogOpen, setKeywordsDialogOpen] = useState(false);

  return (
    <>
      <Stack spacing={2}>
        <Card>
          <CardContent>
            <Stack spacing={2}>
              <Typography variant="subtitle1" fontWeight={600}>
                File Actions
              </Typography>

              <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} flexWrap="wrap" useFlexGap>
                <Button
                  variant="outlined"
                  startIcon={<OpenInNewOutlinedIcon />}
                  component="a"
                  href={getObjectSourceUrl(fileId)}
                  target="_blank"
                  rel="noreferrer"
                >
                  Open Original File
                </Button>

                <Button
                  variant="outlined"
                  startIcon={<CollectionsBookmarkOutlinedIcon />}
                  onClick={() => setCollectionDialogOpen(true)}
                >
                  Add to Collection
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<LocalOfferOutlinedIcon />}
                  onClick={() => setKeywordsDialogOpen(true)}
                >
                  Keywords
                </Button>
              </Stack>

              <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
                <Stack spacing={1} sx={{ minWidth: 220 }}>
                  <TextField
                    select
                    size="small"
                    label="Synthesizer"
                    value={synthesizerName}
                    onChange={(event) => setSynthesizerName(event.target.value)}
                  >
                    <MenuItem value="firstN">firstN</MenuItem>
                    <MenuItem value="recursive">recursive</MenuItem>
                  </TextField>

                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    onClick={() =>
                      synthesisJob.mutate({
                        synthesizer_name: synthesizerName,
                      })
                    }
                    disabled={synthesisJob.isPending}
                  >
                    Rerun Synthesis
                  </Button>
                </Stack>

                <Stack spacing={1} sx={{ minWidth: 220 }}>
                  <TextField
                    select
                    size="small"
                    label="Enricher"
                    value={enricherName}
                    onChange={(event) => setEnricherName(event.target.value)}
                  >
                    <MenuItem value="stats_keywords">stats_keywords</MenuItem>
                    <MenuItem value="noun_adjective_ngrams">noun_adjective_ngrams</MenuItem>
                    <MenuItem value="entity_candidates">entity_candidates</MenuItem>
                    <MenuItem value="llm_wiki_stub">llm_wiki_stub</MenuItem>
                  </TextField>

                  <Button
                    variant="contained"
                    color="secondary"
                    startIcon={<PsychologyOutlinedIcon />}
                    onClick={() =>
                      enrichmentJob.mutate({
                        enricher_name: enricherName,
                        scope: {
                          scope_type: "object",
                          file_id: fileId,
                        },
                        enricher_config: {},
                      })
                    }
                    disabled={enrichmentJob.isPending}
                  >
                    Run Enrichment
                  </Button>
                </Stack>
              </Stack>

              {synthesisJob.isSuccess ? (
                <Alert severity="success">
                  Synthesis job started.
                </Alert>
              ) : null}

              {synthesisJob.isError ? (
                <Alert severity="error">
                  {synthesisJob.error instanceof Error
                    ? synthesisJob.error.message
                    : "Failed to start synthesis job."}
                </Alert>
              ) : null}

              {enrichmentJob.isSuccess ? (
                <Alert severity="success">
                  Enrichment job started.
                </Alert>
              ) : null}

              {enrichmentJob.isError ? (
                <Alert severity="error">
                  {enrichmentJob.error instanceof Error
                    ? enrichmentJob.error.message
                    : "Failed to start enrichment job."}
                </Alert>
              ) : null}
            </Stack>
          </CardContent>
        </Card>
      </Stack>

      <AddFileToCollectionDialog
        open={collectionDialogOpen}
        onClose={() => setCollectionDialogOpen(false)}
        fileId={fileId}
      />
      <ManualKeywordsDialog
        open={keywordsDialogOpen}
        onClose={() => setKeywordsDialogOpen(false)}
        fileId={fileId}
      />
    </>
  );
}
