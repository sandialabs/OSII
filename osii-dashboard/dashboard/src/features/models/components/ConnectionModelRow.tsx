import {Alert, Button, Stack, Typography} from "@mui/material";
import {ModelPicker, type ModelOption} from "./ModelPicker";
export type ModelTestResult = {ok: boolean; detail?: string; dimensions?: number};
/** Keep a model's selection, test action and outcome together. */
export function ConnectionModelRow({label, help, value, options, busy, result, onChange, onTest}: {
  label: string; help: string; value: string; options: ModelOption[]; busy: boolean;
  result?: ModelTestResult; onChange: (model: string) => void; onTest: () => void;
}) {
  return <Stack spacing={0.5}>
    <Stack direction="row" spacing={1} alignItems="flex-start"><Stack sx={{flex: 1, minWidth: 0}}><ModelPicker label={label} value={value} options={options} onChange={onChange} disabled={busy} helperText={help} /></Stack><Button variant="outlined" aria-label={`Test ${label.toLowerCase()}`} disabled={busy || !value} onClick={onTest} sx={{mt: 1}}>Test</Button></Stack>
    {result?.ok && <Typography variant="caption" color="success.main" role="status">✓ Verified{result.dimensions ? ` · ${result.dimensions.toLocaleString()} dimensions` : ""}</Typography>}
    {result && !result.ok && <Alert severity="error" sx={{overflowWrap: "anywhere", whiteSpace: "pre-wrap"}}>{result.detail || "Model test failed."}</Alert>}
  </Stack>;
}
