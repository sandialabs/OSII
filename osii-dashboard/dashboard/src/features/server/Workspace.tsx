import { useEffect, useState, type FormEvent } from "react";
import { Alert, AppBar, Box, Button, Container, Dialog, DialogContent, DialogTitle, Divider, Drawer, IconButton, List, ListItemButton, ListItemIcon, ListItemText, ListSubheader, MenuItem, Paper, Stack, TextField, Toolbar, Typography } from "@mui/material";
import { AccountTreeOutlined, ChatOutlined, CollectionsBookmarkOutlined, FolderOutlined, GroupOutlined, HubOutlined, Menu, Search, SettingsOutlined, StorageOutlined } from "@mui/icons-material";
import { api, type Collection, type Doc, type Hit, type Scope, type User } from "./api";
import { Intake, ModelAdmin, UserAdmin } from "./AdminViews";
import { SourceAdmin } from "./SourceAdmin";
import { TopicExplorer } from "./TopicExplorer";
import { Collections, CollectionSelection } from "./Collections";

import { LibraryBrowser } from "./LibraryBrowser";
import { SearchResultCard } from "../search/components/SearchResultCard";
import { SearchModeSelect, type SearchMode } from "../search/components/SearchModeSelect";

const pages = [
  { id: "library", label: "Library", icon: FolderOutlined }, { id: "collections", label: "Collections", icon: CollectionsBookmarkOutlined },
  { id: "topics", label: "Topic explorer", icon: HubOutlined }, { id: "search", label: "Search", icon: Search }, { id: "chat", label: "Chat", icon: ChatOutlined },
  { id: "processing", label: "Processing", icon: AccountTreeOutlined }, { id: "source", label: "Source & status", icon: StorageOutlined },
  { id: "models", label: "Models", icon: SettingsOutlined }, { id: "users", label: "Users", icon: GroupOutlined },
];
const rootScope: Scope = { scope_type: "root" };
const drawerWidth = 238;

