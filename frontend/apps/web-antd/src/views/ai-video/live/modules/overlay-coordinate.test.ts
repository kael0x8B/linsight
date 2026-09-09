import { describe, expect, it } from 'vitest';

import { mapNormalizedBox } from './overlay-coordinate';

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
