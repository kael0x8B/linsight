import type { AiVideoEventApi } from '#/api/ai-video/event';
import type { AiVideoNode } from '#/api/ai-video/node';

import dayjs from 'dayjs';

export function prioritizeEvents(events: AiVideoEventApi.Event[]) {
  const pending = (event: AiVideoEventApi.Event) =>
    ['ALARM', 'ASSIGNED', 'HANDLING'].includes(event.status) ? 1 : 0;
  const severity: Record<string, number> = {
    URGENT: 5,
    CRITICAL: 4,
    MAJOR: 3,
    MINOR: 2,
    INFO: 1,
  };
  return [...events].toSorted(
    (a, b) =>
      pending(b) - pending(a) ||
      (severity[b.severity] ?? 0) - (severity[a.severity] ?? 0) ||
      dayjs(b.occurredTime).valueOf() - dayjs(a.occurredTime).valueOf(),
  );
}

export function averageResources(nodes: AiVideoNode[]) {
  const snapshots: Record<string, unknown>[] = nodes
    .filter((node) => node.onlineStatus === 1)
    .map((node) => {
      try {
        const value: unknown = JSON.parse(node.resourceSnapshot || '{}');
        return value && typeof value === 'object' && !Array.isArray(value)
          ? (value as Record<string, unknown>)
          : {};
      } catch {
        return {};
      }
    });
  const number = (value: unknown): number | undefined =>
    typeof value === 'number' && Number.isFinite(value) && value >= 0
      ? value
      : undefined;
  const percentage = (value: unknown) => {
    const result = number(value);
    return result !== undefined && result <= 100 ? result : undefined;
  };
  const average = (values: (number | undefined)[]) => {
    const available = values.filter(
      (value): value is number => value !== undefined,
    );
    return available.length > 0
      ? available.reduce((sum, value) => sum + value, 0) / available.length
      : null;
  };
  return {
    cpu: average(snapshots.map((item) => percentage(item.cpuUsage))),
    gpu: average(snapshots.map((item) => percentage(item.gpuUsage))),
    memory: average(
      snapshots.map((item) => {
        const total = number(item.memoryTotalBytes);
        const used = number(item.memoryUsedBytes);
        return total && used !== undefined && used <= total
          ? (used / total) * 100
          : undefined;
      }),
    ),
  };
}
