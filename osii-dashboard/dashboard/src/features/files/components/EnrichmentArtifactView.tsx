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
  Typography,
} from "@mui/material";
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

function TableView({ artifact }: { artifact: StandardTableArtifact }) {
  return (
    <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 520 }}>
      <Table stickyHeader size="small" aria-label={artifact.title}>
        <TableHead>
          <TableRow>
            {artifact.columns.map((column) => (
              <TableCell key={column.key}>
                {column.label}
                {column.unit ? ` (${column.unit})` : ""}
              </TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {artifact.rows.map((row, rowIndex) => (
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
  );
}

function KnowledgeGraphView({ artifact }: { artifact: StandardKnowledgeGraphArtifact }) {
  const labels = new Map(artifact.nodes.map((node) => [node.id, node.label]));
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={1}>
        <Chip label={`${artifact.nodes.length} nodes`} />
        <Chip label={`${artifact.edges.length} relationships`} />
      </Stack>
      <Box sx={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))", gap: 1 }}>
        {artifact.nodes.map((node) => (
          <Paper key={node.id} variant="outlined" sx={{ p: 1.25 }}>
            <Typography fontWeight={600}>{node.label}</Typography>
            <Typography variant="caption" color="text.secondary">{node.entity_type}</Typography>
          </Paper>
        ))}
      </Box>
      <TableContainer component={Paper} variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow><TableCell>Source</TableCell><TableCell>Relationship</TableCell><TableCell>Target</TableCell></TableRow>
          </TableHead>
          <TableBody>
            {artifact.edges.map((edge) => (
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
    <Box className="markdown-body" sx={{ "& table": { borderCollapse: "collapse" }, "& td, & th": { border: "1px solid", borderColor: "divider", p: 1 } }}>
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
        <Box component="pre" sx={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", mt: 1 }}>
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

