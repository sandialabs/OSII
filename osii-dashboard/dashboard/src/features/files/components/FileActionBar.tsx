// src/features/files/components/FileActionBar.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
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
import DeleteOutlineOutlinedIcon from "@mui/icons-material/DeleteOutlineOutlined";
import { useNavigate } from "react-router-dom";

import { useObjectSynthesisJob } from "../../../hooks/useObjectSynthesisJob";
import { useEnrichmentJob } from "../../../hooks/useEnrichmentJob";
import { getObjectSourceUrl } from "../../../api/source";
import { getIntakeReadiness } from "../../../api/queue";
import { AddFileToCollectionDialog } from "../../collections/components/AddFileToCollectionDialog";
import { ManualKeywordsDialog } from "./ManualKeywordsDialog";
import { DeleteObjectDialog } from "./DeleteObjectDialog";

type FileActionBarProps = {
  fileId: string;
};

export function FileActionBar({ fileId }: FileActionBarProps) {
  const navigate = useNavigate();
  const synthesisJob = useObjectSynthesisJob(fileId);
  const enrichmentJob = useEnrichmentJob();

  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const [synthesizerName, setSynthesizerName] = useState("");
  const [enricherName, setEnricherName] = useState("stats_keywords");
  const [collectionDialogOpen, setCollectionDialogOpen] = useState(false);
  const [keywordsDialogOpen, setKeywordsDialogOpen] = useState(false);
  const [deleteDialogOpen, setDeleteDialogOpen] = useState(false);
  const synthesizerOptions = (readiness.data?.synthesizers ?? []).filter(
    (item) => item.available && !["firstN", "firstN_folder", "collection_firstn"].includes(item.id),
  );
  const selectedSynthesizer = synthesizerName
    || synthesizerOptions.find((item) => item.id === readiness.data?.defaults.synthesizer)?.id
    || synthesizerOptions[0]?.id
    || "";

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
                  Labels & Tags
                </Button>
                <Button
                  variant="outlined"
                  color="error"
                  startIcon={<DeleteOutlineOutlinedIcon />}
                  onClick={() => setDeleteDialogOpen(true)}
                >
                  Delete File Data
                </Button>
              </Stack>

              <Stack direction={{ xs: "column", lg: "row" }} spacing={2}>
                <Stack spacing={1} sx={{ minWidth: 220 }}>
                  <TextField
                    select
                    size="small"
                    label="Synthesizer"
                    value={selectedSynthesizer}
                    onChange={(event) => setSynthesizerName(event.target.value)}
                  >
                    {synthesizerOptions.map((item) => (
                      <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
                    ))}
                  </TextField>

                  <Button
                    variant="contained"
                    startIcon={<AutoAwesomeOutlinedIcon />}
                    onClick={() =>
                      synthesisJob.mutate({
                        synthesizer_name: selectedSynthesizer,
                      })
                    }
                    disabled={synthesisJob.isPending || !selectedSynthesizer}
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
      <DeleteObjectDialog
        open={deleteDialogOpen}
        onClose={() => setDeleteDialogOpen(false)}
        onDeleted={() => navigate("/files")}
        fileId={fileId}
      />
    </>
  );
}
