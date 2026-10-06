import type { GatewayTransport } from '#/api/ai-video/node/gateway';

import { describe, expect, it, vi } from 'vitest';

import { uploadApplication } from './application-upgrade';

describe('application package upload', () => {
  it('resumes from the acknowledged offset and submits only after the final chunk', async () => {
    const send = vi.fn(async (action, _payload) => {
      if (action.endsWith('begin')) return { offset: 3 };
      if (action.endsWith('chunk')) return { offset: 6 };
      return { accepted: true };
    });
    const progress = vi.fn();
    await uploadApplication(new File(['abcdef'], 'app.lup'), 'id', send as GatewayTransport, progress, () => false);
    expect(send.mock.calls[1]).toEqual(['app-upgrade.upload.chunk', { id: 'id', offset: 3, data: btoa('def') }]);
    expect(send.mock.calls[2]?.[0]).toBe('app-upgrade.upload.finish');
    expect(progress).toHaveBeenLastCalledWith(100);
  });

  it('never submits an incomplete or cancelled upload', async () => {
    const send = vi.fn(async (action) => ({ offset: action.endsWith('begin') ? 0 : 1 }));
    const file = new File(['abc'], 'app.lup');
    await expect(uploadApplication(file, 'id', send as GatewayTransport, vi.fn(), () => false)).rejects.toThrow('INVALID_OFFSET');
    expect(send.mock.calls.some(([action]) => action.endsWith('finish'))).toBe(false);
    send.mockClear();
    expect(await uploadApplication(file, 'id', send as GatewayTransport, vi.fn(), () => true)).toBe(false);
    expect(send).toHaveBeenCalledTimes(1);
  });
});
