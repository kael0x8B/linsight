import { describe, expect, it } from 'vitest';

import { nodeResources } from './presentation';

describe('node resource presentation', () => {
  it('uses an NPU heartbeat when a discrete GPU metric is unavailable', () => {
    const resources = nodeResources(
      JSON.stringify({ gpuUsage: null, npuUsage: 37.5 }),
    );

    expect(resources.accelerator).toBe(37.5);
  });

  it('shows the busier accelerator when GPU and NPU are both reported', () => {
    const resources = nodeResources(
      JSON.stringify({ gpuUsage: 22, npuUsage: 46 }),
    );

    expect(resources.accelerator).toBe(46);
  });

  it('keeps missing or malformed resource data unavailable', () => {
    expect(nodeResources('{bad json').accelerator).toBeNull();
    expect(
      nodeResources(JSON.stringify({ npuUsage: '50' })).accelerator,
    ).toBeNull();
  });

  it('summarizes a bounded disk cleanup receipt', () => {
    const resources = nodeResources(
      JSON.stringify({
        diskCleanupAfterPercent: 72,
        diskCleanupFreedBytes: 2_147_483_648,
        diskCleanupStatus: 'RECLAIMED',
      }),
    );

    expect(resources.cleanupSummary).toBe(
      '自动处置已回收 2.0 GiB，磁盘降至 72%',
    );
  });

  it('shows exact execution providers and targets reported by Runtime', () => {
    const resources = nodeResources(
      JSON.stringify({
        modelEnvironment: {
          formats: ['ONNX', 'RKNN'],
          providers: [
            {
              code: 'rknpu2',
              deviceType: 'NPU',
              formats: ['RKNN'],
              runtime: 'rknn-toolkit-lite2',
              runtimeVersion: '2.3.2',
              targets: ['rk3588'],
              vendor: 'rockchip',
            },
          ],
          rknnTargets: ['rk3588'],
          schemaVersion: '1.0',
        },
      }),
    );

    expect(resources.modelFormatSummary).toBe('ONNX、RKNN');
    expect(resources.executionSummary).toBe(
      'Rockchip NPU / rk3588（rknn-toolkit-lite2 2.3.2）',
    );
    expect(resources.executionProviders[0]).toMatchObject({
      code: 'rknpu2',
      targets: ['rk3588'],
    });
  });
});
