// src/features/files/components/FileSynthesesPanel.tsx
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
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";

import { getIntakeReadiness } from "../../../api/queue";
import { useObjectSyntheses } from "../../../hooks/useObjectSyntheses";
import { useObjectSynthesisJob } from "../../../hooks/useObjectSynthesisJob";

type FileSynthesesPanelProps = {
  fileId: string;
};

export function FileSynthesesPanel({ fileId }: FileSynthesesPanelProps) {
  const synthesis = useObjectSyntheses(fileId);
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
                helperText="Choose a ready synthesis method configured in Tools & services."
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
              <Alert severity="info">No synthesis method is currently ready. Start or configure one in Tools &amp; services.</Alert>
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
          <Card>
            <CardContent>
              <Stack spacing={1}>
                <Typography variant="subtitle1" fontWeight={600}>
                  Current Synthesis
                </Typography>
                <Typography variant="body2">
                  {synthesis.data.current_text ?? "No current synthesis text is available."}
                </Typography>
              </Stack>
            </CardContent>
          </Card>

          <Card>
            <CardContent>
              <Stack spacing={1}>
                <Typography variant="subtitle1" fontWeight={600}>
                  Synthesis Listing
                </Typography>

                {synthesis.data.syntheses.length > 0 ? (
                  synthesis.data.syntheses.map((item) => (
                    <Typography key={`${item.name}-${item.scope}`} variant="body2" color="text.secondary">
                      {item.name} · {item.scope}
                    </Typography>
                  ))
                ) : (
                  <Typography variant="body2" color="text.secondary">
                    No synthesis artifacts listed.
                  </Typography>
                )}
              </Stack>
            </CardContent>
          </Card>
        </>
      ) : null}
    </Stack>
  );
}
