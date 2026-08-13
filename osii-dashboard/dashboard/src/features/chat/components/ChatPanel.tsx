// src/features/chat/components/ChatPanel.tsx
import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  CircularProgress,
  Divider,
  Link,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SendOutlinedIcon from "@mui/icons-material/SendOutlined";
import OpenInNewOutlinedIcon from "@mui/icons-material/OpenInNewOutlined";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import { useNavigate } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import { useChat } from "../../../hooks/useChat";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { useCollection } from "../../../hooks/useCollections";
import { getObjectSourceUrl } from "../../../api/source";
import type {
  ChatCitation,
  ChatMessage,
  ScopeDescribeRequest,
} from "../../../api/types";
import { buildCollectionRoute, buildFileRoute } from "../../../utils/routes";
import { RecentActivity } from "../../../components/discovery/RecentActivity";
import { ScopeSuggestions } from "../../../components/discovery/ScopeSuggestions";
import { useActivityHistory } from "../../../hooks/useActivityHistory";

type ChatPanelProps = {
  scope: ScopeDescribeRequest;
};

type DisplayChatMessage = ChatMessage & {
  citations?: ChatCitation[];
  provider?: string;
  fallbackUsed?: boolean;
};

function scopeLabel(scope: ScopeDescribeRequest): string {
  if (scope.scope_type === "root") return "Root";
  if (scope.scope_type === "folder") return "Folder";
  if (scope.scope_type === "collection") return "Collection";
  return "File";
}

function prepareAnswerMarkdown(text: string): string {
  return text.replace(/【(\d+)†L\d+(?:-L?\d+)?】/g, (_match, sourceNumber) => {
    return ` [${sourceNumber}](citation:${sourceNumber})`;
  });
}

function getCitationForMarker(
  marker: string,
  citations: ChatCitation[] | undefined,
): ChatCitation | null {
  const index = Number(marker) - 1;

  if (!citations || !Number.isInteger(index) || index < 0) {
    return null;
  }

  return citations[index] ?? null;
}

function CitationThumbnail({
  fileId,
  filename,
}: {
  fileId: string;
  filename: string;
}) {
  const lower = filename.toLowerCase();
  const isPdf = lower.endsWith(".pdf");
  const sourceUrl = isPdf ? getObjectSourceUrl(fileId) : null;
  const { thumbnailUrl } = usePdfThumbnail(sourceUrl, Boolean(sourceUrl));

  if (thumbnailUrl) {
    return (
      <img
        src={thumbnailUrl}
        alt={`${filename} thumbnail`}
        style={{
          width: 84,
          height: 84,
          objectFit: "cover",
          borderRadius: 8,
          border: "1px solid rgba(15,23,42,0.12)",
          display: "block",
          flexShrink: 0,
        }}
      />
    );
  }

  return (
    <Box
      sx={{
        width: 84,
        height: 84,
        borderRadius: 1.25,
        border: (theme) => `1px solid ${theme.palette.divider}`,
        backgroundColor: "background.paper",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        flexShrink: 0,
      }}
    >
      {isPdf ? (
        <PictureAsPdfOutlinedIcon color="error" />
      ) : (
        <DescriptionOutlinedIcon color="action" />
      )}
    </Box>
  );
}

