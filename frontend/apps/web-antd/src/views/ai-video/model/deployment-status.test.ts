import { describe, expect, it, vi } from 'vitest';

vi.mock('#/locales', () => ({ $t: (key: string) => key }));

import { deploymentStatusText, isDeploymentPending } from './deployment-status';

describe('model dependency preparation progress', () => {
  it('keeps polling every preparation stage until model loading finishes', () => {
    for (const stage of [
      'CHECKING_ENV', 'INSTALLING_DEPS', 'DOWNLOADING_DEPS',
      'RETRYING_DEPS', 'VERIFYING_ENV', 'ENV_READY', 'LOADING',
    ]) {
      expect(isDeploymentPending(stage)).toBe(true);
      expect(deploymentStatusText(stage)).toBe(`model-deployment.${stage}`);
    }
  });

  it('allows retry after failure and stops polling terminal or absent states', () => {
    expect(isDeploymentPending('FAILED')).toBe(false);
    expect(isDeploymentPending('READY')).toBe(false);
    expect(isDeploymentPending(undefined)).toBe(false);
  });
});
