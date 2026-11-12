import { SuggestedMetadata } from "./SuggestedMetadata";
import { DerivedProductEditor } from "./DerivedProductEditor";
// src/features/files/components/FileSynthesesPanel.tsx
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Accordion, AccordionSummary, AccordionDetails,
  Alert,
  Button,
  Card,
  CardContent,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import ExpandMoreOutlinedIcon from "@mui/icons-material/ExpandMoreOutlined";
import { apiJson } from "../../../api/client";
import { getIntakeReadiness } from "../../../api/queue";
import { useObjectSyntheses } from "../../../hooks/useObjectSyntheses";
import { useObjectSynthesisJob } from "../../../hooks/useObjectSynthesisJob";

type FileSynthesesPanelProps = {
  fileId: string;
};

export function FileSynthesesPanel({ fileId }: FileSynthesesPanelProps) {
  const synthesis = useObjectSyntheses(fileId);
  const variants = useQuery({ queryKey: ["products", "list", fileId], queryFn: () => apiJson<{ products: { family: string; filename: string; title: string }[] }>("/api/products/list", { method: "POST", json: { scope_type: "object", file_id: fileId } }) });
  const synthesisJob = useObjectSynthesisJob(fileId);
  const readiness = useQuery({ queryKey: ["intake", "readiness"], queryFn: getIntakeReadiness });
  const [synthesizerName, setSynthesizerName] = useState("");
  const synthesizerOptions = (readiness.data?.synthesizers ?? []).filter(
    (item) => item.available && !["firstN", "firstN_folder", "collection_firstn"].includes(item.id),
  );
  const selectedSynthesizer = synthesizerName
    || synthesizerOptions.find((item) => item.id === readiness.data?.defaults.synthesizer)?.id
    || synthesizerOptions[0]?.id
    || "";

  return (
    <Stack spacing={2}>
      <Card variant="outlined">
        <CardContent>
          <Stack spacing={1.5}>
            <Stack spacing={0.25}>
              <Typography variant="subtitle1" fontWeight={700}>Generate a synthesis</Typography>
              <Typography variant="body2" color="text.secondary">
                Synthesis uses the current primary extraction to create a separate cited preview or model-generated summary. It does not alter extracted text.
              </Typography>
            </Stack>
            <Stack direction={{ xs: "column", sm: "row" }} spacing={1.5} alignItems={{ sm: "flex-start" }}>
              <TextField
                select
                size="small"
                label="Synthesizer"
                value={selectedSynthesizer}
                onChange={(event) => setSynthesizerName(event.target.value)}
                sx={{ minWidth: 280 }}
                helperText="Choose a ready synthesis method configured in Setup."
              >
                {synthesizerOptions.map((item) => (
                  <MenuItem key={item.id} value={item.id}>{item.display_name}</MenuItem>
                ))}
              </TextField>
              <Button
                variant="contained"
                startIcon={<AutoAwesomeOutlinedIcon />}
                onClick={() => synthesisJob.mutate({ synthesizer_name: selectedSynthesizer })}
                disabled={synthesisJob.isPending || !selectedSynthesizer}
              >
                {synthesisJob.isPending ? "Starting…" : "Run synthesis"}
              </Button>
            </Stack>
            {!readiness.isLoading && !synthesizerOptions.length ? (
              <Alert severity="info">No synthesis method is currently ready. Start or configure one in Setup.</Alert>
            ) : null}
            {synthesisJob.isSuccess ? <Alert severity="success">Synthesis job started.</Alert> : null}
            {synthesisJob.isError ? (
              <Alert severity="error">
                {synthesisJob.error instanceof Error ? synthesisJob.error.message : "Failed to start synthesis job."}
              </Alert>
            ) : null}
          </Stack>
        </CardContent>
      </Card>

      {synthesis.isLoading ? <Typography>Loading syntheses…</Typography> : null}
      {synthesis.isError ? (
        <Alert severity="warning">
          Failed to load syntheses.
          {synthesis.error instanceof Error ? ` ${synthesis.error.message}` : ""}
        </Alert>
      ) : null}
      {!synthesis.isLoading && !synthesis.isError && !synthesis.data ? <Alert severity="info">No synthesis data available.</Alert> : null}
      {synthesis.data ? (
        <>
          <SuggestedMetadata metadata={synthesis.data.document_metadata} fileId={fileId} />
          {synthesis.data.current_text != null ? <DerivedProductEditor scope={{ scope_type: "object", file_id: fileId }} filename="current" family="synthesis" /> : <Typography>No summary yet.</Typography>}

          {variants.data?.products.filter(item => item.family === "synthesis" && item.filename !== "current").map(item => <Accordion key={item.filename} variant="outlined" disableGutters><AccordionSummary expandIcon={<ExpandMoreOutlinedIcon />}><Typography fontWeight={650}>{item.title}</Typography></AccordionSummary><AccordionDetails><DerivedProductEditor scope={{ scope_type: "object", file_id: fileId }} filename={item.filename} family="synthesis" /></AccordionDetails></Accordion>)}

        </>
      ) : null}
    </Stack>
  );
}
