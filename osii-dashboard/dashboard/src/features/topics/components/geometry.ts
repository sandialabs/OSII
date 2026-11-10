import type { TopicPoint } from "../types";
export type Position = { x: number; y: number };
export type SelectionMode = "replace" | "add" | "remove";
export function mapPositions(
  points: readonly TopicPoint[],
  view: { x: number; y: number; zoom: number },
): Map<string, Position> {
  const minX = Math.min(0, ...points.map((p) => p.x)),
    maxX = Math.max(0, ...points.map((p) => p.x));
  const minY = Math.min(0, ...points.map((p) => p.y)),
    maxY = Math.max(0, ...points.map((p) => p.y));
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
