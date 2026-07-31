import { FormEvent, useState } from "react";
import { Alert, Button, Chip, MenuItem, Paper, Stack, TextField, Typography } from "@mui/material";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { checkProcessorEndpoint, createProcessorEndpoint, listProcessorEndpoints } from "../../../api/queue";
import type { ProcessorEndpoint } from "../../../api/types";

export function ProcessorsPage() {
  const client = useQueryClient();
  const navigate = useNavigate();
  const processors = useQuery({ queryKey: ["admin", "processors"], queryFn: listProcessorEndpoints });
  const [form, setForm] = useState<Omit<ProcessorEndpoint, "id"> & { id: string }>({
    id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true,
  });
  const [message, setMessage] = useState<string | null>(null);

  const add = async (event: FormEvent) => {
    event.preventDefault();
    try {
      await createProcessorEndpoint(form);
      setMessage("Processor endpoint added.");
      setForm({ id: "", display_name: "", kind: "extractor", base_url: "http://", enabled: true });
      await client.invalidateQueries({ queryKey: ["admin", "processors"] });
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Could not add processor endpoint.");
    }
  };

  const check = async (processor: ProcessorEndpoint, test: boolean) => {
    try {
      const result = await checkProcessorEndpoint(processor.id, test);
      setMessage(`${processor.display_name}: ${result.ok ? "passed" : "failed"} — ${result.detail}`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Processor check failed.");
    }
  };

  return (
    <Stack spacing={3}>
      <Stack spacing={0.5}>
        <Typography variant="h5" fontWeight={700}>Tools</Typography>
        <Typography color="text.secondary">
          Connect optional extractors, synthesizers, embedders, and enrichers before Intake. Bundled local tools work without registration.
        </Typography>
      </Stack>
      {message ? <Alert severity={message.includes("failed") || message.includes("Could not") ? "error" : "info"}>{message}</Alert> : null}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={1.25}>
          <Typography fontWeight={700}>How to connect an external tool</Typography>
          <Typography variant="body2">
            1. Start the processor service and confirm that its base URL is reachable from the OSII API.
          </Typography>
          <Typography variant="body2">
            2. Add that base URL below. Do not include <code>/health</code> or <code>/v1</code> in the URL.
          </Typography>
          <Typography variant="body2">
            3. Select <strong>Health</strong> to check connectivity, then <strong>Test</strong> to validate its descriptor and operation contract.
          </Typography>
          <Typography variant="body2">
            4. Return to Intake and select <strong>Retest tools</strong>. The processor will then appear in readiness and routing choices supported by the core.
          </Typography>
          <Alert severity="info">
            With <code>make dev</code>, a service running on this computer normally uses a URL such as <code>http://127.0.0.1:8091</code>. From the packaged container stack, use its Compose service name or <code>host.containers.internal</code> when calling a service on the host.
          </Alert>
          <Typography variant="caption" color="text.secondary">
            Registration and Test validate every processor kind. Remote enrichers are currently the fully integrated external execution path; adapters that commit external extractor, synthesizer, and embedder results are still being completed.
          </Typography>
          <Button variant="outlined" onClick={() => navigate("/intake")} sx={{ alignSelf: "flex-start" }}>
            Return to Intake
          </Button>
        </Stack>
      </Paper>

      <Paper component="form" onSubmit={(event) => void add(event)} variant="outlined" sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Stack spacing={0.25}>
            <Typography fontWeight={700}>Add a processor endpoint</Typography>
            <Typography variant="body2" color="text.secondary">
              The service must implement OSII Processor API v1: <code>/health</code>, <code>/v1/descriptor</code>, and one operation endpoint for its kind.
            </Typography>
          </Stack>
          <Stack direction={{ xs: "column", md: "row" }} spacing={1}>
            <TextField label="ID" required value={form.id} onChange={(event) => setForm({ ...form, id: event.target.value })} />
            <TextField label="Display name" required fullWidth value={form.display_name} onChange={(event) => setForm({ ...form, display_name: event.target.value })} />
            <TextField select label="Kind" value={form.kind} onChange={(event) => setForm({ ...form, kind: event.target.value as ProcessorEndpoint["kind"] })} sx={{ minWidth: 150 }}>
              {["extractor", "synthesizer", "embedder", "enricher"].map((kind) => <MenuItem key={kind} value={kind}>{kind}</MenuItem>)}
            </TextField>
          </Stack>
          <TextField label="Base URL" required fullWidth value={form.base_url} onChange={(event) => setForm({ ...form, base_url: event.target.value })} placeholder="http://127.0.0.1:8091" helperText="Base address only; OSII appends the health, descriptor, and operation paths." />
          <Button type="submit" variant="contained" sx={{ alignSelf: "flex-start" }}>Add processor</Button>
        </Stack>
      </Paper>

      <Stack spacing={1.5}>
        {(processors.data?.processors ?? []).map((processor) => (
          <Paper key={processor.id} variant="outlined" sx={{ p: 2 }}>
            <Stack direction={{ xs: "column", md: "row" }} spacing={1.5} justifyContent="space-between">
              <Stack spacing={0.5}>
                <Stack direction="row" spacing={1} alignItems="center"><Typography fontWeight={700}>{processor.display_name}</Typography><Chip size="small" label={processor.kind} /></Stack>
                <Typography variant="body2" color="text.secondary">{processor.base_url}</Typography>
              </Stack>
              <Stack direction="row" spacing={1}><Button variant="outlined" onClick={() => void check(processor, false)}>Health</Button><Button variant="contained" onClick={() => void check(processor, true)}>Test</Button></Stack>
            </Stack>
          </Paper>
        ))}
        {!processors.isLoading && !(processors.data?.processors.length) ? <Alert severity="info">No external processors are registered.</Alert> : null}
      </Stack>
    </Stack>
  );
}
