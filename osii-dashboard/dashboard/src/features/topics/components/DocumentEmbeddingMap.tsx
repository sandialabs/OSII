import { useEffect, useMemo, useRef, useState } from "react";
import {
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from "@mui/material";
import { usePdfThumbnail } from "../../../hooks/usePdfThumbnail";
import { getObjectSourceUrl } from "../../../api/source";
import {
  topicHoverText,
  topicLabel,
  type LabelField,
  type TopicDisplay,
} from "./presentation";
import {
  circleMembers,
  detailPointIds,
  nearestPoint,
  mapPositions,
  type Position,
  type SelectionMode,
} from "./geometry";
import type { TopicViewProps } from "./viewTypes";
import type { TopicPoint } from "../types";

type Circle = Position & { radius: number };
type Drag = { start: Position; origin: Position; mode: SelectionMode };
export function EmbeddingMap({
  resetPreviewToken = 0,
  points,
  selectedId,
  relatedIds,
  selectedIds = new Set(),
  onSelect,
  onSelection,
  onPreview,
}: TopicViewProps) {
  const [display, setDisplay] = useState<TopicDisplay>(() => {
    try {
      const value = localStorage.getItem("osii-topic-display");
      return value === "filenames" || value === "thumbnails" ? value : "titles";
    } catch {
      return "titles";
    }
  });
  const [tool, setTool] = useState("pan");
  const [view, setView] = useState({ x: 0, y: 0, zoom: 1 });
  const [circle, setCircle] = useState<Circle | null>(null);
  const [preview, setPreview] = useState<Set<string>>(new Set());
  const [thumbnailSize, setThumbnailSize] = useState(64);
  const [radius, setRadius] = useState(80);
  const [showLabels, setShowLabels] = useState(points.length <= 100);
  const [labelField, setLabelField] = useState<LabelField>("auto");
  const drag = useRef<Drag | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const positions = useMemo(() => mapPositions(points, view), [points, view]);
  const details = useMemo(() => {
    const ids = detailPointIds(
      positions,
      display === "thumbnails" ? thumbnailSize * 1.4 : 65,
    );
    if (selectedId) ids.add(selectedId);
    if (hovered) ids.add(hovered);
    return points.filter((point) => ids.has(point.file_id));
  }, [points, positions, display, thumbnailSize, selectedId, hovered]);
  useEffect(() => {
    const node = canvas.current;
    if (!node) return;
    const paint = () => {
      const ratio = window.devicePixelRatio || 1;
      node.width = 800 * ratio;
      node.height = 480 * ratio;
      const context = node.getContext("2d");
      if (!context) return;
      context.scale(ratio, ratio);
      for (const point of points) {
        const p = positions.get(point.file_id)!;
        if (p.x < -10 || p.x > 810 || p.y < -10 || p.y > 490) continue;
        context.beginPath();
        context.arc(
          p.x,
          p.y,
          selectedIds.has(point.file_id) ? 4 : 2.8,
          0,
          Math.PI * 2,
        );
        context.fillStyle = selectedIds.has(point.file_id)
          ? "#d97228"
          : preview.has(point.file_id) || relatedIds.has(point.file_id)
            ? "#00899e"
            : "#629caf";
        context.fill();
      }
    };
    const frame = requestAnimationFrame(paint);
    return () => cancelAnimationFrame(frame);
  }, [points, positions, selectedIds, relatedIds, preview]);
  useEffect(() => {
    setCircle(null);
    setPreview(new Set());
    drag.current = null;
  }, [resetPreviewToken]);
  const resetPreview = () => {
    setCircle(null);
    setPreview(new Set());
    onPreview?.([]);
  };
  const zoom = (factor: number) => {
    resetPreview();
    setView((v) => ({
      ...v,
      zoom: Math.min(64, Math.max(0.5, v.zoom * factor)),
    }));
  };
  const pointer = (event: React.PointerEvent<SVGSVGElement>): Position => {
    const transform = event.currentTarget.getScreenCTM();
    const value = transform
      ? new DOMPoint(event.clientX, event.clientY).matrixTransform(
          transform.inverse(),
        )
      : new DOMPoint();
    return { x: value.x, y: value.y };
  };
  const draw = (center: Position, r: number) => {
    const ids = circleMembers(positions, center, r);
    setCircle({ ...center, radius: r });
    setPreview(new Set(ids));
    onPreview?.(ids);
    return ids;
  };
  return (
    <Stack spacing={1}>
      <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
        <Button size="small" onClick={() => zoom(1.4)} aria-label="Zoom in">
          +
        </Button>
        <Button
          size="small"
          onClick={() => zoom(1 / 1.4)}
          aria-label="Zoom out"
        >
          −
        </Button>
        <Button
          size="small"
          onClick={() => {
            resetPreview();
            setView({ x: 0, y: 0, zoom: 1 });
          }}
        >
          Reset view
        </Button>
        <ToggleButtonGroup
          size="small"
          exclusive
          value={tool}
          aria-label="Map interaction"
          onChange={(_, value) => {
            if (value) {
              setTool(value);
              resetPreview();
            }
          }}
        >
          <ToggleButton value="pan">Pan</ToggleButton>
          {onSelection && (
            <ToggleButton value="circle">Circle select</ToggleButton>
          )}
          <ToggleButton value="nearby">Preview nearby</ToggleButton>
        </ToggleButtonGroup>
      </Stack>
      <Typography variant="caption">
        {tool === "circle"
          ? "Drag a circle to select documents. Shift adds; Alt removes. Escape cancels a drawing."
          : tool === "nearby"
            ? "Click a document to preview its nearby map neighborhood, then review the documents below."
            : "Drag empty space to pan. Select a document to inspect it; Shift-click adds it to the collection selection."}
      </Typography>
      <ToggleButtonGroup
        value={display}
        exclusive
        size="small"
        aria-label="Map document display"
        onChange={(_, value: TopicDisplay | null) => {
          if (value) {
            setDisplay(value);
            try {
              localStorage.setItem("osii-topic-display", value);
            } catch {
              /* Optional preference. */
            }
          }
        }}
      >
        <ToggleButton value="filenames">Filenames</ToggleButton>
        <ToggleButton value="titles">Suggested titles</ToggleButton>
        <ToggleButton value="thumbnails">Thumbnails</ToggleButton>
      </ToggleButtonGroup>
      {display === "thumbnails" && (
        <Typography variant="caption">
          Every mapped document appears as a dot. Representative thumbnails load
          two at a time and are cached. Zoom and pan to reveal more previews, or
          circle a group to review its individual files below.
        </Typography>
      )}
      <Box
        sx={{
          position: "relative",
          background: "linear-gradient(145deg,#eff9fa,#f8fafc)",
          borderRadius: 2,
        }}
      >
        <canvas
          ref={canvas}
          aria-hidden="true"
          data-testid="topic-canvas"
          data-point-count={points.length}
          style={{
            position: "absolute",
            width: "100%",
            height: "100%",
            pointerEvents: "none",
          }}
        />
        <Box
          component="svg"
          viewBox="0 0 800 480"
          role="group"
          aria-label="Document embedding map"
          tabIndex={0}
          sx={{
            width: "100%",
            display: "block",
            position: "relative",
            borderRadius: 2,
            border: "1px solid",
            borderColor: "divider",
            touchAction: "none",
            cursor: tool === "circle" ? "crosshair" : "default",
          }}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              drag.current = null;
              resetPreview();
            }
          }}
          onPointerDown={(event) => {
            if (
              event.button !== 0 ||
              tool === "nearby" ||
              (tool === "pan" &&
                (event.target as Element).closest('[role="button"]'))
            )
              return;
            event.preventDefault();
            event.currentTarget.setPointerCapture(event.pointerId);
            const start = pointer(event);
            drag.current = {
              start,
              origin: { x: view.x, y: view.y },
              mode: event.altKey
                ? "remove"
                : event.shiftKey
                  ? "add"
                  : "replace",
            };
            if (tool === "circle") draw(start, 0);
            else resetPreview();
          }}
          onPointerMove={(event) => {
            const active = drag.current;
            if (!active) {
              setHovered(nearestPoint(positions, pointer(event)));
              return;
            }
            const end = pointer(event);
            if (tool === "circle")
              draw(
                active.start,
                Math.hypot(end.x - active.start.x, end.y - active.start.y),
              );
            else
              setView((v) => ({
                ...v,
                x: active.origin.x + end.x - active.start.x,
                y: active.origin.y + end.y - active.start.y,
              }));
          }}
          onPointerUp={(event) => {
            const active = drag.current;
            if (!active) return;
            drag.current = null;
            if (
              tool === "pan" &&
              Math.hypot(
                pointer(event).x - active.start.x,
                pointer(event).y - active.start.y,
              ) < 4
            ) {
              const id = nearestPoint(positions, pointer(event));
              if (id)
                event.shiftKey ? onSelection?.([id], "add") : onSelect(id);
            }
            if (tool === "circle") {
              const end = pointer(event);
              const ids = draw(
                active.start,
                Math.hypot(end.x - active.start.x, end.y - active.start.y),
              );
              onSelection?.(ids, active.mode);
            }
            if (event.currentTarget.hasPointerCapture(event.pointerId))
              event.currentTarget.releasePointerCapture(event.pointerId);
          }}
          onClick={(event) => {
            if (
              tool !== "nearby" ||
              (event.target as Element).closest('[role="button"]')
            )
              return;
            const transform = event.currentTarget.getScreenCTM();
            if (!transform) return;
            const value = new DOMPoint(
              event.clientX,
              event.clientY,
            ).matrixTransform(transform.inverse());
            const id = nearestPoint(positions, value);
            if (id) draw(positions.get(id)!, radius);
          }}
          onPointerLeave={() => setHovered(null)}
          onPointerCancel={() => {
            drag.current = null;
            resetPreview();
          }}
        >
          <text x="18" y="24" fill="#64748b" fontSize="12">
            Document content · 2D overview
          </text>
          {circle && (
            <circle
              data-testid="selection-circle"
              cx={circle.x}
              cy={circle.y}
              r={circle.radius}
              fill="#e47b3720"
              stroke="#c86520"
              strokeWidth="1.5"
              strokeDasharray="5 3"
              pointerEvents="none"
            />
          )}
          {details.map((point) => {
            const position = positions.get(point.file_id)!;
            return (
              <PointMark
                key={point.file_id}
                point={point}
                position={position}
                focused={point.file_id === selectedId}
                selected={selectedIds.has(point.file_id)}
                preview={preview.has(point.file_id)}
                related={relatedIds.has(point.file_id)}
                display={display}
                labelField={labelField}
                size={thumbnailSize}
                showLabel={showLabels}
                choose={(add) => {
                  if (add) {
                    onSelection?.([point.file_id], "add");
                    return;
                  }
                  if (tool === "nearby") draw(position, radius);
                  else if (tool === "pan") onSelect(point.file_id);
                }}
              />
            );
          })}
        </Box>
      </Box>
      <Typography variant="caption">
        {points.length.toLocaleString()} documents mapped · zoom for detail.
        Search and circle selection include every mapped document.
      </Typography>
      <Box component="details">
        <Typography component="summary" sx={{ cursor: "pointer" }}>
          Advanced map options
        </Typography>
        <Stack spacing={1.5} sx={{ pt: 1 }}>
          <Stack direction={{ xs: "column", sm: "row" }} spacing={2}>
            <TextField
              size="small"
              type="number"
              label="Thumbnail size"
              value={thumbnailSize}
              inputProps={{ min: 36, max: 110 }}
              onChange={(e) =>
                setThumbnailSize(
                  Math.max(36, Math.min(110, Number(e.target.value) || 64)),
                )
              }
            />
            <TextField
              size="small"
              type="number"
              label="Nearby preview radius"
              value={radius}
              inputProps={{ min: 20, max: 240 }}
              onChange={(e) =>
                setRadius(
                  Math.max(20, Math.min(240, Number(e.target.value) || 80)),
                )
              }
            />
            <TextField
              size="small"
              select
              label="Metadata label field"
              value={labelField}
              onChange={(e) => setLabelField(e.target.value as LabelField)}
            >
              {(
                [
                  "auto",
                  "descriptive_title",
                  "title",
                  "author",
                  "date",
                  "agency",
                  "document_type",
                ] as const
              ).map((value) => (
                <MenuItem key={value} value={value}>
                  {value === "auto"
                    ? "Best available title"
                    : value.replace(/_/g, " ")}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <FormControlLabel
            control={
              <Checkbox
                checked={showLabels}
                onChange={(e) => setShowLabels(e.target.checked)}
              />
            }
            label="Show map labels"
          />
          <Typography variant="caption">
            Orange: collection selection. Teal: related or previewed documents.
            A nearby group is a visual aid, not an inferred topic. Positions and
            cached approximate PCA geometry do not change when you change labels
            or thumbnails. Selection covers only the mapped documents.
          </Typography>
        </Stack>
      </Box>
    </Stack>
  );
}

function PointMark({
  point,
  position: { x, y },
  focused,
  selected,
  preview,
  related,
  display,
  labelField,
  size,
  showLabel,
  choose,
}: {
  point: TopicPoint;
  position: Position;
  focused: boolean;
  selected: boolean;
  preview: boolean;
  related: boolean;
  display: TopicDisplay;
  labelField: LabelField;
  size: number;
  showLabel: boolean;
  choose: (add: boolean) => void;
}) {
  const ref = useRef<SVGGElement>(null);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    const node = ref.current;
    if (!node || display !== "thumbnails") return;
    const observer = new IntersectionObserver(
      (entries) => setVisible(entries.some((entry) => entry.isIntersecting)),
      { rootMargin: "100px" },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, [display]);
  const isPdf =
    point.media_type === "application/pdf" || /\.pdf$/i.test(point.filename);
  const isImage =
    point.media_type?.startsWith("image/") ||
    /\.(png|jpe?g|webp|gif)$/i.test(point.filename);
  const enabled = display === "thumbnails" && visible;
  const source = getObjectSourceUrl(point.file_id);
  const { thumbnailUrl, isLoading, error } = usePdfThumbnail(
    enabled && isPdf ? source : null,
    enabled && isPdf,
  );
  const image = enabled ? thumbnailUrl || (isImage ? source : null) : null;
  const color = selected
    ? "#d97228"
    : preview || related
      ? "#00899e"
      : "#629caf";
  const label = topicLabel(point, display, labelField);
  const left = x > 620;
  const thumbnail = display === "thumbnails";
  return (
    <Tooltip
      title={
        <span style={{ whiteSpace: "pre-line" }}>
          {topicHoverText(point)}
          {error
            ? "\nPreview unavailable; open the document to inspect the source."
            : ""}
        </span>
      }
      arrow
      enterDelay={250}
    >
      <g
        ref={ref}
        role="button"
        tabIndex={0}
        aria-label={`Explore ${label}`}
        aria-pressed={focused}
        data-file-id={point.file_id}
        data-selected={selected ? "true" : "false"}
        onClick={(e) => choose(e.shiftKey)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            e.stopPropagation();
            choose(e.shiftKey);
          }
        }}
        style={{ cursor: "pointer" }}
      >
        {thumbnail ? (
          <>
            <rect
              x={x - size / 2}
              y={y - size * 0.65}
              width={size}
              height={size * 1.3}
              rx="3"
              fill="white"
              stroke={focused ? "#7c3510" : color}
              strokeWidth={selected || focused ? 3 : 1.5}
            />
            {image ? (
              <image
                href={image}
                x={x - size / 2 + 2}
                y={y - size * 0.65 + 2}
                width={size - 4}
                height={size * 1.3 - 4}
                preserveAspectRatio="xMidYMid meet"
              />
            ) : (
              <text x={x} y={y} textAnchor="middle" fontSize="9" fill="#64748b">
                {isLoading
                  ? "Loading…"
                  : error
                    ? "No preview"
                    : isPdf
                      ? "PDF"
                      : "File"}
              </text>
            )}
          </>
        ) : (
          <circle
            cx={x}
            cy={y}
            r={focused ? 10 : selected || preview || related ? 7 : 5.5}
            fill={color}
            stroke={focused ? "#7c3510" : "white"}
            strokeWidth={focused ? 2 : 1.5}
          />
        )}
        {(showLabel || focused) && (
          <text
            x={x + (left ? -1 : 1) * (thumbnail ? size / 2 + 5 : 12)}
            textAnchor={left ? "end" : "start"}
            y={y + 4}
            fontSize={focused ? 13 : 10}
            fill="#263442"
            paintOrder="stroke"
            stroke="white"
            strokeWidth="3"
          >
            {label.slice(0, focused ? 65 : 28)}
            {label.length > (focused ? 65 : 28) ? "…" : ""}
          </text>
        )}
      </g>
    </Tooltip>
  );
}
