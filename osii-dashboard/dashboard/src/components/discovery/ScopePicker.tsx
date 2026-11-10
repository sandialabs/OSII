import { Autocomplete, MenuItem, Stack, TextField } from "@mui/material";
import { useQuery } from "@tanstack/react-query";
import { listCollectionScopes, listFolderScopes } from "../../api/scopes";
import { useScopeSummaries } from "../../hooks/useScopeSummaries";
import type { ScopeDescribeRequest } from "../../api/types";

export function ScopePicker({ value, onChange, allowedTypes = ["root", "folder", "collection", "object"], disabled = false }: { value: ScopeDescribeRequest; onChange: (scope: ScopeDescribeRequest) => void; allowedTypes?: ScopeDescribeRequest["scope_type"][]; disabled?: boolean }) {
  const collections = useQuery({ queryKey: ["scopes", "collections"], queryFn: listCollectionScopes, enabled: value.scope_type === "collection" });
  const folders = useQuery({ queryKey: ["scopes", "folders"], queryFn: listFolderScopes, enabled: value.scope_type === "folder" });
  const files = useScopeSummaries({ scope_type: "root" }, value.scope_type === "object");
  const options = value.scope_type === "object" ? (files.data?.summaries ?? []).map(file => ({ id: file.file_id, label: file.filename ?? file.file_id }))
    : value.scope_type === "collection" ? (collections.data?.scopes ?? []).map(scope => ({ id: scope.collection_id, label: scope.label }))
    : value.scope_type === "folder" ? (folders.data?.scopes ?? []).map(scope => ({ id: scope.folder_id, label: scope.path || "/" })) : [];
  const id = value.scope_type === "object" ? value.file_id : value.scope_type === "collection" ? value.collection_id : value.scope_type === "folder" ? value.folder_id : "";
  return <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
    <TextField select disabled={disabled} size="small" label="Scope" value={value.scope_type} onChange={event => {
      const kind = event.target.value;
      onChange(kind === "object" ? { scope_type: "object", file_id: "" } : kind === "folder" ? { scope_type: "folder", folder_id: "" } : kind === "collection" ? { scope_type: "collection", collection_id: "" } : { scope_type: "root" });
    }} sx={{ minWidth: 180 }}>{allowedTypes.map(kind => <MenuItem key={kind} value={kind}>{{ root: "Library", folder: "Folder", collection: "Collection", object: "Document" }[kind]}</MenuItem>)}</TextField>
    {value.scope_type !== "root" ? <Autocomplete disabled={disabled} size="small" options={options} value={options.find(option => option.id === id) ?? null} isOptionEqualToValue={(a, b) => a.id === b.id} getOptionLabel={option => option.label} sx={{ minWidth: 300, flex: 1 }}
      onChange={(_, option) => onChange(value.scope_type === "object" ? { scope_type: "object", file_id: option?.id ?? "" } : value.scope_type === "folder" ? { scope_type: "folder", folder_id: option?.id ?? "" } : { scope_type: "collection", collection_id: option?.id ?? "" })}
      renderInput={params => <TextField {...params} label={`Choose ${value.scope_type === "object" ? "a document" : value.scope_type === "folder" ? "a folder" : "a collection"}`} />} /> : null}
  </Stack>;
}
