import type { AiVideoNode } from '#/api/ai-video/node';

export function nodeResources(value?: string) {
  let data: Record<string, unknown> = {};
  try { data = JSON.parse(value || '{}') ?? {}; } catch { /* Unknown heartbeat data remains unavailable. */ }
  const number = (key: string) => typeof data[key] === 'number' && Number.isFinite(data[key]) ? data[key] as number : null;
  const ratio = (used: string, total: string) => { const a = number(used); const b = number(total); return a !== null && b !== null && b > 0 ? a / b * 100 : null; };
  return { cpu: number('cpuUsage'), gpu: number('gpuUsage'), memory: ratio('memoryUsedBytes', 'memoryTotalBytes'), disk: ratio('diskUsedBytes', 'diskTotalBytes'), data };
}
export function gatewayLocation(id: number, tab = 'algorithms', cameraId?: number) {
  return { path: `/ai-video/node/${id}`, query: { tab, ...(cameraId ? { cameraId: String(cameraId) } : {}) } };
}
export function nodeStatus(node: AiVideoNode) { return node.onlineStatus === 1 ? '在线' : node.onlineStatus === 2 ? '离线' : '状态未知'; }
