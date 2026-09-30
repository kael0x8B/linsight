import type { AiVideoRuleApi } from '#/api/ai-video/rule';

type Point = AiVideoRuleApi.Point;

export const roundCoordinate = (value: number) =>
  Number(Math.max(0, Math.min(1, value)).toFixed(4));

export function translateRegion(points: Point[], offset: Point): Point[] {
  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);
  const dx = Math.max(
    -Math.min(...xs),
    Math.min(1 - Math.max(...xs), offset.x),
  );
  const dy = Math.max(
    -Math.min(...ys),
    Math.min(1 - Math.max(...ys), offset.y),
  );
  return points.map((point) => ({
    x: roundCoordinate(point.x + dx),
    y: roundCoordinate(point.y + dy),
  }));
}

function cross(a: Point, b: Point, c: Point) {
  return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
}

function onSegment(a: Point, b: Point, point: Point) {
  return (
    Math.abs(cross(a, b, point)) < 1e-10 &&
    point.x >= Math.min(a.x, b.x) &&
    point.x <= Math.max(a.x, b.x) &&
    point.y >= Math.min(a.y, b.y) &&
    point.y <= Math.max(a.y, b.y)
  );
}

export function regionGeometryError(points: Point[]) {
  if (points.length < 3) return 'tooFewPoints';
  if (points.length > 20) return 'tooManyPoints';
  if (
    points.some(({ x, y }) =>
      [x, y].some((v) => !Number.isFinite(v) || v < 0 || v > 1),
    )
  )
    return 'outOfBounds';
  if (new Set(points.map(({ x, y }) => `${x},${y}`)).size !== points.length)
    return 'duplicatePoints';

  let area = 0;
  for (const [i, a] of points.entries()) {
    const b = points[(i + 1) % points.length];
    if (!b) continue;
    area += a.x * b.y - b.x * a.y;
    for (let j = i + 2; j < points.length; j++) {
      if ((j + 1) % points.length === i) continue;
      const c = points[j];
      const d = points[(j + 1) % points.length];
      if (!c || !d) continue;
      if (
        (cross(a, b, c) * cross(a, b, d) < 0 &&
          cross(c, d, a) * cross(c, d, b) < 0) ||
        onSegment(a, b, c) ||
        onSegment(a, b, d) ||
        onSegment(c, d, a) ||
        onSegment(c, d, b)
      )
        return 'selfIntersection';
    }
  }
  return Math.abs(area) / 2 < 0.0001 ? 'tooSmall' : undefined;
}