export function ChatPanel({ scope }: ChatPanelProps) {
  const navigate = useNavigate();
  const chatMutation = useChat();
  const recentPrompts = useActivityHistory("chat_prompt");

  const [input, setInput] = useState("");
  const [history, setHistory] = useState<DisplayChatMessage[]>([]);

  const collectionQuery = useCollection(
    scope.scope_type === "collection" ? scope.collection_id : "",
    scope.scope_type === "collection",
  );

  const handleSend = async () => {
    const query = input.trim();
    if (!query) return;
    recentPrompts.add({ text: query, scope });

    const requestHistory: ChatMessage[] = history.map((message) => ({
      role: message.role,
      content: message.content,
    }));

    const nextHistory: DisplayChatMessage[] = [
      ...history,
      { role: "user", content: query },
    ];

    setHistory(nextHistory);
    setInput("");

    try {
      const response = await chatMutation.mutateAsync({
        query,
        scope,
        history: requestHistory,
      });

      setHistory([
        ...nextHistory,
        {
          role: "assistant",
          content: response.answer,
          citations: response.citations,
          provider: response.provider,
          fallbackUsed: response.fallback_used,
        },
      ]);
    } catch (error) {
      setHistory([
        ...nextHistory,
        {
          role: "assistant",
          content:
            error instanceof Error
              ? `Chat request failed: ${error.message}`
              : "Chat request failed.",
        },
      ]);
    }
  };

  const latestAssistantMessage = [...history]
    .reverse()
    .find((message) => message.role === "assistant" && message.citations?.length);

  const latestCitations = latestAssistantMessage?.citations ?? chatMutation.data?.citations ?? [];

  const scopeDisplay = useMemo(() => {
    if (scope.scope_type === "root") {
      return {
        label: "Root",
        value: "All files",
        href: null as string | null,
      };
    }

    if (scope.scope_type === "folder") {
      return {
        label: "Folder",
        value: scope.folder_id,
        href: null as string | null,
      };
    }

    if (scope.scope_type === "collection") {
      return {
        label: "Collection",
        value: collectionQuery.data?.collection.name ?? scope.collection_id,
        href: buildCollectionRoute(scope.collection_id),
      };
    }

    return {
      label: "File",
      value: scope.file_id,
      href: null as string | null,
    };
  }, [scope, collectionQuery.data?.collection.name]);

  return (
    <Stack spacing={2.25}>
      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
        <Chip label={scopeDisplay.label} size="small" color="primary" variant="outlined" />
        {scopeDisplay.href ? (
          <Link
            component="button"
            type="button"
            underline="hover"
            color="text.secondary"
            onClick={() => navigate(scopeDisplay.href!)}
            sx={{ fontSize: "0.8rem" }}
          >
            {scopeDisplay.value}
          </Link>
        ) : (
          <Typography variant="caption" color="text.secondary">
            {scopeDisplay.value}
          </Typography>
        )}
      </Stack>

      <Card
        sx={{
          background:
            "linear-gradient(135deg, rgba(20,184,166,0.10), rgba(6,182,212,0.05) 55%, rgba(255,255,255,1) 100%)",
          borderColor: "rgba(20,184,166,0.18)",
        }}
      >
        <CardContent>
          <Stack spacing={1.5}>
            <Stack spacing={0.5}>
              <Typography variant="subtitle1" fontWeight={700}>
                Ask a grounded question
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Answers are grounded in the current scope and linked back to source evidence.
              </Typography>
            </Stack>

            <TextField
              fullWidth
              multiline
              minRows={3}
              label="Question"
              value={input}
              onChange={(event) => setInput(event.target.value)}
              placeholder="What does this scope say about calibration drift?"
              sx={{
                "& .MuiOutlinedInput-root": {
                  backgroundColor: "rgba(255,255,255,0.85)",
                },
              }}
            />

            <Button
              variant="contained"
              endIcon={<SendOutlinedIcon />}
              onClick={() => void handleSend()}
              disabled={chatMutation.isPending || !input.trim()}
              sx={{ alignSelf: "flex-start" }}
            >
              Send
            </Button>
          </Stack>
        </CardContent>
      </Card>

      <ScopeSuggestions scope={scope} mode="questions" onSelect={setInput} />

      <RecentActivity
        kind="chat_prompt"
        entries={recentPrompts.entries}
        onSelect={(entry) => setInput(entry.text)}
        onDelete={recentPrompts.remove}
        onClear={recentPrompts.clear}
      />

      {history.length === 0 ? (
        <Typography variant="body2" color="text.secondary">
          No answers yet. Choose a suggested question, reuse a recent prompt, or write your own.
        </Typography>
      ) : (
        <Stack spacing={1.5}>
          {history.map((message, index) => (
            <Card key={`${message.role}-${index}`} variant="outlined">
              <CardContent sx={{ py: 1.25 }}>
                <Stack spacing={0.75}>
                  <Typography variant="caption" color="text.secondary">
                    {message.role === "user" ? "You" : `Assistant · ${message.provider ?? "unknown provider"}${message.fallbackUsed ? " (fallback)" : ""}`}
                  </Typography>

                  {message.role === "assistant" ? (
                    <Box
                      sx={{
                        "& p": { mt: 0, mb: 1.1 },
                        "& ul, & ol": { pl: 3, my: 1 },
                        "& li": { mb: 0.5 },
                        "& pre": {
                          overflowX: "auto",
                          p: 1,
                          borderRadius: 1,
                          backgroundColor: "rgba(15,23,42,0.04)",
                        },
                        "& code": {
                          fontFamily: 'Consolas, "Courier New", monospace',
                        },
                        "& a": {
                          color: "primary.main",
                          fontWeight: 700,
                          textDecoration: "none",
                        },
                      }}
                    >
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm, remarkMath]}
                        rehypePlugins={[rehypeKatex]}
                        components={{
                          a: (props) => {
                            const href = String(props.href ?? "");

                            if (href.startsWith("citation:")) {
                              const marker = href.replace("citation:", "");
                              const citation = getCitationForMarker(marker, message.citations);

                              return (
                                <Box
                                  component="button"
                                  type="button"
                                  onClick={() => {
                                    if (!citation) return;

                                    navigate(
                                      buildFileRoute({
                                        fileId: citation.file_id,
                                        charStart: citation.char_start,
                                        charEnd: citation.char_end,
                                        page: citation.page,
                                        segmentId: citation.segment_id,
                                      }),
                                    );
                                  }}
                                  title={citation?.filename ?? `Citation ${marker}`}
                                  sx={{
                                    border: "1px solid rgba(20,184,166,0.35)",
                                    backgroundColor: citation
                                      ? "rgba(20,184,166,0.10)"
                                      : "rgba(15,23,42,0.06)",
                                    color: "primary.main",
                                    borderRadius: 999,
                                    px: 0.65,
                                    py: 0.05,
                                    mx: 0.15,
                                    fontSize: "0.72rem",
                                    fontWeight: 700,
                                    cursor: citation ? "pointer" : "default",
                                  }}
                                >
                                  {marker}
                                </Box>
                              );
                            }

                            return (
                              <a
                                href={href}
                                target="_blank"
                                rel="noreferrer"
                              >
                                {props.children}
                              </a>
                            );
                          },
                        }}
                      >
                        {prepareAnswerMarkdown(message.content)}
                      </ReactMarkdown>
                    </Box>
                  ) : (
                    <Typography variant="body2" sx={{ whiteSpace: "pre-wrap" }}>
                      {message.content}
                    </Typography>
                  )}
                </Stack>
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {chatMutation.isPending ? (
        <Stack direction="row" spacing={1} alignItems="center">
          <CircularProgress size={18} />
          <Typography variant="body2">Generating answer…</Typography>
        </Stack>
      ) : null}

      {latestCitations.length > 0 ? (
        <Stack spacing={1}>
          <Stack direction="row" spacing={1} alignItems="center">
            <AutoAwesomeOutlinedIcon color="primary" fontSize="small" />
            <Typography variant="subtitle2" fontWeight={600}>
              Sources
            </Typography>
          </Stack>

          <Stack spacing={1.25}>
            {latestCitations.map((citation, index) => (
              <Card key={`${citation.file_id}-${citation.chunk_id}-${index}`}>
                <CardActionArea
                  onClick={() =>
                    navigate(
                      buildFileRoute({
                        fileId: citation.file_id,
                        charStart: citation.char_start,
                        charEnd: citation.char_end,
                        page: citation.page,
                        segmentId: citation.segment_id,
                      }),
                    )
                  }
                >
                  <CardContent>
                    <Stack direction="row" spacing={1.25} alignItems="flex-start">
                      <CitationThumbnail
                        fileId={citation.file_id}
                        filename={citation.filename ?? citation.file_id}
                      />

                      <Stack spacing={0.75} sx={{ minWidth: 0, flex: 1 }}>
                        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                          <Chip
                            label={`Source ${index + 1}`}
                            size="small"
                            color="primary"
                            variant="outlined"
                          />
                          <Typography variant="subtitle2" fontWeight={600}>
                            {citation.filename ?? citation.file_id}
                          </Typography>
                        </Stack>

                        {citation.source_relpath ? (
                          <Typography variant="caption" color="text.secondary">
                            {citation.source_relpath}
                          </Typography>
                        ) : null}

                        <Box
                          sx={{
                            p: 1,
                            borderRadius: 1,
                            backgroundColor: "rgba(20,184,166,0.08)",
                            border: "1px solid rgba(20,184,166,0.18)",
                          }}
                        >
                          <Typography
                            variant="body2"
                            sx={{
                              whiteSpace: "pre-wrap",
                              wordBreak: "break-word",
                              lineHeight: 1.55,
                            }}
                          >
                            {citation.snippet ?? "No snippet available."}
                          </Typography>
                        </Box>

                        <Divider />

                        <Button
                          size="small"
                          variant="outlined"
                          startIcon={<OpenInNewOutlinedIcon />}
                          onClick={(event) => {
                            event.stopPropagation();
                            navigate(
                              buildFileRoute({
                                fileId: citation.file_id,
                                charStart: citation.char_start,
                                charEnd: citation.char_end,
                                page: citation.page,
                                segmentId: citation.segment_id,
                              }),
                            );
                          }}
                          sx={{ alignSelf: "flex-start" }}
                        >
                          Open Source
                        </Button>
                      </Stack>
                    </Stack>
                  </CardContent>
                </CardActionArea>
              </Card>
            ))}
          </Stack>
        </Stack>
      ) : null}

      {chatMutation.isError ? (
        <Alert severity="error">
          {chatMutation.error instanceof Error
            ? chatMutation.error.message
            : "Chat failed."}
        </Alert>
      ) : null}
    </Stack>
  );
}
