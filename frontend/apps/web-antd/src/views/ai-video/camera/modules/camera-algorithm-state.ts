import type { AiVideoCameraApi } from '#/api/ai-video/camera';

// Effective status can be STALE; lifecycle permissions always use the stored state.
export function capabilityActions(capability: AiVideoCameraApi.CameraCapability) {
  const state = capability.actualStatus;
  if (capability.entryAccessId) return { remove: state === 'STOPPED', start: state === 'STOPPED', stop: state !== 'STOPPED', stopping: false };
  return {
    remove: ['DRAFT', 'STOPPED'].includes(state),
    start: ['DRAFT', 'FAILED', 'OFFLINE', 'STOPPED'].includes(state),
    stop: ['FAILED', 'OFFLINE', 'RUNNING', 'STARTING', 'STOPPING'].includes(state) && !!capability.activeRunId,
    stopping: state === 'STOPPING' || (capability.desiredStatus === 'STOPPED' && !!capability.errorCode),
  };
}

