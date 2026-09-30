import type { GatewayCapacityPreflight } from '#/api/ai-video/node/gateway';

import { describe, expect, it } from 'vitest';

import {
  gatewayCapacitySummary,
  requireGatewayCapacity,
} from './gateway-capacity';

function report(
  changes: Partial<GatewayCapacityPreflight> = {},
): GatewayCapacityPreflight {
  return {
    schemaVersion: '1.0',
    allowed: true,
    message: '通过',
    taskId: 9,
    slotLimit: 4,
    currentSlotCount: 2,
    projectedSlotCount: 3,
    sharedModelCount: 1,
    currentMemoryBudgetBytes: 128,
    projectedMemoryBudgetBytes: 192 * 1024 * 1024,
    memoryTotalBytes: 8000,
    memoryAvailableBytes: 4000,
    memoryAvailableAfterBytes: 3000,
    memorySafetyReserveBytes: 1000,
    memoryBudgetBasis: 'VERIFIED_ARTIFACT_X2_MIN_64_MIB',
    conflictTasks: [],
    models: [],
    ...changes,
  };
}

describe('gateway model capacity presentation', () => {
  it('shows deduplicated slots and memory budget', () => {
    expect(gatewayCapacitySummary(report())).toBe(
      '3/4 个模型槽位，其中 1 个共享模型已去重，内存预算 192 MiB',
    );
  });

  it('preserves the runtime conflict detail when launch is blocked', () => {
    expect(() =>
      requireGatewayCapacity(
        report({
          allowed: false,
          message:
            '需要 5/4 个模型槽位。当前冲突任务/模型：安全帽任务(#8：模型#122)',
        }),
      ),
    ).toThrow(/安全帽任务.*模型#122/);
  });
});
