import { useWorkbenchAvailability } from "../../hooks/useWorkbenchHome";
import { sharedNavigation } from "../../app/layout/workbenchNavigation";
import { WorkbenchHome } from "../home/components/WorkbenchHome";
import { useLocation, useNavigate } from "react-router-dom";
import { ResearchPage } from "../research/ResearchPage";
import { ToolsPage, ToolsWorkbench } from "../files/pages/ToolsPage";
import { LibraryOverviewPage } from "../library/pages/LibraryOverviewPage";
import { DiscoveryIntakePanel } from "../queue/components/DiscoveryIntakePanel";
import type { PickedFile } from "../../components/discovery/LocationBrowser";
import { useQuery } from "@tanstack/react-query";
import { useEffect, useState, type FormEvent } from "react";
import {
  Alert, Accordion, AccordionSummary, AccordionDetails,
  Button,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import {
  FolderOutlined,
  GroupOutlined,
  SettingsOutlined,
} from "@mui/icons-material";
import {
  api,
  type Collection,
  type Doc,
  type Hit,
  type Scope,
  type User,
} from "./api";
import { Intake, UserAdmin } from "./AdminViews";
import { type ProcessorStatus } from "./ProcessorAdmin";
import { Setup, type SetupSection } from "./Setup";
import {
  WorkbenchLayout,
  WorkbenchNavigation,
  type NavigationItem,
} from "../../app/layout/WorkbenchLayout";
import { MoveToInboxOutlined } from "@mui/icons-material";
import { TopicExplorer } from "./TopicExplorer";
import { Collections, CollectionSelection } from "./Collections";

import { DocumentView } from "./DocumentView";
import { AdvancedChat } from "../chat/components/AdvancedChat";
import type { ChatRequest } from "../../api/types";
import { LibraryBrowser } from "./LibraryBrowser";
import { SearchResultCard } from "../search/components/SearchResultCard";
import {
  SearchModeSelect,
  type SearchMode,
} from "../search/components/SearchModeSelect";

const pagePaths: Record<string, string> = { home: "/", files: "/files", browse: "/browse", search: "/search", chat: "/chat", topics: "/topics", collections: "/collections", tools: "/tools", workbench: "/tools/workbench", research: "/research", overview: "/library-overview", inventory: "/inventory", processing: "/intake", setup: "/setup", users: "/users" };

function InventoryPage() {
  const navigate = useNavigate();
  const [selection, setSelection] = useState<number | null>(null);
  const [files, setFiles] = useState<PickedFile[]>([]);
  const capabilities = useQuery({ queryKey: ["discovery", "capabilities"], queryFn: () => api<{ mount_root: string }>("/api/volume/capabilities") });
  return <Stack spacing={2}><Typography variant="h4">File inventory</Typography>
    <Typography color="text.secondary">Scan mounted locations without reading document contents. Freeze a batch, then review and stage processing in Add files.</Typography>
    <DiscoveryIntakePanel selectedId={selection} onSelect={setSelection} directFiles={files} onFiles={setFiles} allowUploads={false} boundaryPath={capabilities.data?.mount_root} />
    <Button variant="contained" disabled={selection === null} onClick={() => navigate(`/intake?selection=${selection}`)}>Review frozen batch in Intake</Button>
  </Stack>;
}

const pages: readonly NavigationItem[] = [
  ...sharedNavigation,
  { id: "inventory", label: "File inventory", group: "start", icon: FolderOutlined },
  { id: "processing", label: "Add files", group: "start", icon: MoveToInboxOutlined },
  { id: "setup", label: "Setup", group: "setup", icon: SettingsOutlined },
  { id: "users", label: "Users", group: "setup", icon: GroupOutlined },
];
const setupAliases: Record<string, SetupSection> = {
  source: "source",
  models: "models",
  processors: "processors",
};
const rootScope: Scope = { scope_type: "root" };

export function Workspace({
  user,
  onLogout,
  onPassword,
}: {
  user: User;
  onLogout: () => void;
  onPassword: () => void;
}) {
  const availability = useWorkbenchAvailability();
  const location = useLocation();
  const route = useNavigate();
  const availablePages = pages.filter(
    (page) =>
      !["processing", "inventory", "setup", "users"].includes(page.id) ||
      user.role === "admin",
  );
  const pageFromHash = () => {
    if (location.pathname.startsWith("/files/")) return "document";
    const hash = window.location.hash.slice(1);
    const id = (hash === "library" ? "files" : hash) || Object.keys(pagePaths).find(key => pagePaths[key] === location.pathname) || (location.pathname.startsWith("/admin/") ? "setup" : location.pathname.startsWith("/files/") ? "files" : "home");
    if (setupAliases[id] && user.role === "admin") return "setup";
    if (id === "tools" || id === "workbench") return id;
    return availablePages.some((page) => page.id === id) ? id : "home";
  };
  const [setupSection, setSetupSection] = useState<SetupSection>(
    setupAliases[window.location.hash.slice(1)] ?? "models",
  );
  const [processingSection, setProcessingSection] = useState<
    "add" | "process" | "activity"
  >("add");
  const [processingPreset, setProcessingPreset] =
    useState<ProcessorStatus | null>(null);
  const [processingPaths, setProcessingPaths] = useState<string[]>([]);
  const [tab, setTab] = useState(pageFromHash);
  const flat = tab !== "browse";
  const [scope, setScope] = useState<Scope>(rootScope);
  const [collections, setCollections] = useState<Collection[]>([]);
  const [folders, setFolders] = useState<{ folder_id: string; path: string }[]>(
    [],
  );
  const [docs, setDocs] = useState<Doc[]>([]);
  const [total, setTotal] = useState(0);
  const [catalogLoading, setCatalogLoading] = useState(false);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("lexical");
  const [hits, setHits] = useState<Hit[]>([]);
  const [selected, setSelected] = useState<Doc | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [detail, setDetail] = useState("");
  const [libraryRevision, setLibraryRevision] = useState(0);
  const currentCollection =
    scope.scope_type === "collection"
      ? collections.find((c) => c.id === scope.collection_id)
      : undefined;
  const scopeName =
    scope.scope_type === "root"
      ? "Entire library"
      : scope.scope_type === "collection"
        ? (currentCollection?.name ?? "Collection")
        : `Folder: ${scope.folder_id}`;
  const fail = (e: unknown) => setError((e as Error).message);
  const navigate = (id: string) => {
    route(pagePaths[id] ?? "/");
    setTab(id);
    setError("");
  };
  useEffect(() => {
    const change = () => {
      setTab(pageFromHash());
      const section = setupAliases[window.location.hash.slice(1)];
      if (section) setSetupSection(section);
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  useEffect(() => {
    setTab(pageFromHash());
    if (location.pathname.startsWith("/admin/")) setSetupSection("processors");
    if (location.pathname === "/intake") setProcessingSection(new URLSearchParams(location.search).get("tab") === "activity" ? "activity" : "add");
    if (location.pathname === "/browse") {
      const folder = new URLSearchParams(location.search).get("folder_id");
      const nextScope: Scope = folder && folder !== "." ? { scope_type: "folder", folder_id: folder } : rootScope;
      if (scope.scope_type !== nextScope.scope_type || scope.folder_id !== nextScope.folder_id) {
        setScope(nextScope);
        setSelectedIds(new Set());
      }
    }
    if (location.pathname === "/search") {
      const params = new URLSearchParams(location.search);
      const term = params.get("q");
      if (term) {
        const selectedScope: Scope = params.get("scope_type") === "collection" ? { scope_type: "collection", collection_id: params.get("collection_id") ?? "" } : params.get("scope_type") === "folder" ? { scope_type: "folder", folder_id: params.get("folder_id") ?? "" } : params.get("scope_type") === "object" ? { scope_type: "object", file_id: params.get("file_id") ?? "" } : rootScope;
        setQuery(term); setMode("lexical"); setScope(selectedScope); setBusy(true);
        void api<{ results: Hit[]; channels_used: string[] }>("/api/search", "POST", { query: term, mode: "lexical", scope: selectedScope }).then(result => { setHits(result.results); setDetail(result.channels_used.join(" · ")); }).catch(fail).finally(() => setBusy(false));
      }
    }

  }, [location.pathname, location.search, location.hash]);
  const refreshCollections = async () => {
    const result = await api<{ items: Collection[] }>("/api/collections");
    setCollections(result.items);
    return result.items;
  };
  useEffect(() => {
    if (!["files", "browse", "search", "chat", "topics", "collections"].includes(tab)) return;
    void refreshCollections().catch(fail);
    void api<{ items: typeof folders }>("/api/catalog/folders")
      .then((r) => setFolders(r.items))
      .catch(fail);
  }, [libraryRevision, tab]);
  const changeScope = (value: Scope) => {
    setScope(value);
    setHits([]);
    setDetail("");
    setSelectedIds(new Set());
    setError("");
  };
  const catalogPath = (cursor?: string) =>
    `/api/catalog/files?limit=500${!flat && scope.scope_type !== "collection" ? "&direct=true" : ""}${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}${scope.collection_id ? `&collection_id=${encodeURIComponent(scope.collection_id)}` : ""}${scope.folder_id ? `&folder_id=${encodeURIComponent(scope.folder_id)}` : ""}`;
  useEffect(() => {
    if (!["files", "browse"].includes(tab)) return;
    let current = true;
    setDocs([]);
    setCatalogLoading(true);
    setNextCursor(null);
    void api<{ items: Doc[]; next_cursor: string | null; total: number }>(
      catalogPath(),
    )
      .then((r) => {
        if (current) {
          setDocs(r.items);
          setNextCursor(r.next_cursor);
          setTotal(r.total);
        }
      })
      .catch((e) => {
        if (current) fail(e);
      }).finally(() => { if (current) setCatalogLoading(false); });
    return () => {
      current = false;
    };
  }, [scope, libraryRevision, flat, tab]);
  const loadMore = async () => {
    try {
      const result = await api<{ items: Doc[]; next_cursor: string | null }>(
        catalogPath(nextCursor ?? ""),
      );
      setDocs((current) => [...current, ...result.items]);
      setNextCursor(result.next_cursor);
    } catch (e) {
      fail(e);
    }
  };
  const documentId = location.pathname.startsWith("/files/") ? decodeURIComponent(location.pathname.slice(7)) : null;
  useEffect(() => {
    let current = true; setSelected(null);
    if (documentId) void api<Doc>(`/api/objects/${encodeURIComponent(documentId)}`).then(doc => { if (current) setSelected(doc); }).catch(fail);
    return () => { current = false; };
  }, [documentId]);
  const open = async (id: string) => { route(`/files/${encodeURIComponent(id)}`); };
  const toggle = (id: string) =>
    setSelectedIds((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const refresh = async () => {
    const items = await refreshCollections();
    if (scope.collection_id && !items.some((c) => c.id === scope.collection_id))
      changeScope(rootScope);
    setLibraryRevision((v) => v + 1);
  };
  const search = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError("");
    setHits([]);
    try {
      const result = await api<{ results: Hit[]; channels_used: string[]; warning?: string }>("/api/search", "POST", { query, mode, scope });
      setHits(result.results);
      setDetail(result.warning || result.channels_used.join(" · ") || "No matching evidence");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };
  const corpusPage = ["files", "browse", "topics", "search", "chat"].includes(
    tab,
  );
  const queueProcessor = (processor: ProcessorStatus) => {
    setProcessingPreset(processor);
    setProcessingPaths([]);
    setProcessingSection("process");
    navigate("processing");
  };
  return (
    <WorkbenchLayout
      navigation={
        <WorkbenchNavigation
          availability={availability}
          items={availablePages}
          selected={documentId ? "files" : tab === "tools" ? "overview" : tab}
          onNavigate={(id) => {
            if (id === "files") changeScope(rootScope);
            navigate(id);
          }}
        />
      }
      footer={
        <Typography variant="caption" color="text.secondary">
          {user.username} · {user.role}
        </Typography>
      }
      actions={
        <>
          <Button color="inherit" onClick={onPassword}>
            Password
          </Button>
          <Button color="inherit" onClick={onLogout}>
            Sign out
          </Button>
        </>
      }
    >
      <Stack spacing={2.5}>
        {error && (
          <Alert severity="error" onClose={() => setError("")}>
            {error}
          </Alert>
        )}
        {tab === "home" && <WorkbenchHome setupPath="/setup" />}
        {corpusPage && !["browse", "files"].includes(tab) && !location.pathname.startsWith("/files/") && (
          <Accordion disableGutters elevation={0} variant="outlined"><AccordionSummary><Typography variant="body2">Scope: {scopeName}</Typography></AccordionSummary><AccordionDetails>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              select
              fullWidth
              label="Document scope"
              value={
                scope.scope_type === "collection"
                  ? `collection:${scope.collection_id}`
                  : scope.scope_type === "folder"
                    ? `folder:${scope.folder_id}`
                    : "root"
              }
              onChange={(e) => {
                const value = e.target.value;
                changeScope(
                  value.startsWith("collection:")
                    ? {
                        scope_type: "collection",
                        collection_id: value.slice(11),
                      }
                    : value.startsWith("folder:")
                      ? { scope_type: "folder", folder_id: value.slice(7) }
                      : rootScope,
                );
              }}
            >
              <MenuItem value="root">Entire library</MenuItem>
              {collections.map((c) => (
                <MenuItem key={c.id} value={`collection:${c.id}`}>
                  {c.visibility === "private" ? "Private" : "Shared"}: {c.name}
                </MenuItem>
              ))}
              {folders
                .filter((f) => f.path !== ".")
                .map((f) => (
                  <MenuItem key={f.folder_id} value={`folder:${f.folder_id}`}>
                    Folder: {f.path}
                  </MenuItem>
                ))}
            </TextField>
            <Button onClick={() => void refresh().catch(fail)}>
              Refresh library
            </Button>
          </Stack></AccordionDetails></Accordion>
        )}
        {(tab === "files" || tab === "browse") && !location.pathname.startsWith("/files/") && (
          <>
            {flat && <Stack direction="row" alignItems="center" spacing={2}><Typography variant="h5" fontWeight={700}>Files <Typography component="span" variant="body2" color="text.secondary">· {total}{scope.scope_type !== "root" ? ` · ${scopeName}` : ""}</Typography></Typography>{scope.scope_type !== "root" && <Button onClick={() => changeScope(rootScope)}>All files</Button>}</Stack>}
            <LibraryBrowser
              loading={catalogLoading}
              flat={flat}
              docs={docs}
              folders={folders}
              scope={scope}
              onScope={value => {
                changeScope(value);
                if (tab === "browse") {
                  const params = new URLSearchParams(location.search);
                  if (value.scope_type === "folder") params.set("folder_id", value.folder_id || ".");
                  else params.delete("folder_id");
                  route({ pathname: "/browse", search: params.toString() });
                }
              }}
              onOpen={(id) => void open(id)}
              selected={selectedIds}
              onToggle={toggle}
            />
            {nextCursor && (
              <Button onClick={() => void loadMore()}>
                Load more documents ({docs.length} of {total} loaded)
              </Button>
            )}
          </>
        )}
        {tab === "collections" && (
          <Collections
            collections={collections}
            user={user}
            refresh={refresh}
            fail={fail}
            choose={() => {
              changeScope(rootScope);
              navigate("files");
            }}
            browse={(id, page) => {
              changeScope({ scope_type: "collection", collection_id: id });
              navigate(page);
            }}
          />
        )}
        {tab === "chat" && <AdvancedChat key={user.id} scope={scope as ChatRequest["scope"]} onOpenEvidence={item => { if (item.file_id) void open(item.file_id); }} />}
        {tab === "search" && (
          <>
            <Stack component="form" spacing={2} onSubmit={search}>
              <Typography variant="h5">
                Search the library
              </Typography>
              <TextField
                label="Search terms or question"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                required
                inputProps={{ maxLength: 4000 }}
              />
              {tab === "search" && (
                <SearchModeSelect value={mode} onChange={setMode} />
              )}
              <Button type="submit" variant="contained" disabled={busy}>
                {busy ? "Working…" : "Search"}
              </Button>
            </Stack>
            {detail && <Typography color="text.secondary">{detail}</Typography>}
            {hits.map((hit, i) => (
              <Stack key={hit.chunk_id ?? i} spacing={0.5}>
                <SearchResultCard
                  result={{
                    fileId: hit.file_id,
                    filename: hit.filename,
                    sourceRelpath: hit.source_relpath,
                    snippet: hit.snippet,
                    score: hit.score ?? 0,
                    mode: tab === "search" ? mode : null,
                    chunkMethod: null,
                    page: null,
                    segmentId: null,
                    overlapWithPrevious: 0,
                    charStart: hit.char_start,
                    charEnd: hit.char_end,
                    collections: [],
                  }}
                  onOpen={() => void open(hit.file_id)}
                />
                <Button
                  size="small"
                  sx={{ alignSelf: "start" }}
                  onClick={() => toggle(hit.file_id)}
                >
                  {selectedIds.has(hit.file_id)
                    ? "Deselect"
                    : "Select for collection"}
                </Button>
              </Stack>
            ))}
          </>
        )}
        {tab === "topics" && (
          <TopicExplorer
            scope={scope}
            open={(id) => void open(id)}
            collections={collections}
            refreshCollections={refresh}
            canEdit={user.role !== "reader"}
          />
        )}
        {corpusPage && tab !== "topics" && selectedIds.size > 0 && (
          <CollectionSelection
            collections={collections}
            refresh={refresh}
            fail={fail}
            selected={selectedIds}
            clear={() => setSelectedIds(new Set())}
            current={currentCollection}
          />
        )}
        {tab === "tools" && <ToolsPage />}
        {tab === "workbench" && <ToolsWorkbench />}
        {tab === "research" && <ResearchPage draftKey={user.id} />}
        {tab === "overview" && <LibraryOverviewPage />}
        {tab === "inventory" && user.role === "admin" && <InventoryPage />}
        {tab === "processing" && user.role === "admin" && (
          <Intake
            key={`${location.search}:${processingSection}:${processingPreset?.id ?? ""}:${processingPaths.join("|")}`}
            initialSection={processingSection}
            initialPaths={processingPaths}
            initialProcessor={processingPreset}
          />
        )}
        {tab === "setup" && user.role === "admin" && (
          <Setup
            section={setupSection}
            onSection={setSetupSection}
            queue={queueProcessor}
            onProcessing={() => {
              setProcessingPreset(null);
              setProcessingPaths([]);
              setProcessingSection("process");
              navigate("processing");
            }}
          />
        )}
        {tab === "users" && user.role === "admin" && <UserAdmin />}
      </Stack>
      {documentId && !selected && !error && <Typography>Loading document…</Typography>}
      {documentId && selected && (
        <DocumentView
          key={selected.file_id}
          doc={selected}
          close={() => route("/files")}
          canEdit={user.role !== "reader"}
          onProcess={
            user.role === "admin"
              ? () => {
                  setProcessingPreset(null);
                  setProcessingSection("process");
                  setProcessingPaths([selected.source_relpath]);
                  setSelected(null);
                  navigate("processing");
                }
              : undefined
          }
        />
      )}
    </WorkbenchLayout>
  );
}
