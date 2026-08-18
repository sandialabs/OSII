// src/features/files/components/WikiBundleBrowser.tsx
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
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import EditOutlinedIcon from "@mui/icons-material/EditOutlined";
import SaveOutlinedIcon from "@mui/icons-material/SaveOutlined";
import CloseOutlinedIcon from "@mui/icons-material/CloseOutlined";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import type { EnrichmentBundleFileEntry } from "../../../api/types";
import { useWikiFile } from "../../../hooks/useWikiFile";
import { useSaveWikiFile } from "../../../hooks/useSaveWikiFile";

type WikiSection = {
  id: string;
  label: string;
  files: EnrichmentBundleFileEntry[];
};

// Ordered so the reading path runs from overview to detail to maintenance.
const SECTION_ORDER: { id: string; label: string; match: (name: string) => boolean }[] = [
  { id: "index", label: "Index", match: (name) => name === "index.md" },
  { id: "sources", label: "Sources", match: (name) => name.startsWith("sources/") },
  { id: "entities", label: "Entities", match: (name) => name.startsWith("entities/") },
  { id: "concepts", label: "Concepts", match: (name) => name.startsWith("concepts/") },
  { id: "notes", label: "Notes", match: (name) => name.startsWith("notes/") },
  { id: "log", label: "log.md", match: (name) => name === "log.md" },
  { id: "agents", label: "AGENTS.md", match: (name) => name === "AGENTS.md" },
];

function buildSections(files: EnrichmentBundleFileEntry[]): WikiSection[] {
  return SECTION_ORDER.map((section) => ({
    id: section.id,
    label: section.label,
    files: files.filter((file) => file.name.endsWith(".md") && section.match(file.name)),
  })).filter((section) => section.files.length > 0);
}

/**
 * Split YAML front matter off the top of a page.
 *
 * Front matter is metadata rather than prose, so it reads better as chips than
 * as the horizontal rule and run-on paragraph that Markdown would produce.
 */
function splitFrontMatter(text: string): { fields: [string, string][]; body: string } {
  const lines = text.split("\n");

  if (lines[0]?.trim() !== "---") {
    return { fields: [], body: text };
  }

  const closing = lines.indexOf("---", 1);
  if (closing === -1) {
    return { fields: [], body: text };
  }

  const fields: [string, string][] = [];
  for (const line of lines.slice(1, closing)) {
    const separator = line.indexOf(":");
    if (separator === -1) continue;
    const key = line.slice(0, separator).trim();
    const value = line.slice(separator + 1).trim().replace(/^"|"$/g, "");
    if (key && value) fields.push([key, value]);
  }

  return { fields, body: lines.slice(closing + 1).join("\n") };
}

function pageLabel(name: string): string {
  const base = name.split("/").pop() ?? name;
  return base.replace(/\.md$/, "");
}

// The page renders its own title as an H1, and the namespace repeats the source
// filename, so neither earns a chip.
const HIDDEN_FIELDS = new Set(["title", "source_namespace", "tags"]);
const HIGHLIGHTED_FIELDS = new Set(["kind", "entity_type", "status"]);

