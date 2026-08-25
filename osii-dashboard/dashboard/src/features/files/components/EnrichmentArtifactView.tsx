import {
  Alert,
  Box,
  Chip,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from "@mui/material";
import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";

import type {
  StandardEnrichmentArtifact,
  StandardEntityListArtifact,
  StandardKnowledgeGraphArtifact,
  StandardTableArtifact,
  StandardWikiMarkdownArtifact,
} from "../../../api/types";

function displayValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function isStandardArtifact(value: unknown): value is StandardEnrichmentArtifact {
  if (!value || typeof value !== "object") return false;
  return ["table", "knowledge_graph", "entity_list", "wiki_markdown"].includes(
    String((value as { artifact_type?: unknown }).artifact_type),
  );
}

type SortDirection = "asc" | "desc";

function compareValues(left: unknown, right: unknown): number {
  if (typeof left === "number" && typeof right === "number") return left - right;
  return displayValue(left).localeCompare(displayValue(right), undefined, {
    numeric: true,
    sensitivity: "base",
  });
}

function TableView({ artifact }: { artifact: StandardTableArtifact }) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const rows = useMemo(() => {
    if (!sortKey) return artifact.rows;
    return [...artifact.rows].sort((left, right) => {
      const result = compareValues(left[sortKey], right[sortKey]);
      return sortDirection === "asc" ? result : -result;
    });
  }, [artifact.rows, sortDirection, sortKey]);

  const chooseSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
      <Table stickyHeader size="small" aria-label={artifact.title}>
        <TableHead>
          <TableRow>
            {artifact.columns.map((column) => (
              <TableCell key={column.key} sortDirection={sortKey === column.key ? sortDirection : false}>
                <TableSortLabel
                  active={sortKey === column.key}
                  direction={sortKey === column.key ? sortDirection : "asc"}
                  onClick={() => chooseSort(column.key)}
                >
                  {column.label}
                  {column.unit ? ` (${column.unit})` : ""}
                </TableSortLabel>
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, rowIndex) => (
            <TableRow key={rowIndex} hover>
              {artifact.columns.map((column) => (
                <TableCell key={column.key}>{displayValue(row[column.key])}</TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

function EntityListView({ artifact }: { artifact: StandardEntityListArtifact }) {
  return (
    <Box sx={{ maxHeight: 360, overflowY: "auto", pr: 0.5 }}>
      <Stack spacing={1}>
        {artifact.entities.map((entity) => (
          <Paper key={entity.id} variant="outlined" sx={{ p: 1.5 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography fontWeight={600}>{entity.name}</Typography>
              <Chip size="small" label={entity.entity_type} />
              {(entity.aliases ?? []).map((alias) => (
                <Chip key={alias} size="small" variant="outlined" label={alias} />
              ))}
            </Stack>
            {entity.attributes && Object.keys(entity.attributes).length > 0 ? (
              <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
                {Object.entries(entity.attributes)
                  .map(([key, value]) => `${key}: ${displayValue(value)}`)
                  .join(" · ")}
              </Typography>
            ) : null}
          </Paper>
        ))}
      </Stack>
    </Box>
  );
}

function KnowledgeGraphView({ artifact }: { artifact: StandardKnowledgeGraphArtifact }) {
  const labels = new Map(artifact.nodes.map((node) => [node.id, node.label]));
  const [sortKey, setSortKey] = useState<"source" | "relation" | "target">("source");
  const [sortDirection, setSortDirection] = useState<SortDirection>("asc");
  const edges = useMemo(() => [...artifact.edges].sort((left, right) => {
    const leftValue = sortKey === "source"
      ? labels.get(left.source) ?? left.source
      : sortKey === "target"
        ? labels.get(left.target) ?? left.target
        : left.relation;
    const rightValue = sortKey === "source"
      ? labels.get(right.source) ?? right.source
      : sortKey === "target"
        ? labels.get(right.target) ?? right.target
        : right.relation;
    const result = compareValues(leftValue, rightValue);
    return sortDirection === "asc" ? result : -result;
  }), [artifact.edges, labels, sortDirection, sortKey]);
  const chooseSort = (key: "source" | "relation" | "target") => {
    if (sortKey === key) {
      setSortDirection((current) => current === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1}>
        <Chip label={`${artifact.nodes.length} nodes`} />
        <Chip label={`${artifact.edges.length} relationships`} />
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 1, maxHeight: 300, overflowY: "auto", pr: 0.5 }}>
        {artifact.nodes.map((node) => (
          <Paper key={node.id} variant="outlined" sx={{ p: 1.25 }}>
            <Typography fontWeight={600}>{node.label}</Typography>
            <Typography variant="caption" color="text.secondary">{node.entity_type}</Typography>
          </Paper>
        ))}
      </Box>
      <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 360 }}>
        <Table stickyHeader size="small">
          <TableHead>
            <TableRow>
              {(["source", "relation", "target"] as const).map((key) => (
                <TableCell key={key} sortDirection={sortKey === key ? sortDirection : false}>
                  <TableSortLabel active={sortKey === key} direction={sortKey === key ? sortDirection : "asc"} onClick={() => chooseSort(key)}>
                    {key === "relation" ? "Relationship" : `${key[0].toUpperCase()}${key.slice(1)}`}
                  </TableSortLabel>
                </TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {edges.map((edge) => (
              <TableRow key={edge.id}>
                <TableCell>{labels.get(edge.source) ?? edge.source}</TableCell>
                <TableCell>{edge.relation}</TableCell>
                <TableCell>{labels.get(edge.target) ?? edge.target}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableContainer>
    </Stack>
  );
}

function WikiView({ artifact }: { artifact: StandardWikiMarkdownArtifact }) {
  return (
    <Box className="markdown-body" sx={{ maxHeight: 640, overflowY: "auto", pr: 1, "& table": { borderCollapse: "collapse" }, "& td, & th": { border: "1px solid", borderColor: "divider", p: 1 } }}>
      <ReactMarkdown remarkPlugins={[remarkGfm, remarkMath]} rehypePlugins={[rehypeKatex]}>
        {artifact.markdown}
      </ReactMarkdown>
    </Box>
  );
}

export function EnrichmentArtifactView({ data }: { data: unknown }) {
  if (!isStandardArtifact(data)) {
    return (
      <Alert severity="info">
        This artifact uses a custom JSON format. Its raw representation is shown below.
        <Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", overflowY: "auto", maxHeight: 360, mt: 1 }}>
          {JSON.stringify(data, null, 2)}
        </Box>
      </Alert>
    );
  }

  return (
    <Stack spacing={1.5}>
      <Typography variant="h6">{data.title}</Typography>
      {"description" in data && data.description ? (
        <Typography color="text.secondary">{data.description}</Typography>
      ) : null}
      {data.artifact_type === "table" ? <TableView artifact={data} /> : null}
      {data.artifact_type === "entity_list" ? <EntityListView artifact={data} /> : null}
      {data.artifact_type === "knowledge_graph" ? <KnowledgeGraphView artifact={data} /> : null}
      {data.artifact_type === "wiki_markdown" ? <WikiView artifact={data} /> : null}
    </Stack>
  );
}
