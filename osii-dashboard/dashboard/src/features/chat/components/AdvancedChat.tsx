import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Accordion, AccordionDetails, AccordionSummary, Alert, Button, Paper, Stack, TextField, Typography } from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { chat, compareRag, getRagProfiles } from "../../../api/chat";
import type { ChatMessage, ChatRequest, ChatResponse } from "../../../api/types";
import type { TraceEvidence } from "../traceTypes";
import type { RagComparison } from "../types";
import { AgentTraceViewer } from "./AgentTraceViewer";
import { RagComparisonPanel, RagProfileControls } from "./RagExperiments";

/** Chat composition over Core clients. No browser-persisted private conversations. */
export function AdvancedChat({ scope, onOpenEvidence }: {
  scope: ChatRequest["scope"]; onOpenEvidence: (item: TraceEvidence) => void;
}) {
  const catalog = useQuery({ queryKey: ["rag-profiles"], queryFn: getRagProfiles });
  const answerMutation = useMutation({ mutationFn: chat });
  const comparisonMutation = useMutation({ mutationFn: compareRag });
  const [profile, setProfile] = useState("hybrid-v1");
  const [compareIds, setCompareIds] = useState(["lexical-v1", "hybrid-v1"]);
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<(ChatMessage & { response?: ChatResponse })[]>([]);
  const [comparison, setComparison] = useState<RagComparison | null>(null);
  const epoch = useRef(0);
  const scopeKey = JSON.stringify(scope);
  const busy = answerMutation.isPending || comparisonMutation.isPending;
  function clear() {
    epoch.current++; setMessages([]); setComparison(null);
    answerMutation.reset(); comparisonMutation.reset();
  }
  useEffect(() => { clear(); return () => { epoch.current++; }; }, [scopeKey]);
  function history(): ChatMessage[] {
    const value = messages.map(({ role, content }) => ({ role, content })).slice(-12);
    while (value.reduce((count, item) => count + item.content.length, 0) > 12000) value.shift();
    return value;
  }
  async function send() {
    const query = input.trim(); if (!query || busy) return;
    const current = epoch.current;
    const past = history();
    setMessages(value => [...value, { role: "user", content: query }]); setInput("");
    try {
      const response = await answerMutation.mutateAsync({ query, scope, history: past, profile_id: profile });
      if (epoch.current === current) setMessages(value => [...value, { role: "assistant", content: response.answer, response }]);
    } catch { /* The mutation exposes its error below. */ }
  }
  async function compare() {
    const query = input.trim(); if (!query || busy) return;
    const current = epoch.current; setComparison(null);
    try {
      const result = await comparisonMutation.mutateAsync({ query, scope, history: history(), profile_ids: compareIds });
      if (epoch.current === current) setComparison(result);
    } catch { /* The mutation exposes its error below. */ }
  }
  return <Stack spacing={2} sx={{ minWidth: 0 }}>
    <Typography variant="h5">Ask the library</Typography>
    <Button sx={{ alignSelf: "start" }} onClick={clear}>New conversation</Button>
    {catalog.data && <RagProfileControls catalog={catalog.data} selected={profile}
      onSelect={value => { clear(); setProfile(value); }} comparison={compareIds} onComparison={setCompareIds}
      busy={busy} onCompare={() => void compare()} canCompare={Boolean(input.trim())} />}
    {catalog.error && <Alert severity="warning">Could not load RAG strategies: {catalog.error.message}</Alert>}
    <Stack component="form" spacing={1} onSubmit={event => { event.preventDefault(); void send(); }}>
      <TextField label="Question" value={input} onChange={event => setInput(event.target.value)} multiline minRows={2} inputProps={{ maxLength: 4000 }} />
      <Button type="submit" variant="contained" disabled={busy || !input.trim()} sx={{ alignSelf: "start" }}>{busy ? "Working…" : "Ask"}</Button>
    </Stack>
    {answerMutation.error && <Alert severity="error">{answerMutation.error.message}</Alert>}
    {comparisonMutation.error && <Alert severity="error">{comparisonMutation.error.message}</Alert>}
    {comparisonMutation.isPending && <Typography>Comparing strategies…</Typography>}
    {comparison && catalog.data && <RagComparisonPanel value={comparison} catalog={catalog.data} onOpenEvidence={onOpenEvidence} />}
    {messages.map((message, i) => <Paper variant="outlined" key={i} sx={{ p: 2, minWidth: 0 }}><Stack spacing={1.5}>
      <Typography variant="subtitle2">{message.role === "user" ? "You" : `Assistant · ${message.response?.model ?? message.response?.provider}`}</Typography>
      {message.response?.error && <Alert severity="error">{message.response.error}</Alert>}
      <Typography sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere" }}>{message.content}</Typography>
      {message.response?.citations.map((citation, n) => <Button key={`${citation.chunk_id}-${n}`} sx={{ alignSelf: "start" }} onClick={() => onOpenEvidence({ file_id: citation.file_id, source_relpath: citation.source_relpath ?? undefined,
        char_start: citation.char_start ?? undefined, char_end: citation.char_end ?? undefined, source_origin: citation.source_origin ?? undefined })}>Source {n + 1}: {citation.source_relpath ?? citation.file_id}</Button>)}
      {message.response?.agent_trace && <Accordion disableGutters><AccordionSummary expandIcon={<ExpandMoreIcon />}>Inspect agent trace · {message.response.agent_trace.stop_reason}</AccordionSummary><AccordionDetails sx={{ p: { xs: 0, md: 1 } }}><AgentTraceViewer trace={message.response.agent_trace} onOpenEvidence={onOpenEvidence} /></AccordionDetails></Accordion>}
    </Stack></Paper>)}
  </Stack>;
}
