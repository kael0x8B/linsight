import { describe, expect, it } from 'vitest';

import {
  canCancelPreviewReconnect,
  evaluatePreviewMediaHealth,
  isPreviewSessionExpired,
  reconnectDelaySeconds,
  shouldReconnectFailedSession,
} from './camera-preview-health';

describe('camera preview media health', () => {
  it('keeps a connected session while the first RTP packets are within grace', () => {
    expect(
      evaluatePreviewMediaHealth({
        connectedAt: 1000,
        decodedFrames: 0,
        documentHidden: false,
        now: 20_999,
        packetsReceived: 0,
      }),
    ).toBe('WAITING');
  });

  it('reconnects when a connected session receives no RTP after grace', () => {
    expect(
      evaluatePreviewMediaHealth({
        connectedAt: 1000,
        decodedFrames: 0,
        documentHidden: false,
        now: 21_000,
        packetsReceived: 0,
      }),
    ).toBe('RECONNECT_NO_RTP');
  });

  it('does not treat incoming RTP as decoded video forever', () => {
    expect(
      evaluatePreviewMediaHealth({
        connectedAt: 1000,
        decodedFrames: 0,
        documentHidden: false,
        firstPacketAt: 2000,
        lastPacketAt: 22_000,
        now: 22_000,
        packetsReceived: 500,
      }),
    ).toBe('RECONNECT_NO_FRAME');
  });

  it('does not reconnect a background tab solely because decoding is paused', () => {
    expect(
      evaluatePreviewMediaHealth({
        connectedAt: 1000,
        decodedFrames: 100,
        documentHidden: true,
        firstPacketAt: 2000,
        lastFrameAt: 3000,
        lastPacketAt: 30_000,
        now: 30_000,
        packetsReceived: 900,
      }),
    ).toBe('HEALTHY');
  });

  it('uses bounded exponential reconnect delay', () => {
    expect(
      [0, 1, 2, 3, 4].map((attempt) => reconnectDelaySeconds(attempt)),
    ).toEqual([5, 10, 20, 30, 30]);
  });

  it('recognizes expired control-plane ownership independently of RTP health', () => {
    // RequestClient unwraps Axios errors to the CommonResult body.
    expect(
      isPreviewSessionExpired({
        code: 1_020_000_123,
        msg: '预览会话不存在或已过期',
      }),
    ).toBe(true);
    expect(
      isPreviewSessionExpired({ response: { data: { code: 1_020_000_123 } } }),
    ).toBe(true);
    expect(isPreviewSessionExpired({ data: { code: 1_020_000_123 } })).toBe(
      true,
    );
    expect(isPreviewSessionExpired({ response: { data: { code: 500 } } })).toBe(
      false,
    );
    expect(isPreviewSessionExpired(new Error('Network Error'))).toBe(false);
    expect(isPreviewSessionExpired(null)).toBe(false);
  });

  it('keeps rebuilding a closed or expired session but cancels a false failed state', () => {
    for (const reason of ['SESSION_EXPIRED', 'SESSION_CLOSED']) {
      expect(canCancelPreviewReconnect(reason)).toBe(false);
    }
    expect(canCancelPreviewReconnect('SESSION_FAILED')).toBe(true);
    expect(canCancelPreviewReconnect('SESSION_POLL_FAILED')).toBe(true);
    expect(canCancelPreviewReconnect('PEER_CONNECTION_DISCONNECTED')).toBe(
      true,
    );
    expect(canCancelPreviewReconnect('RECONNECT_MEDIA_STALLED')).toBe(true);
  });

  it('trusts recent decoded frames over a failed server-side session poll', () => {
    expect(shouldReconnectFailedSession('connected', 1000, 2000)).toBe(false);
    expect(shouldReconnectFailedSession('connected', 1000, 5_999)).toBe(false);
    expect(shouldReconnectFailedSession('connected', 1000, 6_000)).toBe(true);
    expect(shouldReconnectFailedSession('failed', 1000, 2000)).toBe(true);
    expect(shouldReconnectFailedSession('connected', undefined, 2000)).toBe(true);
  });
});
