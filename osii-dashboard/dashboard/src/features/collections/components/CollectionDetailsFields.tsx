import type { ReactNode } from "react";
import { TextField } from "@mui/material";

export function CollectionDetailsFields({
  name, description, onNameChange, onDescriptionChange, maxNameLength, maxDescriptionLength, children,
}: {
  name: string;
  description: string;
  onNameChange: (name: string) => void;
  onDescriptionChange: (description: string) => void;
  maxNameLength?: number;
  maxDescriptionLength?: number;
  children?: ReactNode;
}) {
  return <>
    <TextField
      fullWidth
      label="Name"
      value={name}
      onChange={event => onNameChange(event.target.value)}
      inputProps={{ maxLength: maxNameLength }}
    />
    <TextField
      fullWidth
      label="Description"
      multiline
      minRows={3}
      value={description}
      onChange={event => onDescriptionChange(event.target.value)}
      inputProps={{ maxLength: maxDescriptionLength }}
    />
    {children}
  </>;
}
