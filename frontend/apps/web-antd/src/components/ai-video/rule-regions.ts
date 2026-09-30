export function hasCustomRegions(
  regions: Array<{ points: Array<{ x: number; y: number }> }> = [],
) {
  return regions.some(({ points }) => {
    if (
      points.length !== 4 ||
      points.some(({ x, y }) => ![0, 1].includes(x) || ![0, 1].includes(y))
    )
      return true;
    const corners = new Set(points.map(({ x, y }) => `${x}:${y}`));
    let area = 0;
    for (const [i, point] of points.entries()) {
      const next = points[(i + 1) % 4]!;
      area += point.x * next.y - next.x * point.y;
    }
    return corners.size !== 4 || Math.abs(area) !== 2;
  });
}
import type { PreviewRegion } from '#/views/ai-video/live/modules/overlay-coordinate';

import { regionGeometryError } from './rule-region-geometry';

export const RECOGNITION_REGION_COLOR = '#facc15';

export function toPreviewRegions(regions: unknown): PreviewRegion[] {
  if (!Array.isArray(regions)) return [];
  return regions.flatMap((region) => {
    if (!region || !Array.isArray(region.points)) return [];
    const points: { x: number; y: number }[] = [];
    for (const point of region.points) {
      if (!point || typeof point.x !== 'number' || typeof point.y !== 'number')
        return [];
      points.push({ x: point.x, y: point.y });
    }
    if (regionGeometryError(points)) return [];
    return [
      {
        points,
        title: typeof region.name === 'string' ? region.name : '',
        color: RECOGNITION_REGION_COLOR,
      },
    ];
  });
}
