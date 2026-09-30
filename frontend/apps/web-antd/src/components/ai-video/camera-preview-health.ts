export const FIRST_RTP_GRACE_MS = 20_000;
export const FIRST_FRAME_GRACE_MS = 20_000;
export const MEDIA_STALL_GRACE_MS = 15_000;
export const FAILED_SESSION_MEDIA_GRACE_MS = 5_000;

export type PreviewMediaHealthDecision =
  | 'HEALTHY'
  | 'RECONNECT_DECODE_STALLED'
  | 'RECONNECT_MEDIA_STALLED'
  | 'RECONNECT_NO_FRAME'
  | 'RECONNECT_NO_RTP'
  | 'WAITING';

export interface PreviewMediaHealthSample {
  connectedAt: number;
  decodedFrames: number;
  documentHidden: boolean;
  firstPacketAt?: number;
  lastFrameAt?: number;
  lastPacketAt?: number;
  now: number;
  packetsReceived: number;
}

export function evaluatePreviewMediaHealth(
  sample: PreviewMediaHealthSample,
): PreviewMediaHealthDecision {
  if (sample.documentHidden) return 'HEALTHY';

  if (sample.packetsReceived === 0) {
    return sample.now - sample.connectedAt >= FIRST_RTP_GRACE_MS
      ? 'RECONNECT_NO_RTP'
      : 'WAITING';
  }

  if (sample.decodedFrames === 0) {
    return sample.firstPacketAt !== undefined &&
      sample.now - sample.firstPacketAt >= FIRST_FRAME_GRACE_MS
      ? 'RECONNECT_NO_FRAME'
      : 'WAITING';
  }

  if (
    sample.lastFrameAt !== undefined &&
    sample.now - sample.lastFrameAt >= MEDIA_STALL_GRACE_MS
  ) {
    return sample.lastPacketAt !== undefined &&
      sample.now - sample.lastPacketAt >= MEDIA_STALL_GRACE_MS
      ? 'RECONNECT_MEDIA_STALLED'
      : 'RECONNECT_DECODE_STALLED';
  }

  return 'HEALTHY';
}

export function reconnectDelaySeconds(attempt: number) {
  return Math.min(5 * 2 ** Math.max(0, attempt), 30);
}

export function isPreviewSessionExpired(error: unknown): boolean {
  const response = error as
    | undefined
    | {
        code?: number;
        data?: { code?: number };
        response?: { data?: { code?: number } };
      };
  return (
    (response?.code ??
      response?.response?.data?.code ??
      response?.data?.code) === 1_020_000_123
  );
}

export function canCancelPreviewReconnect(reason: string): boolean {
  // A server-side FAILED state can race with an actively receiving peer.
  // CLOSED/EXPIRED mean the control-plane lease is gone and need a new session.
  return !['SESSION_CLOSED', 'SESSION_EXPIRED'].includes(reason);
}

export function shouldReconnectFailedSession(
  connectionState: RTCPeerConnectionState | undefined,
  lastFrameAt: number | undefined,
  now: number,
): boolean {
  return (
    connectionState !== 'connected' ||
    lastFrameAt === undefined ||
    now - lastFrameAt >= FAILED_SESSION_MEDIA_GRACE_MS
  );
}
