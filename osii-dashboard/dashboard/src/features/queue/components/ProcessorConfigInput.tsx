import { FormControlLabel, Switch, TextField, MenuItem } from "@mui/material";
import type { ProcessorConfigProperty } from "../../../api/types";

export function ProcessorConfigInput({ name, property, value, onChange }: {
  name: string;
  property: ProcessorConfigProperty;
  value: unknown;
  onChange: (value: unknown) => void;
}) {
  const label = property.title ?? name.replace(/_/g, " ");
  if (property.type === "boolean") {
    return <FormControlLabel control={<Switch checked={Boolean(value)} onChange={(event) => onChange(event.target.checked)} />} label={label} />;
  }
  if (property.enum?.length) {
    return <TextField select fullWidth size="small" label={label} value={value ?? ""} onChange={(event) => onChange(event.target.value)} helperText={property.description}>
      {property.enum.map((option) => <MenuItem key={String(option)} value={option}>{option}</MenuItem>)}
    </TextField>;
  }
  const numeric = property.type === "number" || property.type === "integer";
  return <TextField
    fullWidth size="small" multiline={property.format === "textarea"}
    minRows={property.format === "textarea" ? 6 : undefined} label={label}
    type={numeric ? "number" : "text"} value={value ?? ""}
    inputProps={numeric ? { min: property.minimum, max: property.maximum, step: property.type === "integer" ? 1 : 0.1 } : undefined}
    onChange={(event) => onChange(numeric ? Number(event.target.value) : event.target.value)}
    helperText={property.description}
  />;
}
