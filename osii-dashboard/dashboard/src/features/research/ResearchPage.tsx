import { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Alert, Box, Button, ButtonGroup, Card, CardContent, Chip, CircularProgress, Divider, Stack, TextField, Typography } from "@mui/material";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import "katex/dist/katex.min.css";

import { ScopePicker } from "../../components/discovery/ScopePicker";
import { MathpixText } from "../../components/text/MathpixText";
import { writeResearchReport } from "../../api/research";
import { applyReportChanges, exportReport, reportChanges, type Change, type ReportDraft, type ReportFormat, type ReportScope, type ReportSource, type ResearchReport } from "../../domain/research";

type SavedDraft = { scope: ReportScope; prompt: string; format: ReportFormat; report: ReportDraft | null };
type Proposal = { base: string; response: ResearchReport; changes: Change[] };

function readDraft(key: string): SavedDraft | null {
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) ?? "null");
    return saved?.scope && typeof saved.prompt === "string" && ["markdown", "mathpix"].includes(saved.format)
      && (!saved.report || (typeof saved.report.markdown === "string" && Array.isArray(saved.report.sources) && Array.isArray(saved.report.warnings) && saved.report.scope && typeof saved.report.prompt === "string")) ? saved : null;
  } catch { return null; }
}

function download(content: string, extension: string) {
  const url = URL.createObjectURL(new Blob([content], { type: "text/markdown;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url; link.download = `research-report.${extension}`; link.click();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

function ReportMarkdown({ text }: { text: string }) {
  return <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]} components={{
    a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>,
    img: ({ alt }) => <span>{alt}</span>,
  }}>{text}</ReactMarkdown>;
}

export function ResearchPage({ draftKey = "local" }: { draftKey?: string }) {
  const storageKey = `osii:research:v1:${draftKey}`;
  const [params] = useSearchParams();
  const [saved] = useState(() => readDraft(storageKey));
  const initialScope: ReportScope = params.get("file_id") ? { scope_type: "object", file_id: params.get("file_id")! }
    : { scope_type: "collection", collection_id: params.get("collection_id") ?? "" };
  const [scope, setScope] = useState<ReportScope>(params.has("file_id") || params.has("collection_id") ? initialScope : saved?.scope ?? initialScope);
  const [prompt, setPrompt] = useState(saved?.prompt ?? "");
  const [format, setFormat] = useState<ReportFormat>(saved?.format ?? "markdown");
  const [report, setReport] = useState<ReportDraft | null>(saved?.report ?? null);
  const [previous, setPrevious] = useState<ReportDraft | null>(null);
  const [proposal, setProposal] = useState<Proposal | null>(null);
  const [improvement, setImprovement] = useState("");
  const [selectedSource, setSelectedSource] = useState<ReportSource | null>(null);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [storageError, setStorageError] = useState(false);
  const editor = useRef<HTMLTextAreaElement>(null);
  const mounted = useRef(true);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  useEffect(() => {
    try { sessionStorage.setItem(storageKey, JSON.stringify({ scope, prompt, format, report })); setStorageError(false); }
    catch { setStorageError(true); }
  }, [scope, prompt, format, report, storageKey]);
  const ready = Boolean(scope.scope_type === "collection" ? scope.collection_id : scope.file_id);
  const sources = proposal?.response.sources ?? report?.sources ?? [];
  const citedSources = sources.filter(source => report?.markdown.includes(`](${source.href})`));

  const generate = async (revise: boolean) => {
    if (busy || proposal) return;
    setBusy(true); setError(""); setNotice("");
    const original = report;
    try {
      const response = await writeResearchReport(revise && original ? {
        scope: original.scope, prompt: original.prompt, format: original.format,
        current_markdown: original.markdown, improvement, sources: original.sources,
      } : { scope, prompt, format });
      if (!mounted.current) return;
      if (revise && original) {
        const changes = reportChanges(original.markdown, response.markdown);
        if (!changes.length) setNotice("The writer proposed no changes.");
        else { setPrevious(original); setProposal({ base: original.markdown, response, changes }); setEditing(false); }
      } else {
        setPrevious(original); setReport({ ...response, scope, prompt }); setSelectedSource(null); setEditing(false);
      }
    } catch (e) { if (mounted.current) setError((e as Error).message); }
    finally { if (mounted.current) setBusy(false); }
  };

  const decide = (index: number | "all", decision: "accept" | "reject") => {
    if (!proposal || !report) return;
    const changes = proposal.changes.map((change, i) => change.decision === "pending" && (index === "all" || i === index) ? { ...change, decision } : change);
    const markdown = applyReportChanges(proposal.base, changes);
    setReport({ ...report, ...proposal.response, markdown });
    if (changes.every(change => change.decision !== "pending")) {
      setProposal(null); setImprovement(""); setNotice("Review complete. Only accepted changes were applied.");
    } else setProposal({ ...proposal, changes });
  };

  const insert = (prefix: string, suffix = "") => {
    if (!editor.current || !report) return;
    const { selectionStart: start, selectionEnd: end } = editor.current;
    setReport({ ...report, markdown: report.markdown.slice(0, start) + prefix + report.markdown.slice(start, end) + suffix + report.markdown.slice(end) });
    editor.current.focus();
  };
  const inspectLink = (href: string) => {
    const source = sources.find(item => item.href === href);
    if (source) setSelectedSource(source);
    return Boolean(source);
  };

  return <Stack spacing={2.5} sx={{ maxWidth: 1500, mx: "auto" }}>
    <Stack spacing={0.5}><Typography variant="overline" color="primary">From evidence to understanding</Typography>
      <Typography variant="h4" fontWeight={750}>Research reports</Typography>
      <Typography color="text.secondary">Write with your documents. Follow every reference back to the passage behind it.</Typography></Stack>
    <Card variant="outlined"><CardContent><Stack spacing={2}>
      <Box component="fieldset" disabled={busy || Boolean(proposal)} sx={{ border: 0, p: 0, m: 0, minWidth: 0 }}>
        <Stack spacing={2}>
          <ScopePicker value={scope} disabled={busy || Boolean(proposal)} allowedTypes={["collection", "object"]} onChange={value => {
            if (value.scope_type === "collection") setScope({ scope_type: "collection", collection_id: value.collection_id });
            if (value.scope_type === "object") setScope({ scope_type: "object", file_id: value.file_id });
          }} />
          <TextField label="What should this report explore?" value={prompt} onChange={event => setPrompt(event.target.value)} multiline minRows={3} maxRows={16}
            placeholder="Describe your question, audience, desired structure, and anything you want compared or investigated…"
            helperText="Give as much detail as you need. Reports use sampled extracted passages from this selection." inputProps={{ maxLength: 60000 }} />
        </Stack>
      </Box>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
        <Button variant="contained" disabled={!ready || !prompt.trim() || busy || Boolean(proposal)} onClick={() => void generate(false)}>{busy ? "Writing…" : report ? "Generate a new report" : "Write report"}</Button>
        <ButtonGroup size="small" disabled={busy || Boolean(proposal)} aria-label="Report format">
          <Button variant={format === "markdown" ? "contained" : "outlined"} onClick={() => setFormat("markdown")}>Simple Markdown</Button>
          <Button variant={format === "mathpix" ? "contained" : "outlined"} onClick={() => setFormat("mathpix")}>LaTeX / Mathpix</Button>
        </ButtonGroup>
        <Typography variant="caption" color="text.secondary">Draft kept in this browser tab. Export to keep a copy.</Typography>
      </Stack>
    </Stack></CardContent></Card>
    {storageError && <Alert severity="warning">This browser could not save the draft. Export a copy before leaving.</Alert>}
    {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
    {notice && <Alert severity="info" onClose={() => setNotice("")}>{notice}</Alert>}
    {busy && <Stack direction="row" spacing={1.5} alignItems="center" role="status"><CircularProgress size={20} /><Typography>Reading the selected evidence and writing your draft…</Typography></Stack>}
    {!report && !busy && <Card variant="outlined"><CardContent><Typography variant="h6">A report you can check</Typography><Typography color="text.secondary">Select a collection or document, describe your brief, and generate a draft. Click a reference to see the exact excerpt here. Request changes beside the report and approve each change before it becomes part of your text.</Typography></CardContent></Card>}
    {report && <Box sx={{ display: "grid", gridTemplateColumns: { xs: "minmax(0, 1fr)", lg: "minmax(0, 1fr) 360px" }, gap: 2.5, alignItems: "start" }}>
      <Stack spacing={2} sx={{ minWidth: 0 }}>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap alignItems="center">
          <ButtonGroup size="small" disabled={busy || Boolean(proposal)}><Button variant={!editing ? "contained" : "outlined"} onClick={() => setEditing(false)}>Read</Button><Button variant={editing ? "contained" : "outlined"} onClick={() => setEditing(true)}>Edit text</Button></ButtonGroup>
          <Button size="small" onClick={() => download(exportReport(report, window.location.origin), "md")}>Export Markdown</Button>
          <Button size="small" onClick={() => download(exportReport(report, window.location.origin), "mmd")}>Export LaTeX / Mathpix</Button>
          {previous && <Button size="small" disabled={busy || Boolean(proposal)} onClick={() => { const current = report; setReport(previous); setPrevious(current); setSelectedSource(null); }}>Undo / restore</Button>}
        </Stack>
        <Typography variant="caption" color="text.secondary">{report.model ?? "Extractive draft"} · {report.documents_sampled} / {report.documents_in_scope} documents sampled · {citedSources.length} passage links</Typography>
        <Card variant="outlined"><CardContent sx={{ p: { xs: 2, md: 4 } }}>
          {editing ? <Stack spacing={1}>
            <ButtonGroup size="small"><Button onClick={() => insert("**", "**")}>Bold</Button><Button onClick={() => insert("\n## ")}>Heading</Button><Button onClick={() => insert("\n- ")}>List</Button></ButtonGroup>
            <TextField inputRef={editor} disabled={busy || Boolean(proposal)} value={report.markdown} onChange={event => setReport({ ...report, markdown: event.target.value })} multiline minRows={24} fullWidth label="Report text"
              helperText="Edit any wording or bibliography details. Keep source links beside the claims they support. Choose Read to see the formatted report." inputProps={{ maxLength: 120000 }} />
          </Stack> : <Box sx={{ overflowWrap: "anywhere", lineHeight: 1.8, "& h1": { fontSize: "2rem", lineHeight: 1.25 }, "& h2": { mt: 4, lineHeight: 1.35 }, "& a": { color: "primary.main" }, "& blockquote": { borderLeft: "3px solid", borderColor: "primary.light", pl: 2, ml: 0 }, "& table": { display: "block", overflow: "auto", borderCollapse: "collapse" }, "& td, & th": { border: "1px solid", borderColor: "divider", p: 1 }, "& pre": { overflow: "auto" } }}
            onClick={event => {
              const link = (event.target as Element).closest("a");
              if (link && inspectLink(link.getAttribute("href") ?? "")) event.preventDefault();
            }}>
            {report.format === "mathpix" ? <MathpixText text={report.markdown} controls={false} /> : <ReportMarkdown text={report.markdown} />}
          </Box>}
        </CardContent></Card>
        {report.warnings.map((warning, i) => <Typography key={i} variant="caption" color="text.secondary">{warning}</Typography>)}
      </Stack>
      <Stack spacing={2} sx={{ position: { lg: "sticky" }, top: 96, minWidth: 0 }}>
        <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Stack direction="row" justifyContent="space-between"><Typography variant="h6">Behind the reference</Typography>{selectedSource && <Chip size="small" color="primary" label={selectedSource.id} />}</Stack>
          {selectedSource ? <>
            <Typography fontWeight={700}>{selectedSource.filename}</Typography>
            <Typography variant="caption" color="text.secondary">{selectedSource.page != null ? `Page ${selectedSource.page} · ` : ""}Characters {selectedSource.char_start}–{selectedSource.char_end}</Typography>
            <Box component="blockquote" sx={{ m: 0, p: 1.5, borderLeft: "3px solid", borderColor: "primary.main", bgcolor: "action.hover", maxHeight: 300, overflow: "auto", whiteSpace: "pre-wrap", fontSize: "0.9rem" }}>{selectedSource.excerpt}</Box>
            <Typography variant="caption" color="text.secondary">Exact excerpt supplied to the writer. Check whether it supports the report’s claim.</Typography>
            <Button component="a" href={selectedSource.href} target="_blank" rel="noopener" variant="outlined">Open passage in document ↗</Button>
            <Box component="details" sx={{ fontSize: "0.75rem", overflowWrap: "anywhere" }}><summary>Source identity & provenance</summary><p>{selectedSource.source_relpath}</p><p>Representation: {selectedSource.representation_id}</p><p>Extracted text SHA-256: {selectedSource.text_sha256}</p></Box>
          </> : <Typography color="text.secondary" variant="body2">Click a reference in the report to inspect the exact passage without losing your place.</Typography>}
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>{citedSources.map(source => <Chip key={source.id} size="small" variant={selectedSource?.id === source.id ? "filled" : "outlined"} label={source.id} onClick={() => setSelectedSource(source)} />)}</Stack>
        </Stack></CardContent></Card>
        <Card variant="outlined"><CardContent><Stack spacing={1.5}>
          <Typography variant="h6">Make it better</Typography>
          <TextField label="Request improvements" multiline minRows={3} maxRows={10} value={improvement} disabled={busy || Boolean(proposal)} onChange={event => setImprovement(event.target.value)} placeholder="Expand the comparison, clarify the conclusion, or adjust the tone…" inputProps={{ maxLength: 30000 }} />
          <Typography variant="caption" color="text.secondary">Uses this report’s original selection. Changes appear below for your review.</Typography>
          <Button variant="contained" disabled={busy || Boolean(proposal) || !improvement.trim()} onClick={() => void generate(true)}>Propose changes</Button>
        </Stack></CardContent></Card>
        {proposal && <Card variant="outlined" onClick={event => {
          const link = (event.target as Element).closest("a");
          if (link && inspectLink(link.getAttribute("href") ?? "")) event.preventDefault();
        }}><CardContent><Stack spacing={1.5}>
          <Typography variant="h6">Review changes</Typography>
          <Typography variant="body2">{proposal.changes.filter(change => change.decision === "pending").length} changes waiting for review</Typography>
          <Stack direction="row" spacing={1}><Button variant="contained" size="small" onClick={() => decide("all", "accept")}>Accept all</Button><Button size="small" onClick={() => decide("all", "reject")}>Reject remaining</Button></Stack>
          <Divider />
          {proposal.changes.map((change, index) => <Stack key={index} spacing={1}>
            <Typography variant="subtitle2">Change {index + 1}{change.decision !== "pending" ? ` · ${change.decision === "accept" ? "Accepted" : "Rejected"}` : ""}</Typography>
            {change.before && <Box sx={{ p: 1, bgcolor: "rgba(200,40,40,.08)", borderLeft: "3px solid #b83232", whiteSpace: "pre-wrap", fontSize: "0.8rem", overflowWrap: "anywhere", maxHeight: 220, overflow: "auto" }}><Typography variant="caption" fontWeight={700}>Removed</Typography><Box component="del" sx={{ display: "block" }}><ReportMarkdown text={change.before} /></Box></Box>}
            {change.after && <Box sx={{ p: 1, bgcolor: "rgba(20,150,90,.08)", borderLeft: "3px solid #21854b", whiteSpace: "pre-wrap", fontSize: "0.8rem", overflowWrap: "anywhere", maxHeight: 220, overflow: "auto" }}><Typography variant="caption" fontWeight={700}>Added</Typography><Box component="ins" sx={{ display: "block", textDecoration: "none" }}><ReportMarkdown text={change.after} /></Box></Box>}
            {change.decision === "pending" && <Stack direction="row" spacing={1}><Button size="small" onClick={() => decide(index, "accept")}>Accept</Button><Button size="small" color="secondary" onClick={() => decide(index, "reject")}>Reject</Button></Stack>}
          </Stack>)}
        </Stack></CardContent></Card>}
      </Stack>
    </Box>}
  </Stack>;
}
