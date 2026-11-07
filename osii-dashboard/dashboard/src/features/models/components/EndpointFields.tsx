import { Stack, TextField } from "@mui/material";

/** Transport-free endpoint fields shared by local Setup and hosted administration. */
export function EndpointFields({ baseUrl, onBaseUrl, apiKey, onApiKey, credentialPresent = false,
  credentialHelp, credentialWritable = true, showCredential = true, urlHelp, required = false }: {
  baseUrl: string; onBaseUrl: (value: string) => void; apiKey: string; onApiKey: (value: string) => void;
  credentialPresent?: boolean; credentialHelp?: string; credentialWritable?: boolean;
  showCredential?: boolean; urlHelp?: string; required?: boolean;
}) {
  return <Stack spacing={1.5}>
    <TextField label="Endpoint URL" required={required} value={baseUrl} onChange={e => onBaseUrl(e.target.value)}
      helperText={urlHelp ?? "API base address, including /v1 or /v2 where required. Leave empty to disable."} />
    {showCredential && <TextField type="password" autoComplete="new-password" label={credentialPresent ? "API key (already configured)" : "API key"}
      value={apiKey} onChange={e => onApiKey(e.target.value)} disabled={!credentialWritable}
      helperText={credentialHelp ?? "Leave empty to keep the saved key at the same URL. A changed URL requires its own key."} />}
  </Stack>;
}
