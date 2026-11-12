import { useState } from "react";
import { Autocomplete, Box, Button, Stack, TextField, Typography } from "@mui/material";

export type ModelOption = { id: string; name: string; capabilities: string[] };

/** Names are presentation; the provider identifier stays behind the selection. */
export function ModelPicker({ label, value, options, onChange, helperText }: {
  label: string; value: string; options: ModelOption[]; onChange: (value: string) => void; helperText?: string;
}) {
  const [manual, setManual] = useState(false);
  const selected = options.find(model => model.id === value) ?? (value ? { id: value, name: value, capabilities: [] } : null);
  const choices = selected && !options.some(option => option.id === selected.id) ? [selected, ...options] : options;
  return <Stack spacing={0.5}>
    {manual ? <TextField label={label} value={value} onChange={e => onChange(e.target.value)}
      helperText="Enter the exact model name published by this service. This is only needed when a model list is unavailable." />
      : <Autocomplete options={choices} value={selected} onChange={(_, model) => onChange(model?.id ?? "")}
        isOptionEqualToValue={(a, b) => a.id === b.id} getOptionLabel={model => model.name}
        renderOption={(props, model) => <li {...props} key={model.id}><Box><Typography variant="body2">{model.name}</Typography>
          {model.name !== model.id && <Typography variant="caption" color="text.secondary">{model.id}</Typography>}</Box></li>}
        renderInput={params => <TextField {...params} label={label} helperText={helperText ?? `${options.length} available models. Use “Find available models” to refresh the list.`} />} />}
    <Button color="secondary" size="small" sx={{ alignSelf: "start" }} onClick={() => setManual(!manual)}>{manual ? "Choose from available models" : "Enter a model name manually"}</Button>
  </Stack>;
}
