import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  CircularProgress,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import AutoAwesomeOutlinedIcon from "@mui/icons-material/AutoAwesomeOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { ScopeDescribeRequest, SearchMode } from "../../../api/types";
import { useCollections } from "../../../hooks/useCollections";
import { useSearch } from "../../../hooks/useSearch";
import { buildFileRoute } from "../../../utils/routes";
import { toSearchResultModel, type SearchResultModel } from "../../../domain/search";
import { SearchResultCard } from "../components/SearchResultCard";
import { RecentActivity } from "../../../components/discovery/RecentActivity";
import { ScopeSuggestions } from "../../../components/discovery/ScopeSuggestions";
import { useActivityHistory } from "../../../hooks/useActivityHistory";
import type { ActivityHistoryEntry } from "../../../utils/activityHistory";

import { ToolContext } from "../../../components/workbench/ToolContext";
import { SearchModeSelect } from "../components/SearchModeSelect";

function coerceMode(value: string | null): SearchMode {
  if (value === "semantic" || value === "lexical" || value === "hybrid") {
    return value;
  }
  return "lexical";
}

export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const recentSearches = useActivityHistory("search");

  const initialQuery = searchParams.get("q") ?? "";
  const initialMode = coerceMode(searchParams.get("mode"));
  const submittedCollection = searchParams.get("scope_type") === "collection" ? searchParams.get("collection_id") ?? "" : "";

  const [queryInput, setQueryInput] = useState(initialQuery);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [scopeType, setScopeType] = useState(submittedCollection ? "collection" : "root");
  const [collectionId, setCollectionId] = useState(submittedCollection);
  const [panel, setPanel] = useState<"options" | "keywords" | "history" | null>(null);
  const { data: collectionsData } = useCollections(panel === "options");

  useEffect(() => {
    setQueryInput(initialQuery);
    setMode(initialMode);
    setScopeType(submittedCollection ? "collection" : "root");
    setCollectionId(submittedCollection);
  }, [initialQuery, initialMode, submittedCollection]);

  const searchScope = (id: string): ScopeDescribeRequest =>
    id ? { scope_type: "collection", collection_id: id } : { scope_type: "root" };
  const effectiveScope = searchScope(scopeType === "collection" ? collectionId : "");
  const query = initialQuery;
  const hasSearched = Boolean(query.trim());
  const scopeSelected = scopeType !== "collection" || Boolean(collectionId);
  const keywordScope = scopeSelected ? effectiveScope : searchScope(submittedCollection);

  const { data, isLoading, isError, error } = useSearch({
    query,
    mode: initialMode,
    scope: searchScope(submittedCollection),
    topK: 12,
    enabled: hasSearched,
  });

  const results = useMemo(
    () => (data?.results ?? []).map(toSearchResultModel),
    [data?.results],
  );

  const runSearch = (
    text: string,
    nextMode: SearchMode,
    nextScope: ScopeDescribeRequest,
  ) => {
    const cleanText = text.trim();
    if (!cleanText) return;
    const next = new URLSearchParams();
    next.set("q", cleanText);
    next.set("mode", nextMode);
    next.set("scope_type", nextScope.scope_type);
    setQueryInput(cleanText);
    setMode(nextMode);
    if (nextScope.scope_type === "collection") {
      next.set("collection_id", nextScope.collection_id);
      setScopeType("collection");
      setCollectionId(nextScope.collection_id);
    } else {
      setScopeType("root");
      setCollectionId("");
    }
    setPanel(null);
    recentSearches.add({ text: cleanText, scope: nextScope, mode: nextMode });
    navigate(`/search?${next.toString()}`);
  };

  const handleSearch = () => runSearch(queryInput, mode, effectiveScope);

  const handleRecentSearch = (entry: ActivityHistoryEntry) => {
    const supportedScope = entry.scope.scope_type === "collection" ? entry.scope : { scope_type: "root" as const };
    runSearch(entry.text, entry.mode ?? "semantic", supportedScope);
  };

  const handleOpen = (result: SearchResultModel) => {
    navigate(
      buildFileRoute({
        fileId: result.fileId,
        charStart: result.charStart,
        charEnd: result.charEnd,
        page: result.page,
        segmentId: result.segmentId,
      }),
    );
  };

  return (
    <Stack spacing={1.5}>
      <Box component="form" role="search" onSubmit={event => {
        event.preventDefault();
        if (scopeSelected) handleSearch();
      }}>
        <Stack direction={{ xs: "column", sm: "row" }} spacing={1} alignItems={{ sm: "center" }}>
          <Typography component="h1" variant="h5" fontWeight={700}>Search</Typography>
          <Stack direction="row" spacing={0.75} alignItems="center" sx={{ minWidth: 0, flex: 1 }}>
            <TextField fullWidth size="small" label="Search files" value={queryInput}
              onChange={event => setQueryInput(event.target.value)} />
            <Button type="submit" variant="contained" disabled={!queryInput.trim() || !scopeSelected}
              aria-label="Search" sx={{ minWidth: 40, px: 1.25 }}>
              <SearchOutlinedIcon fontSize="small" />
            </Button>
            <Tooltip title="Search options">
              <IconButton size="small" aria-label="Search options" onClick={() => setPanel("options")}><TuneOutlinedIcon fontSize="small" /></IconButton>
            </Tooltip>
            <Tooltip title="Explore by keyword">
              <IconButton size="small" aria-label="Explore by keyword" onClick={() => setPanel("keywords")}><AutoAwesomeOutlinedIcon fontSize="small" /></IconButton>
            </Tooltip>
            <Tooltip title="Recent searches">
              <IconButton size="small" aria-label="Recent searches" onClick={() => setPanel("history")}><HistoryOutlinedIcon fontSize="small" /></IconButton>
            </Tooltip>
          </Stack>
        </Stack>
      </Box>

      <Dialog open={panel !== null} onClose={() => setPanel(null)} fullWidth maxWidth="sm" aria-labelledby="search-panel-title">
        {panel === "options" && <DialogTitle id="search-panel-title">Search options</DialogTitle>}
        <DialogContent>
          {panel === "options" && <Stack spacing={1.5} sx={{ pt: 0.5 }}>
            <SearchModeSelect value={mode} onChange={setMode} />
            <TextField select size="small" label="Scope" value={scopeType} onChange={event => setScopeType(event.target.value)}>
              <MenuItem value="root">All files</MenuItem>
              <MenuItem value="collection">Collection</MenuItem>
            </TextField>
            {scopeType === "collection" && <TextField select size="small" label="Collection" value={collectionId}
              onChange={event => setCollectionId(event.target.value)}>
              <MenuItem value="">Select a collection</MenuItem>
              {(collectionsData?.collections ?? []).map(collection => <MenuItem key={collection.id} value={collection.id}>{collection.name}</MenuItem>)}
            </TextField>}
            <ToolContext id="search" />
          </Stack>}
          {panel === "keywords" && <ScopeSuggestions scope={keywordScope} compact titleId="search-panel-title"
            onSelect={word => runSearch(word, "hybrid", keywordScope)} />}
          {panel === "history" && <RecentActivity kind="search" entries={recentSearches.entries} onSelect={handleRecentSearch} titleId="search-panel-title"
            onDelete={recentSearches.remove} onClear={recentSearches.clear} />}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPanel(null)}>Close</Button>
          {panel === "options" && <Button variant="contained" disabled={!scopeSelected}
            onClick={() => queryInput.trim() ? handleSearch() : setPanel(null)}>{queryInput.trim() ? "Search" : "Done"}</Button>}
        </DialogActions>
      </Dialog>

      {hasSearched && !isLoading && !isError && data && (
        <Stack spacing={0.25}>
          <Typography component="h2" variant="body2" color="text.secondary">
            {results.length} {results.length === 1 ? "match" : "matches"} for “{query}”
          </Typography>
          {data.retrieval_mode_used !== data.mode && <Typography variant="caption" color="warning.main">
            Requested {data.mode}. Showing {data.retrieval_mode_used} results.
          </Typography>}
        </Stack>
      )}

      {isLoading ? (
        <Stack direction="row" spacing={2} alignItems="center">
          <CircularProgress size={24} />
          <Typography>Searching…</Typography>
        </Stack>
      ) : isError ? (
        <Alert severity="error">
          Search failed.
          {error instanceof Error ? ` ${error.message}` : ""}
        </Alert>
      ) : !hasSearched || results.length === 0 ? null : (
        <Stack spacing={1.25}>
          {results.map((result) => (
            <SearchResultCard
              key={`${result.fileId}:${result.charStart ?? "none"}:${result.charEnd ?? "none"}`}
              result={result}
              onOpen={handleOpen}
            />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
