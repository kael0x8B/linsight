import { describe, expect, it } from 'vitest';

import { hasCustomRegions, toPreviewRegions } from './rule-regions';

describe('reusing camera regions', () => {
  const corners = [
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ];
  it('full frames and unrestricted rules do not require a camera-specific check', () => {
    expect(hasCustomRegions()).toBe(false);
    expect(hasCustomRegions([{ points: corners }])).toBe(false);
    expect(hasCustomRegions([{ points: corners.toReversed() }])).toBe(false);
  });
  it('subregions and malformed corner polygons cannot be treated as full frames', () => {
    expect(
      hasCustomRegions([
        { points: corners.map(({ x, y }) => ({ x: x / 2, y })) },
      ]),
    ).toBe(true);
    expect(
      hasCustomRegions([
        { points: [corners[0]!, corners[2]!, corners[1]!, corners[3]!] },
      ]),
    ).toBe(true);
  });
  it('keeps only valid polygon geometry for yellow live overlays', () => {
    const source = {
      name: '门口',
      points: corners,
      condition: { type: 'AND' },
    };
    expect(toPreviewRegions([source, { points: [null, {}, {}] }])).toEqual([
      { title: '门口', points: corners, color: '#facc15' },
    ]);
    expect(toPreviewRegions(null)).toEqual([]);
    expect(
      toPreviewRegions([{ points: corners.map((p) => ({ ...p, x: 2 })) }]),
    ).toEqual([]);
    expect(source.points).toEqual(corners);
  });
});
