import { Autocomplete, Box, Stack, TextField, Typography } from "@mui/material";

export type ModelOption = { id: string; name: string; capabilities: string[] };

/** Names are presentation; the provider identifier stays behind the selection. */
export function ModelPicker({ label, value, options, onChange, helperText, disabled = false }: {
  label: string; value: string; options: ModelOption[]; onChange: (value: string) => void; helperText?: string; disabled?: boolean;
}) {
  const selected = options.find(model => model.id === value) ?? (value ? { id: value, name: value, capabilities: [] } : null);
  const choices = selected && !options.some(option => option.id === selected.id) ? [selected, ...options] : options;
  return <Stack spacing={0.5}>
    {<Autocomplete disabled={disabled} options={[...choices].sort((a, b) => Number(Boolean(b.capabilities.length)) - Number(Boolean(a.capabilities.length)))} groupBy={model => model.capabilities.length ? "Declared capability · untested" : "Capability unknown"} value={selected} onChange={(_, model) => onChange(model?.id ?? "")}
        isOptionEqualToValue={(a, b) => a.id === b.id} getOptionLabel={model => model.name}
        renderOption={(props, model) => <li {...props} key={model.id}><Box><Typography variant="body2">{model.name}</Typography>
          {!model.capabilities.length && <Typography variant="caption" color="text.secondary">Capability unknown · test before use</Typography>}
          {model.name !== model.id && <Typography variant="caption" color="text.secondary">{model.id}</Typography>}</Box></li>}
        renderInput={params => <TextField {...params} label={label} helperText={helperText ?? `${options.length} available models. Save and check the connection to refresh the list.`} />} />}

  </Stack>;
}
