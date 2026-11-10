import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Alert, Button, Stack } from "@mui/material";
import { apiJson } from "../../../api/client";
import { DerivedProductEditor } from "./DerivedProductEditor";

export function ExtractionCopyEditor({
  fileId,
  variantId,
  artifactId,
}: {
  fileId: string;
  variantId: string;
  artifactId?: string;
}) {
  const client = useQueryClient();
  const [filename, setFilename] = useState("");
  const copy = useMutation({
    mutationFn: () =>
      apiJson<{ filename: string }>(
        `/api/objects/${encodeURIComponent(fileId)}/extractions/${encodeURIComponent(variantId)}/editable-copy`,
        { method: "POST", json: { artifact_id: artifactId } },
      ),
    onSuccess: (result) => {
      setFilename(result.filename);
      void client.invalidateQueries({ queryKey: ["enrichments"] });
    },
  });
  return (
    <Stack spacing={1}>
      {filename ? (
        <>
          <Alert severity="info">
            Editable copy saved in Products. Original extraction and source
            locations are retained; edited passages need grounding review.
          </Alert>
          <DerivedProductEditor
            scope={{ scope_type: "object", file_id: fileId }}
            filename={filename}
          />
        </>
      ) : (
        <Button
          size="small"
          sx={{ alignSelf: "flex-start" }}
          disabled={copy.isPending}
          onClick={() => copy.mutate()}
        >
          {artifactId
            ? "Edit a copy of this product"
            : "Edit a copy of this extraction"}
        </Button>
      )}
      {copy.isError ? (
        <Alert severity="error">Could not create an editable copy.</Alert>
      ) : null}
    </Stack>
  );
}
