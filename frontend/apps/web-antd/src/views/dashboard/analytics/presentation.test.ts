import type { AiVideoEventApi } from '#/api/ai-video/event';
import type { AiVideoNode } from '#/api/ai-video/node';

import { describe, expect, it } from 'vitest';

import { averageResources, prioritizeEvents } from './presentation';

const event = (
  id: number,
  status: string,
  severity: string,
  occurredTime: number,
) => ({ id, status, severity, occurredTime }) as AiVideoEventApi.Event;
const node = (onlineStatus: number, resourceSnapshot?: string) =>
  ({ onlineStatus, resourceSnapshot }) as AiVideoNode;

describe('dashboard event priority', () => {
  it('keeps open events ahead of closed events, then ranks severity and recency', () => {
    const source = [
      event(1, 'CLOSED', 'URGENT', 5000),
      event(2, 'ALARM', 'MINOR', 4000),
      event(3, 'ASSIGNED', 'CRITICAL', 1000),
      event(4, 'HANDLING', 'CRITICAL', 3000),
    ];
    expect(prioritizeEvents(source).map((item) => item.id)).toEqual([
      4, 3, 2, 1,
    ]);
    expect(source.map((item) => item.id)).toEqual([1, 2, 3, 4]);
  });
});

describe('dashboard resource availability', () => {
  it('does not turn absent, invalid, or offline telemetry into zero utilization', () => {
    expect(averageResources([])).toEqual({
      cpu: null,
      gpu: null,
      memory: null,
    });
    expect(
      averageResources([
        node(1, 'null'),
        node(1, 'invalid'),
        node(1, '[]'),
        node(2, '{"cpuUsage":25}'),
      ]),
    ).toEqual({ cpu: null, gpu: null, memory: null });
  });

  it('averages each reported metric independently and preserves an actual zero', () => {
    expect(
      averageResources([
        node(1, '{"cpuUsage":20,"memoryUsedBytes":25,"memoryTotalBytes":100}'),
        node(1, '{"cpuUsage":60,"gpuUsage":0}'),
        node(1, '{}'),
        node(2, '{"cpuUsage":100,"gpuUsage":100}'),
      ]),
    ).toEqual({ cpu: 40, gpu: 0, memory: 25 });
  });

  it('excludes out-of-range percentages and inconsistent memory readings', () => {
    expect(
      averageResources([
        node(
          1,
          '{"cpuUsage":101,"gpuUsage":-1,"memoryUsedBytes":200,"memoryTotalBytes":100}',
        ),
        node(
          1,
          '{"cpuUsage":null,"gpuUsage":"20","memoryUsedBytes":0,"memoryTotalBytes":0}',
        ),
      ]),
    ).toEqual({ cpu: null, gpu: null, memory: null });
  });
});
