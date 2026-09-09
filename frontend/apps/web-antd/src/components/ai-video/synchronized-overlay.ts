import type { SourceStamp } from './frame-stamp';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';

type OverlayFrame = AiVideoCameraApi.OverlayFrame;
const lerp = (a: number, b: number, fraction: number) => a + (b - a) * fraction;

/** Display interpolation only. These objects never enter event/rule evaluation. */
export function alignedOverlay(frames: OverlayFrame[], stamp: SourceStamp) {
  const candidates = frames.filter(frame => frame.streamId === stamp.streamId
    && frame.sourcePts !== undefined).sort((a, b) => a.sourcePts! - b.sourcePts!);
  const before = candidates.findLast(frame => frame.sourcePts! <= stamp.sourcePts);
  const after = candidates.find(frame => frame.sourcePts! >= stamp.sourcePts);
  const nearest = !before ? after : !after ? before
    : stamp.sourcePts - before.sourcePts! <= after.sourcePts! - stamp.sourcePts ? before : after;
  if (!nearest) return;
  const anchorDistanceMs = Math.abs(stamp.sourcePts - nearest.sourcePts!) / 90;
  if (!before || !after || before === after || after.sourcePts! - before.sourcePts! > 45_000
    || before.runId !== after.runId || before.taskId !== after.taskId) {
    // A single observation is not a motion estimate. Never hold or extrapolate
    // that box beyond 100 ms when the next real observation is unavailable.
    if (anchorDistanceMs > 100) return;
    return { frame: nearest, anchorDistanceMs, interpolated: false };
  }
  const fraction = (stamp.sourcePts - before.sourcePts!) / (after.sourcePts! - before.sourcePts!);
  let tracked = false;
  const objects = nearest.objects.flatMap(object => {
    const observed = anchorDistanceMs <= 100 ? [object] : [];
    if (!object.trackId) return observed;
    const a = before.objects.find(candidate => candidate.trackId === object.trackId);
    const b = after.objects.find(candidate => candidate.trackId === object.trackId);
    if (!a || !b || a.class !== b.class || a.attributes.helmet !== b.attributes.helmet
      || a.attributes.vest !== b.attributes.vest) return observed;
    const boxKeys = ['ppeBoxX', 'ppeBoxY', 'ppeBoxWidth', 'ppeBoxHeight'];
    if (boxKeys.some(key => a.attributes[key] !== undefined || b.attributes[key] !== undefined)
      && !boxKeys.every(key => typeof a.attributes[key] === 'number' && typeof b.attributes[key] === 'number')) return observed;
    tracked = true;
    const attributes = { ...object.attributes };
    for (const key of boxKeys) {
      if (typeof a.attributes[key] === 'number' && typeof b.attributes[key] === 'number') {
        attributes[key] = lerp(a.attributes[key] as number, b.attributes[key] as number, fraction);
      }
    }
    return [{ ...object, attributes, bbox: {
      x: lerp(a.bbox.x, b.bbox.x, fraction), y: lerp(a.bbox.y, b.bbox.y, fraction),
      width: lerp(a.bbox.width, b.bbox.width, fraction), height: lerp(a.bbox.height, b.bbox.height, fraction),
    } }];
  });
  if (anchorDistanceMs > 100 && !tracked) return;
  return { frame: { ...nearest, sourcePts: tracked ? stamp.sourcePts : nearest.sourcePts, objects },
    anchorDistanceMs, interpolated: tracked,
    trackingSpanMs: tracked ? (after.sourcePts! - before.sourcePts!) / 90 : 0 };
}
