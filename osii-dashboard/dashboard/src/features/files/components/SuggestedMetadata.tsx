import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Stack, TextField, Typography } from "@mui/material";
import { apiJson } from "../../../api/client";
import type { DocumentMetadata } from "../../../api/documentMetadata";
const fields = [
  "descriptive_title",
  "title",
  "author",
  "date",
  "agency",
  "document_type",
] as const;
const label = (name: string) =>
  name.replace(/_/g, " ").replace(/^./, (value) => value.toUpperCase());
type RecordResponse = {
  revision: string | null;
  document_metadata?: DocumentMetadata | null;
};

type MetadataRequest = typeof apiJson;
export function SuggestedMetadata(props: {
  metadata?: DocumentMetadata | null;
  fileId?: string;
  canEdit?: boolean;
  request?: MetadataRequest;
  onSaved?: () => void;
}) {
  return <MetadataEditor key={props.fileId ?? "preview"} {...props} />;
}

function MetadataEditor({
  metadata,
  fileId,
  canEdit = true,
  request = apiJson,
  onSaved,
}: {
  metadata?: DocumentMetadata | null;
  fileId?: string;
  canEdit?: boolean;
  request?: MetadataRequest;
  onSaved?: () => void;
}) {
  const client = useQueryClient();
  const [draft, setDraft] = useState<Record<string, string> | null>(null);
  const [base, setBase] = useState<string | null>(null);
  const record = useQuery({
    queryKey: ["objects", fileId, "metadata"],
    enabled: Boolean(fileId),
    queryFn: () =>
      request<RecordResponse>(
        `/api/objects/${encodeURIComponent(fileId!)}/metadata`,
      ),
  });
  const current = record.data?.document_metadata ?? metadata;
  const save = useMutation({
    mutationFn: () =>
      request<RecordResponse>(
        `/api/objects/${encodeURIComponent(fileId!)}/metadata`,
        { method: "PUT", json: { values: draft, expected_revision: base } },
      ),
    onSuccess: async () => {
      setDraft(null);
      onSaved?.();
      await Promise.all(
        ["objects", "scopes", "topics", "products", "enrichments"].map((key) =>
          client.invalidateQueries({ queryKey: [key] }),
        ),
      );
    },
  });
  if (!current && !fileId) return null;
  return (
    <Stack spacing={1} aria-label="Document metadata">
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="subtitle2">
          {current?.method === "human"
            ? "Document metadata"
            : "Suggested metadata"}
        </Typography>
        {fileId && canEdit && !draft ? (
          <Button
            size="small"
            disabled={!record.data}
            onClick={() => {
              setBase(record.data?.revision ?? null);
              setDraft(
                Object.fromEntries(
                  fields.map((name) => [name, current?.[name]?.value ?? ""]),
                ),
              );
            }}
          >
            Edit metadata
          </Button>
        ) : null}
      </Stack>
      {draft ? (
        <>
          {fields.map((name) => (
            <TextField
              key={name}
              size="small"
              label={label(name)}
              value={draft[name]}
              onChange={(event) =>
                setDraft({ ...draft, [name]: event.target.value })
              }
              inputProps={{ maxLength: 240 }}
              helperText={
                name === "descriptive_title"
                  ? "Short content label; may differ from the title printed on the document."
                  : undefined
              }
            />
          ))}
          {record.data && base !== record.data.revision ? (
            <Alert severity="warning">
              Metadata changed. Latest:{" "}
              {fields
                .map(
                  (name) =>
                    `${label(name)}: ${record.data?.document_metadata?.[name]?.value || "—"}`,
                )
                .join(" · ")}{" "}
              <Button onClick={() => setBase(record.data!.revision)}>
                Keep draft over latest
              </Button>
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={save.isPending}
              onClick={() =>
                save.mutate(undefined, {
                  onError: () => {
                    void record.refetch();
                  },
                })
              }
            >
              Save metadata
            </Button>
            <Button onClick={() => setDraft(null)}>Cancel</Button>
          </Stack>
          <Typography variant="caption">
            Blank fields are allowed. Edits are saved separately from file
            properties and AI suggestions.
          </Typography>
        </>
      ) : (
        <>
          {current?.method !== "human" ? (
            <Typography variant="caption" color="text.secondary">
              Inferred from text. Verify against the original.
            </Typography>
          ) : null}
          {fields.map((name) => (
            <Stack key={name} spacing={0.25}>
              <Typography variant="body2">
                <strong>{label(name)}:</strong> {current?.[name]?.value || "—"}
              </Typography>
              {current?.[name]?.qualifier ? (
                <Typography variant="body2" color="text.secondary">
                  {current[name]?.qualifier}
                </Typography>
              ) : null}
              {current?.[name]?.evidence ? (
                <Typography
                  variant="caption"
                  component="blockquote"
                  sx={{
                    m: 0,
                    pl: 1,
                    borderLeft: "2px solid",
                    borderColor: "divider",
                  }}
                >
                  “{current[name]?.evidence}”
                </Typography>
              ) : null}
            </Stack>
          ))}
        </>
      )}
      {save.isError ? (
        <Alert severity="error">
          {save.error instanceof Error
            ? save.error.message
            : "Could not save metadata. Your draft is preserved."}
        </Alert>
      ) : null}
      {record.isError ? (
        <Alert severity="warning">
          Metadata is unavailable.{" "}
          <Button onClick={() => void record.refetch()}>Retry</Button>
        </Alert>
      ) : null}
    </Stack>
  );
}
