// src/features/search/pages/SearchPage.tsx
import { useMemo, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import SearchOutlinedIcon from "@mui/icons-material/SearchOutlined";
import TuneOutlinedIcon from "@mui/icons-material/TuneOutlined";
import { useNavigate, useSearchParams } from "react-router-dom";

import type { ScopeDescribeRequest, SearchMode } from "../../../api/types";
import { useCollections } from "../../../hooks/useCollections";
import { useSearch } from "../../../hooks/useSearch";
import { buildFileRoute } from "../../../utils/routes";
import { toSearchResultModel, type SearchResultModel } from "../../../domain/search";
import { SearchResultCard } from "../components/SearchResultCard";

function coerceMode(value: string | null): SearchMode {
  if (value === "semantic" || value === "lexical" || value === "hybrid") {
    return value;
  }
  return "semantic";
}

export function SearchPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const { data: collectionsData } = useCollections();

  const initialQuery = searchParams.get("q") ?? "";
  const initialMode = coerceMode(searchParams.get("mode"));
  const initialScopeType = searchParams.get("scope_type") ?? "root";

  const [queryInput, setQueryInput] = useState(initialQuery);
  const [mode, setMode] = useState<SearchMode>(initialMode);
  const [scopeType, setScopeType] = useState<string>(initialScopeType);
  const [collectionId, setCollectionId] = useState(searchParams.get("collection_id") ?? "");
  const [showOptions, setShowOptions] = useState(false);

  const effectiveScope: ScopeDescribeRequest = useMemo(() => {
    if (scopeType === "collection" && collectionId.trim()) {
      return {
        scope_type: "collection",
        collection_id: collectionId.trim(),
      };
    }

    return { scope_type: "root" };
  }, [scopeType, collectionId]);

  const query = searchParams.get("q") ?? "";
  const hasSearched = query.trim().length > 0;

  const { data, isLoading, isError, error } = useSearch({
    query,
    mode,
    scope: effectiveScope,
    topK: 12,
    enabled: hasSearched,
  });

  const results = useMemo(
    () => (data?.results ?? []).map(toSearchResultModel),
    [data?.results],
  );

  const handleSearch = () => {
    const next = new URLSearchParams();

    if (queryInput.trim()) {
      next.set("q", queryInput.trim());
    }

    next.set("mode", mode);
    next.set("scope_type", scopeType);

    if (scopeType === "collection" && collectionId.trim()) {
      next.set("collection_id", collectionId.trim());
    }

    navigate(`/search?${next.toString()}`);
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
    <Stack spacing={3}>
      <Card
        sx={{
          background:
            "linear-gradient(135deg, rgba(20,184,166,0.10), rgba(6,182,212,0.05) 55%, rgba(255,255,255,1) 100%)",
          borderColor: "rgba(20,184,166,0.18)",
        }}
      >
        <CardContent sx={{ py: 2.5 }}>
          <Stack spacing={2.25}>
            <Stack spacing={0.5}>
              <Typography variant="h5" fontWeight={700}>
                Search
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Search across your indexed files with grounded results.
              </Typography>
            </Stack>

            <Stack
              direction={{ xs: "column", md: "row" }}
              spacing={1.25}
              alignItems={{ xs: "stretch", md: "center" }}
            >
              <TextField
                fullWidth
                size="medium"
                label="Search files"
                placeholder="Ask a question or enter keywords"
                value={queryInput}
                onChange={(event) => setQueryInput(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && queryInput.trim()) {
                    handleSearch();
                  }
                }}
                sx={{
                  "& .MuiOutlinedInput-root": {
                    backgroundColor: "rgba(255,255,255,0.82)",
                  },
                }}
              />

              <Button
                variant="contained"
                size="medium"
                startIcon={<SearchOutlinedIcon />}
                onClick={handleSearch}
                disabled={!queryInput.trim()}
                sx={{
                  minWidth: { xs: "100%", md: 140 },
                  alignSelf: { xs: "stretch", md: "auto" },
                }}
              >
                Search
              </Button>
            </Stack>

            <Stack spacing={1}>
              <Button
                variant="text"
                size="small"
                startIcon={<TuneOutlinedIcon />}
                onClick={() => setShowOptions((prev) => !prev)}
                sx={{
                  alignSelf: "flex-start",
                  px: 0,
                  color: "text.secondary",
                }}
              >
                {showOptions ? "Hide search options" : "Show search options"}
              </Button>

              {showOptions ? (
                <Stack
                  direction={{ xs: "column", lg: "row" }}
                  spacing={1.25}
                  alignItems={{ xs: "stretch", lg: "center" }}
                >
                  <TextField
                    select
                    size="small"
                    label="Mode"
                    value={mode}
                    onChange={(event) => setMode(event.target.value as SearchMode)}
                    sx={{ minWidth: 160 }}
                  >
                    <MenuItem value="semantic">Semantic</MenuItem>
                    <MenuItem value="lexical">Lexical</MenuItem>
                    <MenuItem value="hybrid">Hybrid</MenuItem>
                  </TextField>

                  <TextField
                    select
                    size="small"
                    label="Scope"
                    value={scopeType}
                    onChange={(event) => setScopeType(event.target.value)}
                    sx={{ minWidth: 160 }}
                  >
                    <MenuItem value="root">All files</MenuItem>
                    <MenuItem value="collection">Collection</MenuItem>
                  </TextField>

                  {scopeType === "collection" ? (
                    <TextField
                      select
                      size="small"
                      label="Collection"
                      value={collectionId}
                      onChange={(event) => setCollectionId(event.target.value)}
                      sx={{ minWidth: 220 }}
                    >
                      <MenuItem value="">Select a collection</MenuItem>
                      {(collectionsData?.collections ?? []).map((collection) => (
                        <MenuItem key={collection.id} value={collection.id}>
                          {collection.name}
                        </MenuItem>
                      ))}
                    </TextField>
                  ) : null}
                </Stack>
              ) : null}
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={0.5}>
        <Typography variant="subtitle1" fontWeight={600}>
          Matched Chunks
        </Typography>

        {hasSearched && !isLoading && !isError && data ? (
          <Stack spacing={0.25}>
            <Typography variant="body2" color="text.secondary">
              {results.length} result{results.length === 1 ? "" : "s"} for “{query}”
            </Typography>

            {data.retrieval_mode_used !== data.mode ? (
              <Typography variant="caption" color="warning.main">
                Requested {data.mode}, using {data.retrieval_mode_used} because semantic retrieval is currently unavailable.
              </Typography>
            ) : null}
          </Stack>
        ) : null}
      </Stack>

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
      ) : !hasSearched ? (
        <Typography color="text.secondary">
          Enter a query to search the corpus.
        </Typography>
      ) : results.length === 0 ? (
        <Typography color="text.secondary">No results found.</Typography>
      ) : (
        <Stack spacing={2}>
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
