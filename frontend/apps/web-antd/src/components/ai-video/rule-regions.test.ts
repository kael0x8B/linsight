import { describe, expect, it } from 'vitest';

import { hasCustomRegions } from './rule-regions';

describe('reusing camera regions', () => {
  const corners = [{ x: 0, y: 0 }, { x: 1, y: 0 }, { x: 1, y: 1 }, { x: 0, y: 1 }];
  it('full frames and unrestricted rules do not require a camera-specific check', () => {
    expect(hasCustomRegions()).toBe(false);
    expect(hasCustomRegions([{ points: corners }])).toBe(false);
    expect(hasCustomRegions([{ points: corners.toReversed() }])).toBe(false);
  });
  it('subregions and malformed corner polygons cannot be treated as full frames', () => {
    expect(hasCustomRegions([{ points: corners.map(({ x, y }) => ({ x: x / 2, y })) }])).toBe(true);
    expect(hasCustomRegions([{ points: [corners[0]!, corners[2]!, corners[1]!, corners[3]!] }])).toBe(true);
  });
});
