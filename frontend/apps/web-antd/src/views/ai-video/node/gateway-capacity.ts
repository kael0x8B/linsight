import type { GatewayCapacityPreflight } from '#/api/ai-video/node/gateway';

export function requireGatewayCapacity(report: GatewayCapacityPreflight) {
  if (!report.allowed) throw new Error(report.message || '模型容量预检未通过');
  return report;
}

export function gatewayCapacitySummary(report: GatewayCapacityPreflight) {
  const memory = Math.round(report.projectedMemoryBudgetBytes / 1024 / 1024);
  const shared = report.sharedModelCount
    ? `，其中 ${report.sharedModelCount} 个共享模型已去重`
    : '';
  return `${report.projectedSlotCount}/${report.slotLimit} 个模型槽位${shared}，内存预算 ${memory} MiB`;
}
