import { useEffect, useRef, useState } from "react";
import { Box, Button, Stack, ToggleButton, ToggleButtonGroup, Tooltip, Typography } from "@mui/material";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";
import { topicHoverText, topicLabel, type TopicDisplay } from "./presentation";
import type { TopicPoint } from "../types";

export function EmbeddingMap({ points, selectedId, relatedIds, onSelect }: {
  points: TopicPoint[]; selectedId: string; relatedIds: Set<string>; onSelect: (id: string) => void;
}) {
  const [display, setDisplay] = useState<TopicDisplay>(() => {
    try { const saved = localStorage.getItem("osii-topic-display"); return saved === "filenames" || saved === "thumbnails" ? saved : "titles"; } catch { return "titles"; }
  });
  const [previewLimit, setPreviewLimit] = useState(40);
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
    <ToggleButtonGroup value={display} exclusive size="small" aria-label="Map document display" onChange={(_, value: TopicDisplay | null) => {
      if (!value) return; setDisplay(value); try { localStorage.setItem("osii-topic-display", value); } catch { /* Preference is optional. */ }
    }}><ToggleButton value="filenames">Filenames</ToggleButton><ToggleButton value="titles">Suggested titles</ToggleButton><ToggleButton value="thumbnails">Thumbnails</ToggleButton></ToggleButtonGroup>
    {display === "thumbnails" && <Stack direction="row" spacing={1} alignItems="center"><Typography variant="caption">Previews load in batches and are cached in this browser. Files without previews use a file marker.</Typography>{previewLimit < points.length && <Button size="small" onClick={() => setPreviewLimit(value => value + 40)}>Load 40 more previews</Button>}</Stack>}
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
      {points.map((point, index) => {
        const selected = point.file_id === selectedId;
        const related = relatedIds.has(point.file_id);
        const { x, y } = position(point);
        return <PointMark key={point.file_id} point={point} x={x} y={y} selected={selected} related={related} display={display}
          preview={display === "thumbnails" && index < previewLimit} onSelect={onSelect} />;
      })}
    </Box>
    <Typography variant="caption" color="text.secondary">Orange: selected · Teal: related · Blue: other documents. Nearby points are an approximation; similarity uses full embeddings. Map geometry is cached and rebuilds when embeddings or scope change.</Typography>
  </Stack>;
}

function PointMark({ point, x, y, selected, related, display, preview, onSelect }: {
  point: TopicPoint; x:number; y:number; selected:boolean; related:boolean; display:TopicDisplay; preview:boolean; onSelect:(id:string)=>void;
}) {
  const ref = useRef<SVGGElement>(null);
  const [visible,setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current; if (!node || !preview) return;
    const observer = new IntersectionObserver(entries => {setVisible(entries.some(entry => entry.isIntersecting));});
    observer.observe(node); return () => observer.disconnect();
  },[preview]);
  const isPdf = point.media_type === "application/pdf" || /\.pdf$/i.test(point.filename);
  const isImage = point.media_type?.startsWith("image/") || /\.(png|jpe?g|webp|gif)$/i.test(point.filename);
  const source = getObjectSourceUrl(point.file_id);
  const { thumbnailUrl } = usePdfThumbnail(preview && visible && isPdf ? source : null, preview && visible && isPdf);
  const image = preview && visible ? thumbnailUrl || (isImage ? source : null) : null;
  const label = topicLabel(point,display);
  const labelLeft = x > 630;
  const color = selected ? "#e47b37" : related ? "#00899e" : "#629caf";
  return <Tooltip title={<span style={{whiteSpace:"pre-line"}}>{topicHoverText(point)}</span>} arrow enterDelay={250}>
    <g ref={ref} role="button" tabIndex={0} aria-label={`Explore ${label}`} aria-pressed={selected} onClick={() => onSelect(point.file_id)}
      onKeyDown={event => {if(event.key === "Enter" || event.key === " "){event.preventDefault();onSelect(point.file_id);}}} style={{cursor:"pointer"}}>
      {image ? <><rect x={x-19} y={y-25} width="38" height="50" rx="2" fill="white" stroke={color} strokeWidth={selected ? 3 : 1.5}/><image href={image} x={x-17} y={y-23} width="34" height="46" preserveAspectRatio="xMidYMid meet"/></>
        : <circle cx={x} cy={y} r={selected ? 10 : related ? 7 : 5.5} fill={color} stroke={selected ? "#7c3510" : "white"} strokeWidth={selected ? 2 : 1.5} opacity={selected || related ? 1 : 0.8}/>}
      <text x={x + (labelLeft ? -1 : 1) * (image ? 23 : 12)} textAnchor={labelLeft ? "end" : "start"} y={y + 4} fill="#263442" fontSize={selected ? 13 : 10} paintOrder="stroke" stroke="white" strokeWidth="3">{label.slice(0,selected ? 65 : 28)}{label.length > (selected ? 65 : 28) ? "…" : ""}</text>
    </g>
  </Tooltip>;
}
