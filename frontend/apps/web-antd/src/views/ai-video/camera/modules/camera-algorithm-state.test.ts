import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { describe, expect, it } from 'vitest';

import { capabilityActions } from './camera-algorithm-state';

function capability(
  actualStatus: string,
  effectiveStatus = actualStatus,
  activeRunId?: string,
) {
  return {
    actualStatus,
    effectiveStatus,
    activeRunId,
  } as AiVideoCameraApi.CameraCapability;
}
describe('camera algorithm lifecycle', () => {
  it('a rejected stop remains retryable after a running heartbeat', () => {
    expect(
      capabilityActions({
        ...capability('RUNNING', 'RUNNING', 'run-1'),
        desiredStatus: 'STOPPED',
        errorCode: 'MODEL_COMMAND_FAILED',
      }),
    ).toEqual({ start: false, stop: true, remove: false, stopping: true });
  });
  it('entrance uses its own enabled state without a continuous-task run id', () => {
    expect(
      capabilityActions({ ...capability('RUNNING'), entryAccessId: 8 }),
    ).toEqual({ start: false, stop: true, remove: false, stopping: false });
    expect(
      capabilityActions({ ...capability('STOPPED'), entryAccessId: 8 }),
    ).toEqual({ start: true, stop: false, remove: true, stopping: false });
  });
  it('stale running tasks can request a stop but cannot be removed or restarted', () => {
    expect(capabilityActions(capability('RUNNING', 'STALE', 'run-1'))).toEqual({
      start: false,
      stop: true,
      remove: false,
      stopping: false,
    });
  });
  it('retains removal guard until a stop is confirmed', () => {
    expect(capabilityActions(capability('STOPPING', 'STALE', 'run-1'))).toEqual(
      { start: false, stop: true, remove: false, stopping: true },
    );
    expect(capabilityActions(capability('STOPPED'))).toEqual({
      start: true,
      stop: false,
      remove: true,
      stopping: false,
    });
  });
  it('offers state reconciliation when a gateway stopped locally', () => {
    expect(
      capabilityActions({
        ...capability('STOPPED', 'STOPPED', 'run-1'),
        desiredStatus: 'RUNNING',
      }).stop,
    ).toBe(true);
  });
  it('drafts can be removed but do not send stop commands without a run', () => {
    expect(capabilityActions(capability('DRAFT')).remove).toBe(true);
    expect(capabilityActions(capability('FAILED')).stop).toBe(false);
    expect(
      capabilityActions(capability('FAILED', 'OFFLINE', 'run-1')).stop,
    ).toBe(true);
  });
});
