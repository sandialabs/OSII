import type { TopicPoint } from "../types";
export type Position = { x: number; y: number };
export type SelectionMode = "replace" | "add" | "remove";
export function mapPositions(
  points: readonly TopicPoint[],
  view: { x: number; y: number; zoom: number },
): Map<string, Position> {
  let minX = 0,
    maxX = 0,
    minY = 0,
    maxY = 0;
  for (const point of points) {
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  }
  const scale = Math.min(644 / (maxX - minX || 1), 324 / (maxY - minY || 1));
  return new Map(
    points.map((p) => [
      p.file_id,
      {
        x: 400 + (p.x - (minX + maxX) / 2) * scale * view.zoom + view.x,
        y: 240 - (p.y - (minY + maxY) / 2) * scale * view.zoom + view.y,
      },
    ]),
  );
}
export function circleMembers(
  positions: ReadonlyMap<string, Position>,
  center: Position,
  radius: number,
): string[] {
  if (!Number.isFinite(radius) || radius < 0) return [];
  return [...positions]
    .filter(
      ([, p]) => (p.x - center.x) ** 2 + (p.y - center.y) ** 2 <= radius ** 2,
    )
    .map(([id]) => id);
}
export function updateSelection(
  current: ReadonlySet<string>,
  ids: readonly string[],
  mode: SelectionMode,
  allowed: ReadonlySet<string>,
): Set<string> {
  const result = new Set(
    mode === "replace" ? [] : [...current].filter((id) => allowed.has(id)),
  );
  for (const id of ids)
    if (allowed.has(id)) {
      if (mode === "remove") result.delete(id);
      else result.add(id);
    }
  return result;
}

/** One representative per visible screen cell; all points stay on the canvas.
 * Panning/zooming changes representatives. Never select by this detail subset.
 */
export function detailPointIds(
  positions: ReadonlyMap<string, Position>,
  size: number,
): Set<string> {
  const cells = new Map<string, { id: string; distance: number }>();
  for (const [id, p] of positions) {
    if (p.x < 0 || p.x > 800 || p.y < 0 || p.y > 480) continue;
    const col = Math.floor(p.x / size),
      row = Math.floor(p.y / size);
    const key = `${col}:${row}`;
    const distance =
      (p.x - (col + 0.5) * size) ** 2 + (p.y - (row + 0.5) * size) ** 2;
    if (!cells.has(key) || cells.get(key)!.distance > distance)
      cells.set(key, { id, distance });
  }
  return new Set([...cells.values()].map((cell) => cell.id));
}

export function nearestPoint(
  positions: ReadonlyMap<string, Position>,
  at: Position,
  radius = 12,
): string | null {
  let closest: string | null = null,
    distance = radius ** 2;
  for (const [id, p] of positions) {
    const candidate = (p.x - at.x) ** 2 + (p.y - at.y) ** 2;
    if (candidate < distance) {
      closest = id;
      distance = candidate;
    }
  }
  return closest;
}
