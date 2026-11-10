import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Alert,
  Button,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import { apiJson } from "../../../api/client";
import type { ScopeDescribeRequest } from "../../../api/types";
import { MathpixText } from "../../../components/text/MathpixText";
import { EnrichmentArtifactView } from "./EnrichmentArtifactView";

type Revision = {
  id: string;
  origin: string;
  created_at: string | null;
  data: unknown;
  parent?: string;
};
type History = {
  permissions?: { edit: boolean };
  library_id: string;
  current: string;
  data: unknown;
  revisions: Revision[];
};
const asText = (data: unknown) =>
  data &&
  typeof data === "object" &&
  "artifact_type" in data &&
  data.artifact_type === "text" &&
  "text" in data &&
  typeof data.text === "string"
    ? data.text
    : null;

function Editor({
  history,
  address,
}: {
  history: History;
  address: Record<string, unknown>;
}) {
  const client = useQueryClient();
  const draftKey = `osii:product-draft:${history.library_id}:${JSON.stringify(address)}`;
  const [tab, setTab] = useState("read");
  const [draft, setDraft] = useState<{ value: string; base: string } | null>(
    () => {
      try {
        const saved = JSON.parse(localStorage.getItem(draftKey) ?? "null");
        return saved &&
          typeof saved.value === "string" &&
          typeof saved.base === "string"
          ? saved
          : null;
      } catch {
        return null;
      }
    },
  );
  const [storageError, setStorageError] = useState(false);
  const [selected, setSelected] = useState("");
  const [error, setError] = useState("");
  const dataRecord =
    history.data && typeof history.data === "object"
      ? (history.data as Record<string, unknown>)
      : {};
  const wiki =
    dataRecord.artifact_type === "wiki_markdown" &&
    typeof dataRecord.markdown === "string";
  const text = wiki ? (dataRecord.markdown as string) : asText(history.data);
  const save = useMutation({
    mutationFn: (change: Record<string, unknown>) =>
      apiJson<History>("/api/products/revisions", {
        method: "PUT",
        json: { ...address, ...change },
      }),
    onSuccess: async (_, change) => {
      if ("data" in change) {
        setDraft(null);
        try {
          localStorage.removeItem(draftKey);
        } catch {
          setStorageError(true);
        }
      }
      setTab("read");
      await Promise.all([
        client.invalidateQueries({ queryKey: ["products"] }),
        client.invalidateQueries({ queryKey: ["enrichments"] }),
        client.invalidateQueries({ queryKey: ["objects"] }),
        client.invalidateQueries({ queryKey: ["scopes"] }),
        client.invalidateQueries({ queryKey: ["topics"] }),
      ]);
    },
  });
  useEffect(() => {
    if (draft) {
      try {
        localStorage.setItem(draftKey, JSON.stringify(draft));
      } catch {
        setStorageError(true);
      }
    }
  }, [draft, draftKey]);
  const edit = () => {
    if (!draft)
      setDraft({
        value: text ?? JSON.stringify(history.data, null, 2),
        base: history.current,
      });
    setTab("edit");
  };
  const render = (data: unknown) =>
    asText(data) !== null ? (
      <MathpixText text={asText(data)!} />
    ) : (
      <EnrichmentArtifactView data={data} />
    );
  const candidate = history.revisions.find((item) => item.id === selected);
  const generatedCandidate = history.revisions.some(
    (item) =>
      item.id !== history.current &&
      item.origin === "generated" &&
      item.parent === history.current,
  );
  return (
    <Stack spacing={1.5}>
      <Tabs
        value={tab}
        onChange={(_, value: string) =>
          value === "edit" ? edit() : setTab(value)
        }
        aria-label="Product views"
      >
        <Tab value="read" label="Read" />
        <Tab value="edit" label={draft ? "Resume draft" : "Edit"} disabled={history.permissions?.edit === false || dataRecord.artifact_type === "scope_batch_run"} />
        <Tab value="history" label={`History (${history.revisions.length})`} />
      </Tabs>
      {generatedCandidate ? (
        <Alert severity="info">
          A generated version is saved in History. Your edits remain current.
        </Alert>
      ) : null}
      {tab === "read" ? render(history.data) : null}
      {tab === "edit" && draft ? (
        <>
          <TextField
            fullWidth
            multiline
            minRows={12}
            maxRows={32}
            label={text !== null ? "Text / Mathpix Markdown" : "Product JSON"}
            value={draft.value}
            onChange={(event) =>
              setDraft({ ...draft, value: event.target.value })
            }
            inputProps={{ style: { fontFamily: "monospace" } }}
          />
          {draft.base !== history.current ? (
            <Alert severity="warning">
              This product changed. Compare the latest revision before rebasing
              your draft.{" "}
              <Button
                onClick={() => setDraft({ ...draft, base: history.current })}
              >
                Use latest as base
              </Button>
            </Alert>
          ) : null}
          <Stack direction="row" spacing={1}>
            <Button
              variant="contained"
              disabled={save.isPending || draft.base !== history.current}
              onClick={() => {
                try {
                  const data =
                    text !== null
                      ? {
                          ...dataRecord,
                          [wiki ? "markdown" : "text"]: draft.value,
                        }
                      : JSON.parse(draft.value);
                  setError("");
                  save.mutate({ data, expected_revision: draft.base });
                } catch {
                  setError("Fix the JSON syntax before saving.");
                }
              }}
            >
              Save revision
            </Button>
            <Button onClick={() => setTab("read")}>Keep draft</Button>
            <Button
              color="error"
              onClick={() => {
                setDraft(null);
                try {
                  localStorage.removeItem(draftKey);
                } catch {
                  setStorageError(true);
                }
                setTab("read");
              }}
            >
              Discard draft
            </Button>
          </Stack>
          <Typography variant="caption">
            {storageError
              ? "Browser storage is full. Keep this page open until saved."
              : "Draft saved on this device. Changes retain the generated original and require citation review."}
          </Typography>
        </>
      ) : null}
      {tab === "history" ? (
        <>
          <TextField
            select
            size="small"
            label="Revision"
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            {[...history.revisions].reverse().map((item) => (
              <MenuItem key={item.id} value={item.id}>
                {item.origin} ·{" "}
                {item.created_at
                  ? new Date(item.created_at).toLocaleString()
                  : "Original"}
                {item.id === history.current ? " · Current" : ""}
              </MenuItem>
            ))}
          </TextField>
          {candidate ? (
            <>
              <Typography fontWeight={700}>Selected revision</Typography>
              {render(candidate.data)}
              {candidate.id !== history.current && history.permissions?.edit !== false ? (
                <Button
                  onClick={() =>
                    save.mutate({
                      revision: candidate.id,
                      expected_revision: history.current,
                    })
                  }
                >
                  Use this revision
                </Button>
              ) : null}
            </>
          ) : null}
        </>
      ) : null}
      {error || save.isError ? (
        <Alert severity="error">
          {error ||
            (save.error instanceof Error
              ? save.error.message
              : "Could not save. Your draft is preserved.")}
        </Alert>
      ) : null}
    </Stack>
  );
}

export function DerivedProductEditor({
  scope,
  filename,
  family = "enrichment",
}: {
  scope: ScopeDescribeRequest;
  filename: string;
  family?: "enrichment" | "synthesis";
}) {
  const address = { scope, filename, family };
  const history = useQuery({
    queryKey: ["products", "revisions", address],
    queryFn: () =>
      apiJson<History>("/api/products/revisions", {
        method: "POST",
        json: address,
      }),
  });
  if (history.isError)
    return (
      <Alert severity="warning">
        This product could not be loaded.{" "}
        <Button onClick={() => void history.refetch()}>Retry</Button>
      </Alert>
    );
  if (!history.data) return <Typography>Loading saved product…</Typography>;
  return (
    <Editor
      key={`${history.data.library_id}:${JSON.stringify(address)}`}
      history={history.data}
      address={address}
    />
  );
}
