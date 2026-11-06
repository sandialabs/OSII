import { useRef, useState } from "react";
import { Box, Button, Stack, Typography } from "@mui/material";
import type { TopicPoint } from "../types";

export function EmbeddingMap({ points, selectedId, relatedIds, onSelect }: {
  points: TopicPoint[]; selectedId: string; relatedIds: Set<string>; onSelect: (id: string) => void;
}) {
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const drag = useRef<{ x: number; y: number; originX: number; originY: number } | null>(null);
  const width = 800, height = 480, padding = 38;
  // Preserve aspect ratio: independent axis scaling would distort geometry further.
  const minX = Math.min(0, ...points.map(p => p.x)), maxX = Math.max(0, ...points.map(p => p.x));
  const minY = Math.min(0, ...points.map(p => p.y)), maxY = Math.max(0, ...points.map(p => p.y));
  const scale = Math.min((width - padding * 2) / (maxX - minX || 1), (height - padding * 2) / (maxY - minY || 1));
  const position = (point: TopicPoint) => ({
    x: width / 2 + ((point.x - (minX + maxX) / 2) * scale) * view.zoom + view.x,
    y: height / 2 - ((point.y - (minY + maxY) / 2) * scale) * view.zoom + view.y,
  });
  const zoom = (factor: number) => setView(v => ({ ...v, zoom: Math.min(8, Math.max(0.5, v.zoom * factor)) }));
  return <Stack spacing={1}>
    <Stack direction="row" spacing={1} alignItems="center">
      <Button size="small" onClick={() => zoom(1.4)} aria-label="Zoom in">+</Button>
      <Button size="small" onClick={() => zoom(1 / 1.4)} aria-label="Zoom out">−</Button>
      <Button size="small" onClick={() => setView({ x: 0, y: 0, zoom: 1 })}>Reset view</Button>
      <Typography variant="caption" color="text.secondary">Drag to pan · Select a document</Typography>
    </Stack>
    <Box component="svg" viewBox={`0 0 ${width} ${height}`} role="group" aria-label="Document embedding map"
      sx={{ width: "100%", background: "linear-gradient(145deg, #eff9fa, #f8fafc)", borderRadius: 2, border: "1px solid", borderColor: "divider", touchAction: "none" }}
      onPointerDown={event => {
        if ((event.target as Element).closest('[role="button"]')) return;
        event.currentTarget.setPointerCapture(event.pointerId);
        drag.current = { x: event.clientX, y: event.clientY, originX: view.x, originY: view.y };
      }}
      onPointerMove={event => {
        if (!drag.current) return;
        const ratio = width / event.currentTarget.getBoundingClientRect().width;
        setView(v => ({ ...v, x: drag.current!.originX + (event.clientX - drag.current!.x) * ratio,
          y: drag.current!.originY + (event.clientY - drag.current!.y) * ratio }));
      }}
      onPointerUp={() => { drag.current = null; }} onPointerCancel={() => { drag.current = null; }}>
      <text x="18" y="24" fill="#64748b" fontSize="12">Document content · 2D overview</text>
      {points.map(point => {
        const selected = point.file_id === selectedId;
        const related = relatedIds.has(point.file_id);
        const { x, y } = position(point);
        return <g key={point.file_id} role="button" tabIndex={0} aria-label={`Explore ${point.filename}`} aria-pressed={selected}
          onClick={() => onSelect(point.file_id)} onKeyDown={event => {
            if (event.key === "Enter" || event.key === " ") { event.preventDefault(); onSelect(point.file_id); }
          }} style={{ cursor: "pointer", outlineOffset: 3 }}>
          <title>{point.source_relpath}</title>
          <circle cx={x} cy={y} r={selected ? 10 : related ? 7 : 5.5} fill={selected ? "#e47b37" : related ? "#00899e" : "#629caf"}
            stroke={selected ? "#7c3510" : "white"} strokeWidth={selected ? 2 : 1.5} opacity={selected || related ? 1 : 0.8} />
          {selected && <text x={x + 14} y={y + 4} fill="#263442" fontSize="13" paintOrder="stroke" stroke="white" strokeWidth="3">{point.filename.slice(0, 45)}</text>}
        </g>;
      })}
    </Box>
    <Typography variant="caption" color="text.secondary">Orange: selected · Teal: related · Blue: other documents. Nearby points are an approximation; similarity uses full embeddings.</Typography>
  </Stack>;
}
