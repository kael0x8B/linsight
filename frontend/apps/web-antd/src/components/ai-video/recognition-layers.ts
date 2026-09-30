import type { SourceStamp } from './frame-stamp';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { alignedOverlay } from './synchronized-overlay';

export interface RecognitionLayer {
  key: string;
  title: string;
  color: string;
  visible: boolean;
  frame?: AiVideoCameraApi.OverlayFrame;
}
export function layerColor(key: string) {
  let hash = 0;
  for (const c of key)
    hash = (hash * 31 + (c.codePointAt(0) ?? 0)) % 4_294_967_296;
  return ['#38bdf8', '#a78bfa', '#fbbf24', '#34d399', '#fb7185', '#fb923c'][
    hash % 6
  ]!;
}
export function capabilityKey(value: AiVideoCameraApi.CameraCapability) {
  return value.entryAccessId
    ? `entry-${value.entryAccessId}`
    : `task-${value.taskId}`;
}
export function cameraPreviewNode(
  camera: AiVideoCameraApi.Camera | undefined,
  nodes: {
    id: number;
    onlineStatus: number;
    previewTunnelConnected?: boolean;
    status: number;
  }[],
  current?: number,
) {
  const ready = nodes.filter(
    (n) => n.status === 0 && n.onlineStatus === 1 && n.previewTunnelConnected,
  );
  const associated = new Set(
    camera?.recognitionCapabilities?.map((c) => c.nodeId),
  );
  return (
    ready.find((n) => n.id === current && associated.has(n.id))?.id ??
    ready.find((n) => associated.has(n.id))?.id ??
    ready.find((n) => n.id === current)?.id ??
    ready[0]?.id
  );
}

/** Independent histories prevent one algorithm's cadence/run reset clearing another. */
export class RecognitionLayerBuffer {
  private histories = new Map<string, AiVideoCameraApi.OverlayFrame[]>();
  private layers: RecognitionLayer[] = [];
  align(stamp: SourceStamp, locate?: (key: string) => SourceStamp | undefined) {
    const matches = this.layers.flatMap((layer) => {
      if (!layer.visible) return [];
      const history = (this.histories.get(layer.key) ?? []).flatMap((frame) => {
        if (frame.streamId === stamp.streamId) return [frame];
        // An exact encoded-frame fingerprint is required across decoder epochs/boxes.
        // Host clocks, frame numbers, and equal numeric PTS alone are not identities.
        const mapped = frame.frameKey && locate?.(frame.frameKey);
        if (!mapped || mapped.streamId !== stamp.streamId) return [];
        return [
          { ...frame, streamId: mapped.streamId, sourcePts: mapped.sourcePts },
        ];
      });
      const match = alignedOverlay(history, stamp);
      return match ? [{ ...match, layer }] : [];
    });
    if (matches.length === 0) return;
    const first = matches[0]!;
    return {
      ...first,
      heldObjects: matches.reduce(
        (total, match) => total + match.heldObjects,
        0,
      ),
      maxHoldAgeMs: Math.max(...matches.map((match) => match.maxHoldAgeMs)),
      anchorDistanceMs: Math.max(
        ...matches.map((match) => match.anchorDistanceMs),
      ),
      interpolated: matches.some((match) => match.interpolated),
      trackingSpanMs: Math.max(...matches.map((match) => match.trackingSpanMs)),
      frame: {
        ...first.frame,
        objects: matches.flatMap(({ frame, layer }) =>
          frame.objects.map((object) => ({
            ...object,
            trackId: `${layer.key}:${object.trackId ?? ''}`,
            attributes: {
              ...object.attributes,
              overlayLayer: layer.title,
              overlayColor: layer.color,
            },
          })),
        ),
      },
      layerCount: matches.length,
    };
  }
  clear() {
    this.histories.clear();
  }
  update(layers: RecognitionLayer[]) {
    this.layers = layers.slice(0, 64);
    const keys = new Set(
      this.layers.filter((l) => l.visible && l.frame).map((l) => l.key),
    );
    for (const key of this.histories.keys())
      if (!keys.has(key)) this.histories.delete(key);
    for (const layer of this.layers) {
      const frame = layer.frame;
      if (!layer.visible || !frame) continue;
      let history = this.histories.get(layer.key) ?? [];
      const previous = history.at(-1);
      if (
        previous &&
        (previous.runId !== frame.runId ||
          previous.streamId !== frame.streamId ||
          previous.cameraId !== frame.cameraId)
      )
        history = [];
      if (history.at(-1)?.frameId !== frame.frameId) history.push(frame);
      this.histories.set(layer.key, history.slice(-40));
    }
  }
}
