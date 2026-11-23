import type {FlowTestReport} from "../../../domain/processingFlowTests";
import {MenuItem, Stack, TextField, Typography} from "@mui/material";
import {useQuery} from "@tanstack/react-query";
import {apiJson} from "../../../api/client";
export type ProcessingFlow = {id: string; name: string; routes: {name: string; extensions: string[]; extractor: string; fallbacks?: string[]}[]; synthesizer_name: string; enricher_name: string; chunk_size: number; chunk_overlap: number; fingerprint: string; test?: FlowTestReport | null; build_embeddings?: boolean; editable?: boolean};
export function useProcessingFlows() {return useQuery({queryKey: ["processing-flows"], queryFn: () => apiJson<{flows: ProcessingFlow[]; default_flow_id: string}>("/api/processing-flows")});}
export function ProcessingFlowSelect({value, onChange}: {value: string; onChange: (id: string) => void}) {
  const flows = useProcessingFlows();
  const flow = flows.data?.flows.find(item => item.id === value);
  if (flows.isError) return <Typography color="error">{flows.error.message}</Typography>;
  if (!flow) return <Typography role="status">Loading processing flows…</Typography>;
  return <Stack spacing={1}><TextField select size="small" fullWidth label="Processing flow" value={value} onChange={event => onChange(event.target.value)}>{flows.data?.flows.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}</TextField><Typography variant="caption" color={flow.test?.ok ? "success.main" : "text.secondary"}>{flow.test ? `${flow.test.ok ? "Sample passed" : "Sample had errors"} · ${new Date(flow.test.tested_at).toLocaleString()}` : "Sample not tested yet · Test and configure flows in Setup"}</Typography></Stack>;
}
