import { describe, expect, it } from 'vitest';

import { visibleModelVersionIds } from './model-inventory';

describe('visibleModelVersionIds', () => {
  it('uses a live empty gateway inventory instead of stale READY history', () => {
    expect(
      visibleModelVersionIds(
        [],
        [
          { actualStatus: 'READY', modelVersionId: 121 },
          { actualStatus: 'READY', modelVersionId: 128 },
        ],
        true,
      ),
    ).toEqual([]);
  });

  it('keeps active and failed operations visible while live inventory is empty', () => {
    expect(
      visibleModelVersionIds(
        [],
        [
          { actualStatus: 'QUEUED', modelVersionId: 121 },
          { actualStatus: 'FAILED', modelVersionId: 128 },
          { actualStatus: 'REMOVED', modelVersionId: 130 },
        ],
        true,
      ),
    ).toEqual([121, 128]);
  });

  it('falls back to deployment history when the gateway cannot be read', () => {
    expect(
      visibleModelVersionIds(
        [],
        [
          { actualStatus: 'READY', modelVersionId: 121 },
          { actualStatus: 'REMOVED', modelVersionId: 128 },
        ],
        false,
      ),
    ).toEqual([121]);
  });
});