function WikiPage({ relpath }: { relpath: string }) {
  const page = useWikiFile(relpath);
  const save = useSaveWikiFile();
  const [draft, setDraft] = useState<string | null>(null);

  // Switching pages drops any draft rather than carrying it to another file.
  useEffect(() => {
    setDraft(null);
  }, [relpath]);

  if (page.isLoading) return <CircularProgress size={20} />;
  if (page.isError) {
    return (
      <Alert severity="warning">
        {page.error instanceof Error ? page.error.message : "Could not load this page."}
      </Alert>
    );
  }

  const source = page.data ?? "";

  if (draft !== null) {
    return (
      <Stack spacing={1.5}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Button
            variant="contained"
            startIcon={<SaveOutlinedIcon />}
            disabled={save.isPending || draft === source}
            onClick={() =>
              save.mutate(
                { relpath, content: draft },
                { onSuccess: () => setDraft(null) },
              )
            }
          >
            {save.isPending ? "Saving…" : "Save"}
          </Button>
          <Button
            variant="outlined"
            startIcon={<CloseOutlinedIcon />}
            disabled={save.isPending}
            onClick={() => setDraft(null)}
          >
            Cancel
          </Button>
          <Typography variant="caption" color="text.secondary">
            Editing {relpath.split("/").pop()}
          </Typography>
        </Stack>

        {save.isError ? (
          <Alert severity="error">
            {save.error instanceof Error ? save.error.message : "Could not save this page."}
          </Alert>
        ) : null}

        <TextField
          multiline
          fullWidth
          minRows={18}
          maxRows={40}
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
    );
  }

  const { fields, body } = splitFrontMatter(source);
  const visibleFields = fields.filter(([key]) => !HIDDEN_FIELDS.has(key));

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" spacing={1} alignItems="center" justifyContent="flex-end">
        {save.isSuccess ? (
          <Typography variant="caption" color="success.main">
            Saved
          </Typography>
        ) : null}
        <Button
          size="small"
          variant="outlined"
          startIcon={<EditOutlinedIcon />}
          onClick={() => setDraft(source)}
        >
          Edit page
        </Button>
      </Stack>
      {visibleFields.length > 0 ? (
        <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
          {visibleFields.map(([key, value]) => {
            const highlighted = HIGHLIGHTED_FIELDS.has(key);
            return (
              <Chip
                key={key}
                size="small"
                color={highlighted ? "primary" : "default"}
                variant={highlighted ? "filled" : "outlined"}
                label={
                  key === "uid" || key === "file_id"
                    ? value
                    : `${key}: ${value.length > 40 ? `${value.slice(0, 40)}…` : value}`
                }
              />
            );
          })}
        </Stack>
      ) : null}

      <Box
        className="markdown-body"
        sx={{
          backgroundColor: "background.paper",
          border: (theme) => `1px solid ${theme.palette.divider}`,
          borderRadius: 1.5,
          px: 2.5,
          py: 2,
          "& > :first-of-type": { mt: 0 },
          "& > :last-child": { mb: 0 },
          "& h1": { fontSize: "1.3rem", fontWeight: 700, letterSpacing: "-0.01em", mt: 0, mb: 1.5 },
          "& h2": { fontSize: "1rem", fontWeight: 600, mt: 2.5, mb: 0.75 },
          "& h3": { fontSize: "0.9rem", fontWeight: 600, mt: 2, mb: 0.5 },
          "& p, & li": { fontSize: "0.875rem", lineHeight: 1.7, color: "text.secondary" },
          "& ul, & ol": { pl: 2.5, my: 0.5 },
          "& blockquote": {
            m: 0,
            pl: 1.5,
            borderLeft: (theme) => `3px solid ${theme.palette.primary.main}`,
            color: "text.secondary",
          },
          "& code": {
            backgroundColor: "action.hover",
            px: 0.75,
            py: 0.25,
            borderRadius: 0.75,
            fontSize: "0.8rem",
          },
          "& pre": { overflowX: "auto", backgroundColor: "action.hover", p: 1.5, borderRadius: 1 },
          "& pre code": { backgroundColor: "transparent", p: 0 },
          "& table": { borderCollapse: "collapse" },
          "& td, & th": { border: "1px solid", borderColor: "divider", p: 1 },
          "& a": { color: "secondary.main" },
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
          {body}
        </ReactMarkdown>
      </Box>
    </Stack>
  );
}

export function WikiBundleBrowser({ files }: { files: EnrichmentBundleFileEntry[] }) {
  const sections = useMemo(() => buildSections(files), [files]);
  const [sectionId, setSectionId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, string>>({});

  if (sections.length === 0) {
    return <Alert severity="info">This wiki bundle contains no Markdown pages yet.</Alert>;
  }

  const activeId = sectionId && sections.some((s) => s.id === sectionId)
    ? sectionId
    : sections[0].id;
  const active = sections.find((section) => section.id === activeId) as WikiSection;
  const activeFile = selected[active.id] ?? active.files[0].relpath;

  return (
    <Stack spacing={2}>
      <Tabs
        value={activeId}
        onChange={(_, value: string) => setSectionId(value)}
        variant="scrollable"
        scrollButtons="auto"
      >
        {sections.map((section) => (
          <Tab
            key={section.id}
            value={section.id}
            label={
              section.files.length > 1
                ? `${section.label} (${section.files.length})`
                : section.label
            }
          />
        ))}
      </Tabs>

      {active.files.length > 1 ? (
        <Stack direction={{ xs: "column", md: "row" }} spacing={2} alignItems="flex-start">
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
            {active.files.map((file) => (
              <ListItemButton
                key={file.relpath}
                dense
                selected={file.relpath === activeFile}
                onClick={() =>
                  setSelected((current) => ({ ...current, [active.id]: file.relpath }))
                }
              >
                <ListItemText
                  primary={pageLabel(file.name)}
                  primaryTypographyProps={{
                    variant: "body2",
                    sx: { wordBreak: "break-word" },
                  }}
                />
              </ListItemButton>
            ))}
          </List>

          <Box sx={{ flex: 1, minWidth: 0 }}>
            <WikiPage relpath={activeFile} />
          </Box>
        </Stack>
      ) : (
        <>
          <Typography variant="caption" color="text.secondary">
            {active.files[0].name}
          </Typography>
          <WikiPage relpath={active.files[0].relpath} />
        </>
      )}
    </Stack>
  );
}
