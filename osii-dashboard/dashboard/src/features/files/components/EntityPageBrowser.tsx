// src/features/files/components/EntityPageBrowser.tsx
import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import AddOutlinedIcon from "@mui/icons-material/AddOutlined";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { useWikiFile } from "../../../hooks/useWikiFile";
import { useSaveWikiFile } from "../../../hooks/useSaveWikiFile";
import {
  appendEntitySection,
  entityNameInDraft,
  newEntityUid,
  parseEntitySections,
  replaceEntitySection,
} from "./entityPage";
import { markdownSx } from "./markdownSx";

/**
 * Present one document-level entities page as a page per entity.
 *
 * Storage stays a single Markdown file; an edit here rewrites only that
 * entity's section of it.
 */
export function EntityPageBrowser({
  relpath,
  focusEntity,
}: {
  relpath: string;
  focusEntity?: string | null;
}) {
  const page = useWikiFile(relpath);
  const save = useSaveWikiFile();
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  const source = page.data ?? "";
  const body = useMemo(() => stripFrontMatter(source), [source]);
  const sections = useMemo(() => parseEntitySections(body), [body]);

  useEffect(() => {
    setSelected(null);
    setDraft(null);
    setCreating(false);
  }, [relpath]);

  // A wiki link may name the entity to open.
  useEffect(() => {
    if (focusEntity) {
      setSelected(focusEntity);
      setDraft(null);
    }
  }, [focusEntity]);

  if (page.isLoading) return <CircularProgress size={20} />;
  if (page.isError) {
    return (
      <Alert severity="warning">
        {page.error instanceof Error ? page.error.message : "Could not load this page."}
      </Alert>
    );
  }

  // An empty page still needs the create affordance, so the empty state is
  // rendered inline rather than returned early.
  const active = sections.find((section) => section.name === selected) ?? sections[0] ?? null;

  const commit = () => {
    if (draft === null) return;

    const content = creating || !active
      ? appendEntitySection(source, draft)
      : replaceEntitySection(source, active, draft);

    const created = creating ? entityNameInDraft(draft) : null;

    save.mutate(
      { relpath, content },
      {
        onSuccess: () => {
          setDraft(null);
          setCreating(false);
          if (created) setSelected(created);
        },
      },
    );
  };

  const startCreating = () => {
    setCreating(true);
    setDraft(
      [
        "### New entity",
        "",
        `- UID: \`${newEntityUid()}\``,
        "- Entity type: `other`",
        "- Summary: ",
        "- Evidence: ",
        "",
      ].join("\n"),
    );
  };

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" justifyContent="flex-end">
        <Button
          size="small"
          variant="outlined"
          startIcon={<AddOutlinedIcon />}
          disabled={draft !== null}
          onClick={startCreating}
        >
          Add entity
        </Button>
      </Stack>

      {sections.length === 0 && draft === null ? (
        <Alert severity="info">
          No entities were extracted for this document. Use Add entity to create one.
        </Alert>
      ) : null}

      <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="flex-start">
      {sections.length > 0 ? (
      <List
        dense
        sx={{
          width: { xs: "100%", md: 260 },
          flexShrink: 0,
          border: (theme) => `1px solid ${theme.palette.divider}`,
          borderRadius: 1,
          maxHeight: 520,
          overflowY: "auto",
          py: 0,
        }}
      >
        {sections.map((section) => (
          <ListItemButton
            key={section.name}
            dense
            selected={section.name === active.name}
            onClick={() => {
              setSelected(section.name);
              setDraft(null);
            }}
          >
            <ListItemText
              primary={section.name}
              secondary={section.group || undefined}
              primaryTypographyProps={{ variant: "body2", sx: { wordBreak: "break-word" } }}
              secondaryTypographyProps={{ variant: "caption" }}
            />
          </ListItemButton>
        ))}
      </List>
      ) : null}

      <Box sx={{ flex: 1, minWidth: 0 }}>
        {draft !== null ? (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Button
                variant="contained"
                startIcon={<SaveOutlinedIcon />}
                disabled={save.isPending || (!creating && draft === active?.body)}
                onClick={commit}
              >
                {save.isPending ? "Saving…" : "Save"}
              </Button>
              <Button
                variant="outlined"
                startIcon={<CloseOutlinedIcon />}
                disabled={save.isPending}
                onClick={() => {
                  setDraft(null);
                  setCreating(false);
                }}
              >
                Cancel
              </Button>
              <Typography variant="caption" color="text.secondary">
                {creating
                  ? "New entity; it is appended to this document's entities page."
                  : "Editing this entity only; the rest of the page is untouched."}
              </Typography>
            </Stack>

            {save.isError ? (
              <Alert severity="error">
                {save.error instanceof Error ? save.error.message : "Could not save."}
              </Alert>
            ) : null}

            <TextField
              multiline
              fullWidth
              minRows={14}
              maxRows={34}
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              InputProps={{
                sx: {
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: "0.8rem",
                },
              }}
            />
          </Stack>
        ) : !active ? null : (
          <Stack spacing={1.5}>
            <Stack direction="row" spacing={1} alignItems="center" justifyContent="space-between">
              {active.group ? (
                <Chip size="small" color="primary" label={active.group} />
              ) : <span />}
              <Stack direction="row" spacing={1} alignItems="center">
                {save.isSuccess ? (
                  <Typography variant="caption" color="success.main">Saved</Typography>
                ) : null}
                <Button
                  size="small"
                  variant="outlined"
                  startIcon={<EditOutlinedIcon />}
                  onClick={() => setDraft(active.body)}
                >
                  Edit entity
                </Button>
              </Stack>
            </Stack>

            <Box className="markdown-body" sx={markdownSx}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{active.body}</ReactMarkdown>
            </Box>
          </Stack>
        )}
      </Box>
      </Stack>
    </Stack>
  );
}

function stripFrontMatter(text: string): string {
  const lines = text.split("\n");
  if (lines[0]?.trim() !== "---") return text;
  const closing = lines.indexOf("---", 1);
  return closing === -1 ? text : lines.slice(closing + 1).join("\n");
}
