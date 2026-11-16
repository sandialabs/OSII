import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  LinearProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { ExpandMore, HelpOutline } from "@mui/icons-material";
import { apiJson } from "../../../api/client";

type Suggestion = {
  id: string;
  name: string;
  description: string;
  file_ids: string[];
  keywords: string[];
  method: string;
  documents: { file_id: string; filename: string; title: string }[];
};
type Suggestions = {
  suggestions: Suggestion[];
  considered_documents: number;
  grouped_documents: number;
  candidate_documents: number;
  can_prompt: boolean;
  chat_model: string | null;
  guided: boolean;
  algorithm: string;
};
export type CreateSuggestedCollection = (
  name: string,
  ids: string[],
  description?: string,
) => Promise<void>;

/** Stay visible after the first save so other starter choices can still be created. */
export function useStarterCollections(count: number, ready: boolean) {
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    if (ready && count === 0) setVisible(true);
  }, [ready, count]);
  return visible;
}

export function CollectionSuggestions({
  create,
}: {
  create: CreateSuggestedCollection;
}) {
  const client = useQueryClient();
  const automatic = useQuery({
    queryKey: ["collection-suggestions"],
    queryFn: () => apiJson<Suggestions>("/api/collection-suggestions"),
    staleTime: 60_000,
    refetchOnWindowFocus: false,
  });
  const [prompt, setPrompt] = useState("");
  const [help, setHelp] = useState(false);
  const [saved, setSaved] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState<string | null>(null);
  const [saveError, setSaveError] = useState("");
  const guided = useMutation({
    mutationFn: () =>
      apiJson<Suggestions>("/api/collection-suggestions", {
        method: "POST",
        json: { prompt: prompt.trim() },
      }),
  });
  const result = guided.data ?? automatic.data;
  const save = async (items: Suggestion[]) => {
    setSaveError("");
    const remaining = items.filter((item) => !saved.has(item.id));
    if (!remaining.length) return;
    setSaving(remaining[0].id);
    try {
      for (const item of remaining) {
        setSaving(item.id);
        await create(item.name, item.file_ids, item.description);
        setSaved((previous) => new Set([...previous, item.id]));
      }
      await client.invalidateQueries({ queryKey: ["collections"] });
    } catch (error) {
      setSaveError((error as Error).message);
    } finally {
      setSaving(null);
    }
  };
  return (
    <Stack spacing={2} aria-label="Suggested collections">
      <Stack direction="row" spacing={1} alignItems="center">
        <Typography variant="h6" fontWeight={700}>
          Suggested collections
        </Typography>
        <IconButton
          size="small"
          aria-label="How collection suggestions work"
          onClick={() => setHelp(true)}
        >
          <HelpOutline fontSize="small" />
        </IconButton>
      </Stack>
      <Stack
        direction={{ xs: "column", sm: "row" }}
        spacing={1}
        alignItems={{ sm: "start" }}
      >
        <TextField
          fullWidth
          label="Describe the collections you want"
          placeholder="For example: separate practical gardening, forest ecology, and historical accounts"
          multiline
          minRows={2}
          maxRows={5}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          inputProps={{ maxLength: 2000 }}
          disabled={guided.isPending || Boolean(saving)}
        />
        <Button
          variant="outlined"
          disabled={
            !prompt.trim() ||
            !result?.can_prompt ||
            guided.isPending ||
            Boolean(saving)
          }
          onClick={() => guided.mutate()}
        >
          Suggest with AI
        </Button>
      </Stack>
      {result && !result.can_prompt && (
        <Typography variant="caption" color="text.secondary">
          A chat model must be configured in Setup to use a prompt. Starter
          suggestions use saved library data.
        </Typography>
      )}
      {automatic.isPending && !result && (
        <Stack spacing={1}>
          <LinearProgress />
          <Typography variant="body2" role="status">
            Finding related documents…
          </Typography>
        </Stack>
      )}
      {guided.isPending && (
        <Stack spacing={1}>
          <LinearProgress />
          <Typography variant="body2" role="status">
            Suggesting collections with{" "}
            {result?.chat_model || "the configured model"}…
          </Typography>
        </Stack>
      )}
      {automatic.isError && !result && (
        <Alert
          severity="warning"
          action={
            <Button onClick={() => void automatic.refetch()}>Retry</Button>
          }
        >
          Could not load collection suggestions.
        </Alert>
      )}
      {guided.isError && (
        <Alert severity="warning">{(guided.error as Error).message}</Alert>
      )}
      {guided.data && (
        <Button sx={{ alignSelf: "start" }} onClick={() => guided.reset()}>
          Show starter suggestions
        </Button>
      )}
      {result && (
        <Typography variant="caption" color="text.secondary">
          {result.guided
            ? `AI-guided from ${result.candidate_documents} candidate documents chosen across ${result.considered_documents} files`
            : `Best guesses across ${result.considered_documents} files`}{" "}
          · {result.grouped_documents} documents grouped. Other documents can
          stay outside collections.
        </Typography>
      )}
      {result && !result.suggestions.length && (
        <Alert severity="info">
          Not enough related evidence for a useful collection yet. Add or
          process documents, try a more specific prompt, or select files
          manually.
        </Alert>
      )}
      {saveError && (
        <Alert severity="error">
          {saveError} Completed collections are kept; retry creates the
          remaining selections.
        </Alert>
      )}
      {result && result.suggestions.length > 1 && (
        <Button
          variant="outlined"
          sx={{ alignSelf: "start" }}
          disabled={
            Boolean(saving) ||
            guided.isPending ||
            result.suggestions.every((item) => saved.has(item.id))
          }
          onClick={() => void save(result.suggestions)}
        >
          Create all suggestions
        </Button>
      )}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            md: "repeat(2,minmax(0,1fr))",
            xl: "repeat(3,minmax(0,1fr))",
          },
          gap: 2,
        }}
      >
        {result?.suggestions.map((item) => (
          <Card key={item.id} variant="outlined">
            <CardContent>
              <Stack spacing={1.25}>
                <Typography
                  variant="subtitle1"
                  fontWeight={700}
                  sx={{ overflowWrap: "anywhere" }}
                >
                  {item.name}
                </Typography>
                <Typography variant="body2" sx={{ overflowWrap: "anywhere" }}>
                  {item.description}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {item.file_ids.length} documents ·{" "}
                  {item.method === "ai-guided"
                    ? "AI suggestion"
                    : item.method === "saved-embeddings"
                      ? "Saved embeddings"
                      : "Saved text"}
                </Typography>
                <Accordion
                  disableGutters
                  elevation={0}
                  variant="outlined"
                  slotProps={{ transition: { unmountOnExit: true } }}
                >
                  <AccordionSummary expandIcon={<ExpandMore />}>
                    <Typography variant="body2">Preview documents</Typography>
                  </AccordionSummary>
                  <AccordionDetails>
                    <Stack
                      spacing={0.5}
                      sx={{ maxHeight: 240, overflow: "auto" }}
                    >
                      {item.documents.map((doc) => (
                        <Button
                          key={doc.file_id}
                          component={Link}
                          to={`/files/${encodeURIComponent(doc.file_id)}`}
                          size="small"
                          sx={{
                            justifyContent: "start",
                            overflowWrap: "anywhere",
                          }}
                        >
                          {doc.title}
                        </Button>
                      ))}
                    </Stack>
                  </AccordionDetails>
                </Accordion>
                <Button
                  variant="contained"
                  aria-label={`Create collection ${item.name}`}
                  disabled={
                    Boolean(saving) || guided.isPending || saved.has(item.id)
                  }
                  onClick={() => void save([item])}
                >
                  {saved.has(item.id)
                    ? "Created"
                    : saving === item.id
                      ? "Creating…"
                      : "Create collection"}
                </Button>
              </Stack>
            </CardContent>
          </Card>
        ))}
      </Box>
      <Dialog
        open={help}
        onClose={() => setHelp(false)}
        fullWidth
        maxWidth="sm"
      >
        <DialogTitle>How collection suggestions work</DialogTitle>
        <DialogContent>
          <Stack spacing={2}>
            <Typography>
              Starter suggestions group compatible saved embeddings, with
              saved-text topics as a fallback. Shared terms provide names. They
              are best guesses: weak matches and near-duplicate groups are left
              out.
            </Typography>
            <Typography>
              A prompt sends a bounded selection of saved descriptions to your
              configured chat model. It may propose names and choose only known
              documents. It cannot create a collection by itself.
            </Typography>
            <Typography>
              Preview the documents or create a suggestion directly. Collections
              do not need to cover the library, and you can edit them afterward.
              Hosted collections start private.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setHelp(false)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
