export function hasCustomRegions(regions: Array<{ points: Array<{ x: number; y: number }> }> = []) {
  return regions.some(({ points }) => {
    if (points.length !== 4 || points.some(({ x, y }) => ![0, 1].includes(x) || ![0, 1].includes(y))) return true;
    const corners = new Set(points.map(({ x, y }) => `${x}:${y}`));
    const area = points.reduce((sum, point, i) => {
      const next = points[(i + 1) % 4]!;
      return sum + point.x * next.y - next.x * point.y;
    }, 0);
    return corners.size !== 4 || Math.abs(area) !== 2;
  });
}
