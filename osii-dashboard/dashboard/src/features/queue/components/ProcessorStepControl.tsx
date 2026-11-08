import type { ReactNode } from "react";
import { Checkbox, FormControlLabel, MenuItem, Stack, TextField, Typography } from "@mui/material";
export type ProcessorOption = { id: string; display_name: string; available?: boolean; detail?: string };
export function ProcessorStepControl({ label, methodLabel, checked, onChecked, method, onMethod, options, disabled = false, helperText, children }: {
  label: string; methodLabel: string; checked: boolean; onChecked: (checked: boolean) => void;
  method: string; onMethod: (method: string) => void; options: ProcessorOption[]; disabled?: boolean; helperText?: string; children?: ReactNode;
}) {
  return <Stack spacing={1}>
    <FormControlLabel control={<Checkbox checked={checked} disabled={disabled || !options.some(option => option.available !== false)} onChange={e => onChecked(e.target.checked)} />} label={label} />
    {checked && <TextField select size="small" label={methodLabel} value={options.some(option => option.id === method) ? method : ""} disabled={disabled} onChange={e => onMethod(e.target.value)}>
      {options.map(option => <MenuItem key={option.id} value={option.id} disabled={option.available === false}>{option.display_name}{option.available === false ? ` — ${option.detail || "unavailable"}` : ""}</MenuItem>)}
    </TextField>}
    {helperText && <Typography variant="caption" color="text.secondary">{helperText}</Typography>}
    {checked && children}
  </Stack>;
}
