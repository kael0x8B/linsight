import type { RecognitionLayer } from './recognition-layers';

import { describe, expect, it } from 'vitest';

import {
  cameraPreviewNode,
  RecognitionLayerBuffer,
} from './recognition-layers';
function layer(key: string, streamId = 'a', pts = 9000): RecognitionLayer {
  return {
    key,
    title: key,
    color: '#38bdf8',
    visible: true,
    frame: {
      cameraId: 1,
      sessionId: 's',
      taskId: Number(key),
      runId: key,
      streamId,
      sourcePts: pts,
      frameKey: key.padStart(32, '0'),
      frameId: `${key}:${pts}`,
      timestamp: 0,
      sourceWidth: 640,
      sourceHeight: 480,
      objects: [
        {
          class: 'person',
          confidence: 0.9,
          trackId: 'same',
          attributes: {},
          bbox: { x: 0.1, y: 0.1, width: 0.2, height: 0.2 },
        },
      ],
    },
  };
}
describe('camera algorithm layers', () => {
  it('merges independent task histories and namespaces track IDs', () => {
    const buffer = new RecognitionLayerBuffer();
    buffer.update([layer('1'), layer('2')]);
    const result = buffer.align({ streamId: 'a', sourcePts: 9000 });
    expect(result?.frame.objects).toHaveLength(2);
    expect(result?.frame.objects.map((o) => o.trackId)).toEqual([
      '1:same',
      '2:same',
    ]);
    buffer.update([layer('1'), { ...layer('2'), visible: false }]);
    expect(
      buffer.align({ streamId: 'a', sourcePts: 9000 })?.frame.objects,
    ).toHaveLength(1);
  });
  it('requires exact frame fingerprints across boxes and never equates numeric PTS', () => {
    const buffer = new RecognitionLayerBuffer();
    buffer.update([layer('1'), layer('2', 'other-box', 500)]);
    expect(buffer.align({ streamId: 'a', sourcePts: 9000 })?.layerCount).toBe(
      1,
    );
    expect(
      buffer.align({ streamId: 'a', sourcePts: 9000 }, (key) =>
        key.endsWith('2') ? { streamId: 'a', sourcePts: 9000 } : undefined,
      )?.layerCount,
    ).toBe(2);
    expect(
      buffer.align({ streamId: 'a', sourcePts: 73_000 }, () => ({
        streamId: 'a',
        sourcePts: 9000,
      })),
    ).toBeUndefined();
  });
  it('clears one run without dropping other algorithms and suppresses missing frames', () => {
    const buffer = new RecognitionLayerBuffer();
    buffer.update([layer('1'), layer('2')]);
    buffer.update([{ ...layer('1'), frame: undefined }, layer('2')]);
    expect(
      buffer.align({ streamId: 'a', sourcePts: 9000 })?.frame.objects[0]
        ?.trackId,
    ).toBe('2:same');
  });
  it('clears held boxes on task stop and reports holds from every visible layer', () => {
    const buffer = new RecognitionLayerBuffer();
    buffer.update([layer('1', 'a', 0), layer('2', 'a', 0)]);
    buffer.update([layer('1'), layer('2')]);
    expect(
      buffer.align({ streamId: 'a', sourcePts: 36_000 })?.heldObjects,
    ).toBe(2);
    buffer.update([{ ...layer('1'), frame: undefined }, layer('2')]);
    const retained = buffer.align({ streamId: 'a', sourcePts: 36_000 });
    expect(retained?.heldObjects).toBe(1);
    expect(retained?.maxHoldAgeMs).toBe(300);
    expect(retained?.frame.objects.map((object) => object.trackId)).toEqual([
      '2:same',
    ]);
    buffer.update([]);
    expect(buffer.align({ streamId: 'a', sourcePts: 36_000 })).toBeUndefined();
  });
  it('chooses a ready associated box for each camera among thousands of nodes', () => {
    const nodes = Array.from({ length: 2000 }, (_, i) => ({
      id: i + 1,
      status: 0,
      onlineStatus: 1,
      previewTunnelConnected: true,
    }));
    const camera = {
      recognitionCapabilities: [{ nodeId: 1530 }],
    } as Parameters<typeof cameraPreviewNode>[0];
    expect(cameraPreviewNode(camera, nodes)).toBe(1530);
    nodes[1529]!.onlineStatus = 2;
    expect(cameraPreviewNode(camera, nodes)).toBe(1);
  });
});
