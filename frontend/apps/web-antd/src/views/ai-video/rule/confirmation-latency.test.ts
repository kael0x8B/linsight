import { describe, expect, it } from 'vitest';

import {
  conflictsWithVisibilityTarget,
  estimateConfirmationLatency,
} from './confirmation-latency';

const rule = (duration: number) => ({
  condition: {
    type: 'AND',
    children: [
      { type: 'N_OF_M', n: 3, m: 5 },
      { type: 'DURATION', seconds: duration },
    ],
  },
});

describe('confirmation latency', () => {
  it('shows the low-fps lower bound on sample boundaries', () => {
    const estimate = estimateConfirmationLatency(rule(2), 0.2);
    expect(estimate?.minimumSeconds).toBe(15);
    expect(conflictsWithVisibilityTarget(estimate)).toBe(true);
  });

  it('accepts a single rule gate that leaves delivery budget', () => {
    const estimate = estimateConfirmationLatency(rule(0), 2);
    expect(estimate?.minimumSeconds).toBe(1);
    expect(conflictsWithVisibilityTarget(estimate)).toBe(false);
  });
});
