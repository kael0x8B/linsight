import { describe, expect, it } from 'vitest';

import { OverlayDelay } from './overlay-delay';
describe('adaptive video delay', () => {
  it('accommodates late metadata using the shared source clock', () => {
    const delay = new OverlayDelay();
    expect(delay.observe('run1', 90_000, 126_000, 800, 1000)).toBe(1500);
    delay.observe('run1', 108_000, 900_000, 800, 2000);
    expect(delay.observe('run1', 126_000, 900_000, 800, 3000)).toBe(1800);
  });
  it('does not grow repeatedly from the video delay it just added', () => {
    const delay = new OverlayDelay();
    delay.observe('run1', 90_000, 126_000, 800, 1000);
    // At the same 1200 ms pipeline latency, a 1500 ms video delay puts video
    // 300 ms behind the incoming result rather than adding another 1500 ms.
    expect(delay.observe('run1', 117_000, 90_000, 1500, 2000)).toBe(1500);
  });
  it('resets on a new run and rejects invalid clocks', () => {
    const delay = new OverlayDelay();
    delay.observe('run1', 0, 180_000, 800, 1000);
    expect(delay.observe('run2', Number.NaN, 0, 800, 2000)).toBe(800);
    expect(delay.observe('run2', 0, 1e9, 800, 3000)).toBe(800);
  });
});

it('reserves the measured NPU cadence for the next interpolation anchor', () => {
  const delay = new OverlayDelay();
  delay.observe('run', 90_000, 54_000, 800, 1000); // Result delivery 400 ms.
  expect(delay.observe('run', 144_000, 108_000, 800, 2000)).toBe(1000); // 600 ms inference cadence.
  expect(delay.cadenceMs).toBe(600);
  expect(delay.deliveryLagMs).toBe(400);
  expect(delay.observe('run', 144_000, 180_000, 1000, 3000)).toBe(1000); // Duplicate result.
});
