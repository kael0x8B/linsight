import { describe, expect, it } from 'vitest';

import { formatFileSize } from '../upload';

describe('formatFileSize', () => {
  it.each([null, undefined, Number.NaN, Number.POSITIVE_INFINITY, -1])(
    'shows an unavailable size for %s',
    (size) => {
      expect(formatFileSize(size)).toBe('-');
    },
  );

  it.each([
    [0, '0 B'],
    [1, '1 B'],
    [1024, '1 KB'],
    [1536, '1.5 KB'],
    [1024 ** 2, '1 MB'],
  ] as const)('formats %s bytes as %s', (size, label) => {
    expect(formatFileSize(size)).toBe(label);
  });
});
