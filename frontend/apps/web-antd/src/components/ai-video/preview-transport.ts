import type { AiVideoCameraApi } from '#/api/ai-video/camera';

/** Session signaling only; the shared player always receives native WebRTC video. */
export interface PreviewTransport {
  create: (offer: { cameraId: number; nodeId: number; offerSdp: string; offerType: 'offer' }) => Promise<AiVideoCameraApi.PreviewSession>;
  get: (sessionId: string) => Promise<AiVideoCameraApi.PreviewSession>;
  release: (sessionId: string) => Promise<unknown>;
}
