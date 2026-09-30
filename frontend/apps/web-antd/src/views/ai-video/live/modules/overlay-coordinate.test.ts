import { describe, expect, it } from 'vitest';

import { mapNormalizedBox, mapNormalizedPolygon } from './overlay-coordinate';

describe('mapNormalizedBox', () => {
  it('maps normalized source coordinates through horizontal letterbox offsets', () => {
    const result = mapNormalizedBox(
      { height: 0.4, width: 0.3, x: 0.1, y: 0.2 },
      1080,
      1920,
      1000,
      1000,
    );

    expect(result.height).toBeCloseTo(400);
    expect(result.width).toBeCloseTo(168.75);
    expect(result.x).toBeCloseTo(275);
    expect(result.y).toBeCloseTo(200);
  });
});

describe('polygon ROI coordinates', () => {
  it('preserves a quadrilateral through side letterboxing instead of replacing it with a bounding box', () => {
    expect(
      mapNormalizedPolygon(
        [
          { x: 0.2, y: 0.3 },
          { x: 0.7, y: 0.25 },
          { x: 0.75, y: 0.8 },
          { x: 0.2, y: 0.85 },
        ],
        640,
        480,
        1000,
        600,
      ),
    ).toEqual([
      { x: 260, y: 180 },
      { x: 660, y: 150 },
      { x: 700, y: 480 },
      { x: 260, y: 510 },
    ]);
  });
});
