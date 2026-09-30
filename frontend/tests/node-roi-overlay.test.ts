import type { App } from 'vue';

import { createApp, h, nextTick, ref } from 'vue';

import { afterEach, describe, expect, it, vi } from 'vitest';

import PreviewOverlay from '../apps/web-antd/src/views/ai-video/live/modules/preview-overlay.vue';

vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) => key,
}));

let app: App | undefined;
let root: HTMLElement;
afterEach(() => {
  app?.unmount();
  root?.remove();
  vi.restoreAllMocks();
});

describe('recognition ROI display', () => {
  it('draws a yellow dashed polygon independently from detection boxes and clears only the requested layer', async () => {
    const context = {
      strokeStyle: '',
      lineWidth: 0,
      font: '',
      fillStyle: '',
      setTransform: vi.fn(),
      clearRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      closePath: vi.fn(),
      stroke: vi.fn(),
      strokeRect: vi.fn(),
      setLineDash: vi.fn(),
      fillRect: vi.fn(),
      fillText: vi.fn(),
      measureText: () => ({ width: 30 }),
    };
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(
      context as unknown as CanvasRenderingContext2D,
    );
    vi.spyOn(
      HTMLCanvasElement.prototype,
      'getBoundingClientRect',
    ).mockReturnValue(new DOMRect(0, 0, 1000, 600));
    const regionsVisible = ref(true);
    const boxesVisible = ref(false);
    root = document.createElement('div');
    document.body.append(root);
    app = createApp({
      render: () =>
        h(PreviewOverlay, {
          regions: [
            {
              title: '车牌区域',
              color: '#facc15',
              points: [
                { x: 0.2, y: 0.3 },
                { x: 0.7, y: 0.25 },
                { x: 0.75, y: 0.8 },
                { x: 0.2, y: 0.85 },
              ],
            },
          ],
          videoWidth: 640,
          videoHeight: 480,
          showRegions: regionsVisible.value,
          visible: boxesVisible.value,
          historical: true,
          frame: {
            cameraId: 2,
            frameId: 'frame-1',
            sessionId: 'preview',
            timestamp: Date.now(),
            sourceWidth: 640,
            sourceHeight: 480,
            objects: [
              {
                class: 'car',
                confidence: 0.9,
                attributes: {},
                bbox: { x: 0.1, y: 0.2, width: 0.2, height: 0.3 },
              },
            ],
          },
        }),
    });
    app.mount(root);
    await nextTick();
    expect(context.stroke).toHaveBeenCalled();
    expect(context.strokeStyle).toBe('#facc15');
    expect(context.setLineDash).toHaveBeenCalledWith([8, 5]);
    expect(context.moveTo).toHaveBeenCalledWith(260, 180);
    expect(context.lineTo).toHaveBeenCalledWith(660, 150);
    expect(context.closePath).toHaveBeenCalled();
    expect(context.strokeRect).not.toHaveBeenCalled();

    vi.clearAllMocks();
    regionsVisible.value = false;
    boxesVisible.value = true;
    await nextTick();
    await nextTick();
    expect(context.clearRect).toHaveBeenCalled();
    expect(context.stroke).not.toHaveBeenCalled();
    expect(context.strokeRect).toHaveBeenCalled();
    expect(root.querySelector('canvas')?.dataset.regionCount).toBe('0');
  });
});
