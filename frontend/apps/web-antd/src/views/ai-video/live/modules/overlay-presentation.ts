import type { AiVideoCameraApi } from '#/api/ai-video/camera';

export function frameTimestampMillis(timestamp: number | string) {
  return typeof timestamp === 'number' ? timestamp : Date.parse(timestamp);
}

export function describeObject(object: AiVideoCameraApi.OverlayObject) {
  const attribute = ['helmet', 'vest'].find(key =>
    ['absent', 'present', 'unknown'].includes(String(object.attributes[key])));
  const state = attribute ? object.attributes[attribute] : undefined;
  if (object.class === 'person' && object.attributes.ppeConfirmedPerson === true && attribute) {
    const keys = attribute === 'vest'
      ? { absent: 'noVest', present: 'vest', unknown: 'vestUnknown' }
      : { absent: 'noHelmet', present: 'helmet', unknown: 'helmetUnknown' };
    return {
      bbox: state === 'unknown' ? object.bbox : ppeBox(object) ?? object.bbox,
      labelKey: keys[state as keyof typeof keys],
      classKey: `${attribute}_${state}`,
      confidence: state === 'unknown' ? undefined
        : typeof object.attributes.ppeConfidence === 'number' ? object.attributes.ppeConfidence : object.confidence,
      visibleByDefault: state === 'absent',
    };
  }

  return { bbox: object.bbox, labelKey: object.class === 'person' ? 'person' : object.class === 'face' ? 'face' : undefined, classKey: object.class,
    confidence: object.confidence, visibleByDefault: true };
}

function ppeBox(object: AiVideoCameraApi.OverlayObject): AiVideoCameraApi.OverlayBoundingBox | undefined {
  const { ppeBoxX: x, ppeBoxY: y, ppeBoxWidth: width, ppeBoxHeight: height } = object.attributes;
  if (typeof x !== 'number' || typeof y !== 'number' || typeof width !== 'number' || typeof height !== 'number'
    || ![x, y, width, height].every(Number.isFinite)
    || x < 0 || y < 0 || x >= 1 || y >= 1 || width <= 0 || height <= 0 || x + width > 1.000001 || y + height > 1.000001) {
    return undefined;
  }
  return { x, y, width: Math.min(width, 1 - x), height: Math.min(height, 1 - y) };
}

export function isFreshFrame(frame: AiVideoCameraApi.OverlayFrame | undefined, now: number, maxAgeMs: number) {
  if (!frame) return false;
  const age = now - frameTimestampMillis(frame.timestamp);
  return Number.isFinite(age) && age >= -1000 && age <= maxAgeMs;
}

export function acceptsTaskFrame(frame: AiVideoCameraApi.OverlayFrame,
  task: Pick<AiVideoCameraApi.CameraCapability, 'activeRunId' | 'effectiveStatus' | 'taskId'> | undefined, previous?: AiVideoCameraApi.OverlayFrame) {
  return task?.effectiveStatus === 'RUNNING' && frame.taskId === task.taskId
    && frame.runId === task.activeRunId
    && (!previous || frameTimestampMillis(frame.timestamp) > frameTimestampMillis(previous.timestamp));
}
