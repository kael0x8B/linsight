import type { PackageResolution } from '#/api/ai-video/algorithm/package';

import { describe, expect, it } from 'vitest';

import {
  packageBindings,
  packageDeploymentSummary,
} from './package-deployment';

const resolution = {
  manifest: { models: [{ slot: 'person' }, { slot: 'ppe' }] },
  bindings: { person: 121, ppe: 122 },
  roles: {
    person: [{ id: 121, installed: true, deployable: true }],
    ppe: [
      { id: 122, installed: false, deployable: true },
      { id: 123, deployable: false },
    ],
  },
  supported: true,
} as unknown as PackageResolution;

describe('automatic algorithm deployment', () => {
  it('uses server choices on a new box without exposing a mandatory model selection', () => {
    expect(packageBindings(resolution)).toEqual({ person: 121, ppe: 122 });
    expect(
      packageDeploymentSummary(
        resolution.manifest,
        resolution,
        packageBindings(resolution),
      ),
    ).toEqual({ missing: [], installed: 1, toInstall: 1 });
  });

  it('keeps existing bindings pinned and does not silently replace a missing version', () => {
    expect(packageBindings(resolution, { person: 121, ppe: 999 })).toEqual({
      person: 121,
    });
    expect(
      packageDeploymentSummary(resolution.manifest, resolution, { person: 121 })
        .missing,
    ).toEqual([{ slot: 'ppe' }]);
  });

  it('blocks incompatible model overrides', () => {
    expect(packageBindings(resolution, { person: 121, ppe: 123 })).toEqual({
      person: 121,
    });
    expect(
      packageDeploymentSummary(resolution.manifest, resolution, {
        person: 121,
        ppe: 123,
      }).missing,
    ).toHaveLength(1);
  });

  it('counts a shared model only once across roles', () => {
    const shared = {
      ...resolution,
      roles: {
        person: resolution.roles.person!,
        ppe: resolution.roles.person!,
      },
    };
    expect(
      packageDeploymentSummary(shared.manifest, shared, {
        person: 121,
        ppe: 121,
      }),
    ).toEqual({ missing: [], installed: 1, toInstall: 0 });
  });
});