export function Workspace({ user, onLogout, onPassword }: { user: User; onLogout: () => void; onPassword: () => void }) {
  const curator = user.role !== "reader";
  const availablePages = pages.filter(page => ["source", "models", "users"].includes(page.id) ? user.role === "admin" : page.id !== "processing" || curator);
  const pageFromHash = () => availablePages.some(page => page.id === window.location.hash.slice(1)) ? window.location.hash.slice(1) : "library";
  const [tab, setTab] = useState(pageFromHash);
  const [mobileOpen, setMobileOpen] = useState(false);
  const [scope, setScope] = useState<Scope>(rootScope);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [folders, setFolders] = useState<{ folder_id: string; path: string }[]>([]);
  const [docs, setDocs] = useState<Doc[]>([]);
  const [total, setTotal] = useState(0);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("lexical");
  const [hits, setHits] = useState<Hit[]>([]);
  const [answer, setAnswer] = useState("");
  const [history, setHistory] = useState<{ role: string; content: string }[]>([]);
  const [selected, setSelected] = useState<Doc | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState("");
  const [libraryRevision, setLibraryRevision] = useState(0);
  const currentCollection = scope.scope_type === "collection" ? collections.find(c => c.id === scope.collection_id) : undefined;
  const scopeName = scope.scope_type === "root" ? "Entire library" : scope.scope_type === "collection" ? currentCollection?.name ?? "Collection" : `Folder: ${scope.folder_id}`;
  const fail = (e: unknown) => setError((e as Error).message);
  const navigate = (id: string) => { window.location.hash = id; setTab(id); setMobileOpen(false); setError(""); };
  useEffect(() => { const change = () => { setTab(pageFromHash()); setMobileOpen(false); }; window.addEventListener("hashchange", change); return () => window.removeEventListener("hashchange", change); }, []);
  const refreshCollections = async () => { const result = await api<{ items: Collection[] }>("/api/collections"); setCollections(result.items); return result.items; };
  useEffect(() => { void refreshCollections().catch(fail); void api<{ items: typeof folders }>("/api/catalog/folders").then(r => setFolders(r.items)).catch(fail); }, [libraryRevision]);
  const changeScope = (value: Scope) => { setScope(value); setHistory([]); setHits([]); setAnswer(""); setDetail(""); setSelectedIds(new Set()); setError(""); };
  const catalogPath = (cursor?: string) => `/api/catalog/files?limit=100${scope.scope_type !== "collection" ? "&direct=true" : ""}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}${scope.collection_id ? `&collection_id=${encodeURIComponent(scope.collection_id)}` : ""}${scope.folder_id ? `&folder_id=${encodeURIComponent(scope.folder_id)}` : ""}`;
  useEffect(() => {
    let current = true; setDocs([]); setNextCursor(null);
    void api<{ items: Doc[]; next_cursor: string | null; total: number }>(catalogPath()).then(r => { if (current) { setDocs(r.items); setNextCursor(r.next_cursor); setTotal(r.total); } }).catch(e => { if (current) fail(e); });
    return () => { current = false; };
  }, [scope, libraryRevision]);
  const loadMore = async () => { try { const result = await api<{ items: Doc[]; next_cursor: string | null }>(catalogPath(nextCursor ?? "")); setDocs(current => [...current, ...result.items]); setNextCursor(result.next_cursor); } catch (e) { fail(e); } };
  const open = async (id: string) => { try { setSelected(await api<Doc>(`/api/objects/${id}`)); } catch (e) { fail(e); } };
  const toggle = (id: string) => setSelectedIds(current => { const next = new Set(current); if (next.has(id)) next.delete(id); else next.add(id); return next; });
  const refresh = async () => { const items = await refreshCollections(); if (scope.collection_id && !items.some(c => c.id === scope.collection_id)) changeScope(rootScope); setLibraryRevision(v => v + 1); };
  const search = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError(""); setAnswer(""); setHits([]);
    try {
      if (tab === "chat") {
        const result = await api<{ answer: string; citations: Hit[]; provider: string; fallback_used: boolean; retrieval_mode: string }>("/api/chat", "POST", { query, history, scope });
        setAnswer(result.answer); setHits(result.citations); setDetail(`${result.provider} · ${result.retrieval_mode}${result.fallback_used ? " · extractive fallback" : ""}`);
        setHistory(current => [...current, { role: "user", content: query }, { role: "assistant", content: result.answer }].slice(-12));
      } else {
        const result = await api<{ results: Hit[]; channels_used: string[]; warning?: string }>("/api/search", "POST", { query, mode, scope }); setHits(result.results); setDetail(result.warning || result.channels_used.join(" · ") || "No matching evidence");
      }
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const nav = <><Toolbar /><List subheader={<ListSubheader>Shared library</ListSubheader>}>{availablePages.map(page => <ListItemButton key={page.id} selected={tab === page.id} onClick={() => navigate(page.id)}><ListItemIcon><page.icon /></ListItemIcon><ListItemText primary={page.label} /></ListItemButton>)}</List><Box sx={{ mt: "auto", p: 2 }}><Typography variant="caption" color="text.secondary">{user.username} · {user.role}</Typography></Box></>;
  const corpusPage = ["library", "topics", "search", "chat"].includes(tab);

  return <Box sx={{ display: "flex", minHeight: "100vh" }}>
    <AppBar position="fixed" sx={{ zIndex: theme => theme.zIndex.drawer + 1 }}><Toolbar><IconButton color="inherit" aria-label="Open navigation" onClick={() => setMobileOpen(true)} sx={{ display: { md: "none" } }}><Menu /></IconButton><Typography variant="h6" sx={{ flex: 1 }}>OSII<Box component="span" sx={{ display: { xs: "none", sm: "inline" } }}> · Shared library</Box></Typography><Button color="inherit" onClick={onPassword}>Password</Button><Button color="inherit" onClick={onLogout}>Sign out</Button></Toolbar></AppBar>
    <Box component="nav" aria-label="Main navigation" sx={{ width: { md: drawerWidth }, flexShrink: { md: 0 } }}><Drawer variant="temporary" open={mobileOpen} onClose={() => setMobileOpen(false)} sx={{ display: { xs: "block", md: "none" }, "& .MuiDrawer-paper": { width: drawerWidth, display: "flex" } }}>{nav}</Drawer><Drawer variant="permanent" sx={{ display: { xs: "none", md: "block" }, "& .MuiDrawer-paper": { width: drawerWidth, boxSizing: "border-box", display: "flex" } }}>{nav}</Drawer></Box>
    <Box component="main" sx={{ flexGrow: 1, minWidth: 0 }}><Toolbar /><Container maxWidth="lg" sx={{ py: 3 }}><Stack spacing={3}>
      {error && <Alert severity="error" onClose={() => setError("")}>{error}</Alert>}
      {corpusPage && <Stack direction={{ xs: "column", sm: "row" }} spacing={2}><TextField select fullWidth label="Document scope" value={scope.scope_type === "collection" ? `collection:${scope.collection_id}` : scope.scope_type === "folder" ? `folder:${scope.folder_id}` : "root"} onChange={e => { const value = e.target.value; changeScope(value.startsWith("collection:") ? { scope_type: "collection", collection_id: value.slice(11) } : value.startsWith("folder:") ? { scope_type: "folder", folder_id: value.slice(7) } : rootScope); }}><MenuItem value="root">Entire library</MenuItem>{collections.map(c => <MenuItem key={c.id} value={`collection:${c.id}`}>{c.visibility === "private" ? "Private" : "Shared"}: {c.name}</MenuItem>)}{folders.filter(f => f.path !== ".").map(f => <MenuItem key={f.folder_id} value={`folder:${f.folder_id}`}>Folder: {f.path}</MenuItem>)}</TextField><Button onClick={() => void refresh().catch(fail)}>Refresh library</Button></Stack>}
      {tab === "library" && <><Typography variant="h5">{scopeName}</Typography><Typography color="text.secondary">{total} documents · Select files to create your own collection.</Typography>{!docs.length && <Alert severity="info">No indexed documents in this scope. A curator can process source files to make them available.</Alert>}<LibraryBrowser docs={docs} folders={folders} scope={scope} onScope={changeScope} onOpen={id => void open(id)} selected={selectedIds} onToggle={toggle} />{nextCursor && <Button onClick={() => void loadMore()}>Load more documents</Button>}</>}
      {tab === "collections" && <Collections collections={collections} user={user} refresh={refresh} fail={fail} choose={() => { changeScope(rootScope); navigate("library"); }} browse={(id, page) => { changeScope({ scope_type: "collection", collection_id: id }); navigate(page); }} />}
      {(tab === "search" || tab === "chat") && <><Stack component="form" spacing={2} onSubmit={search}><Typography variant="h5">{tab === "chat" ? "Ask the library" : "Search the library"}</Typography>{tab === "chat" && <Button sx={{ alignSelf: "start" }} onClick={() => { setHistory([]); setAnswer(""); setHits([]); }}>New conversation</Button>}<TextField label={tab === "chat" ? "Question" : "Search terms or question"} value={query} onChange={e => setQuery(e.target.value)} required inputProps={{ maxLength: 4000 }} />{tab === "search" && <SearchModeSelect value={mode} onChange={setMode} />}<Button type="submit" variant="contained" disabled={busy}>{busy ? "Working…" : tab === "chat" ? "Ask" : "Search"}</Button></Stack>{detail && <Typography color="text.secondary">{detail}</Typography>}{answer && <Paper sx={{ p: 3, whiteSpace: "pre-wrap" }}>{answer}</Paper>}{hits.map((hit, i) => <Stack key={hit.chunk_id ?? i} spacing={0.5}><SearchResultCard result={{ fileId: hit.file_id, filename: hit.filename,
        sourceRelpath: hit.source_relpath, snippet: hit.snippet, score: hit.score ?? 0, mode: tab === "search" ? mode : null,
        chunkMethod: null, page: null, segmentId: null, overlapWithPrevious: 0, charStart: hit.char_start, charEnd: hit.char_end, collections: [] }}
        onOpen={() => void open(hit.file_id)} /><Button size="small" sx={{ alignSelf: "start" }} onClick={() => toggle(hit.file_id)}>{selectedIds.has(hit.file_id) ? "Deselect" : "Select for collection"}</Button></Stack>)}</>}
      {tab === "topics" && <TopicExplorer scope={scope} open={id => void open(id)} onSelect={id => setSelectedIds(current => new Set([...current, id]))} />}
      {corpusPage && selectedIds.size > 0 && <CollectionSelection collections={collections} refresh={refresh} fail={fail} selected={selectedIds} clear={() => setSelectedIds(new Set())} current={currentCollection} />}
      {tab === "processing" && curator && <Intake />}{tab === "source" && user.role === "admin" && <SourceAdmin />}{tab === "models" && user.role === "admin" && <ModelAdmin />}{tab === "users" && user.role === "admin" && <UserAdmin />}
    </Stack></Container></Box>
    <Dialog open={Boolean(selected)} onClose={() => setSelected(null)} fullWidth maxWidth="lg"><DialogTitle>{selected?.filename}</DialogTitle><DialogContent><Stack spacing={2}><Button component="a" href={`/api/objects/${selected?.file_id}/source`} target="_blank" rel="noopener">Open original source</Button>{selected?.media_type === "application/pdf" && <Box component="iframe" title="Source PDF" src={`/api/objects/${selected.file_id}/source`} sx={{ height: 500, border: 0 }} />}<Divider /><Typography variant="h6">Extracted evidence</Typography><Typography component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontFamily: "inherit" }}>{selected?.text}</Typography></Stack></DialogContent></Dialog>
  </Box>;
}
