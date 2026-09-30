import type { SourceStamp } from './frame-stamp';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { legacyStateSignature } from '../../views/ai-video/live/modules/legacy-object-presentation';
import {
  describeObject,
  displayBox,
} from '../../views/ai-video/live/modules/overlay-presentation';

type OverlayFrame = AiVideoCameraApi.OverlayFrame;
type OverlayObject = AiVideoCameraApi.OverlayObject;
const OBSERVATION_WINDOW_MS = 100;
// Presentation grace, measured from the original observation, never from a repaint.
export const OVERLAY_HOLD_MS = 600;
const MAX_TRACK_SPAN_MS = 1000;
const CONTINUOUS_TRACK_SPAN_MS = 1500;
const lerp = (a: number, b: number, fraction: number) => a + (b - a) * fraction;

function sameRun(a: OverlayFrame, b: OverlayFrame) {
  return (
    a.cameraId === b.cameraId &&
    a.taskId === b.taskId &&
    a.runId === b.runId &&
    a.streamId === b.streamId
  );
}

function geometryContinuity(a: OverlayObject, b: OverlayObject) {
  return (
    a.attributes.displayGeometryContinuity === true &&
    b.attributes.displayGeometryContinuity === true &&
    describeObject(a).visibleByDefault &&
    describeObject(b).visibleByDefault
  );
}

function continuousGeometry(a: OverlayObject, b: OverlayObject) {
  const left = describeObject(a).bbox;
  const right = describeObject(b).bbox;
  // A body track alone is insufficient when a provider switches the part it
  // associated with that body. Never animate a box from one person's head to another.
  const dx =
    right.x + right.width / 2 - left.x - left.width / 2 - (b.bbox.x - a.bbox.x);
  const dy =
    right.y +
    right.height / 2 -
    left.y -
    left.height / 2 -
    (b.bbox.y - a.bbox.y);
  return (
    Math.abs(dx) <= 0.75 * Math.max(left.width, right.width) &&
    Math.abs(dy) <= 0.75 * Math.max(left.height, right.height) &&
    Math.max(left.width, right.width) <=
      2 * Math.min(left.width, right.width) &&
    Math.max(left.height, right.height) <=
      2 * Math.min(left.height, right.height)
  );
}

function stationaryBetween(previous: OverlayObject, current: OverlayObject) {
  const box = describeObject(previous).bbox;
  return (
    Math.abs(previous.bbox.x - current.bbox.x) <= box.width * 0.15 &&
    Math.abs(previous.bbox.y - current.bbox.y) <= box.height * 0.15
  );
}

function interpolateObject(
  a: OverlayObject,
  b: OverlayObject,
  fraction: number,
): OverlayObject | undefined {
  if (
    a.class !== b.class ||
    legacyStateSignature(a) !== legacyStateSignature(b) ||
    !continuousGeometry(a, b)
  )
    return;
  const aDisplay = describeObject(a);
  const bDisplay = describeObject(b);
  if (
    !geometryContinuity(a, b) &&
    (aDisplay.state !== bDisplay.state ||
      aDisplay.label !== bDisplay.label ||
      aDisplay.labelKey !== bDisplay.labelKey ||
      aDisplay.visibleByDefault !== bDisplay.visibleByDefault)
  )
    return;
  // Interpolate display geometry independently; ppeBox only supports old observations.
  const boxKeys: string[] = [];
  for (const prefix of ['displayBox', 'ppeBox']) {
    const keys = ['X', 'Y', 'Width', 'Height'].map((suffix) => prefix + suffix);
    if (
      keys.some(
        (key) =>
          Object.hasOwn(a.attributes, key) || Object.hasOwn(b.attributes, key),
      )
    ) {
      if (
        !displayBox(a.attributes, prefix) ||
        !displayBox(b.attributes, prefix)
      )
        return;
      boxKeys.push(...keys);
    }
  }
  const attributes = { ...a.attributes };
  for (const key of boxKeys) {
    if (
      typeof a.attributes[key] === 'number' &&
      typeof b.attributes[key] === 'number'
    ) {
      attributes[key] = lerp(
        a.attributes[key] as number,
        b.attributes[key] as number,
        fraction,
      );
    }
  }
  return {
    ...a,
    attributes,
    bbox: {
      x: lerp(a.bbox.x, b.bbox.x, fraction),
      y: lerp(a.bbox.y, b.bbox.y, fraction),
      width: lerp(a.bbox.width, b.bbox.width, fraction),
      height: lerp(a.bbox.height, b.bbox.height, fraction),
    },
  };
}

function overlaps(a: OverlayObject, b: OverlayObject) {
  const width = Math.max(
    0,
    Math.min(a.bbox.x + a.bbox.width, b.bbox.x + b.bbox.width) -
      Math.max(a.bbox.x, b.bbox.x),
  );
  const height = Math.max(
    0,
    Math.min(a.bbox.y + a.bbox.height, b.bbox.y + b.bbox.height) -
      Math.max(a.bbox.y, b.bbox.y),
  );
  return (
    width * height >
    0.5 * Math.min(a.bbox.width * a.bbox.height, b.bbox.width * b.bbox.height)
  );
}

/** Bounded display continuity only; never fed to inference, rules or saved evidence. */
export function alignedOverlay(frames: OverlayFrame[], stamp: SourceStamp) {
  const candidates = frames
    .filter(
      (frame) =>
        frame.streamId === stamp.streamId && Number.isFinite(frame.sourcePts),
    )
    .toSorted((a, b) => a.sourcePts! - b.sourcePts!);
  const before = candidates.findLast(
    (frame) => frame.sourcePts! <= stamp.sourcePts,
  );
  const after = candidates.find((frame) => frame.sourcePts! >= stamp.sourcePts);
  const base = before ?? after;
  if (!base) return;
  const distance = Math.abs(stamp.sourcePts - base.sourcePts!) / 90;
  const span =
    before && after ? (after.sourcePts! - before.sourcePts!) / 90 : 0;
  const canInterpolate =
    before &&
    after &&
    sameRun(before, after) &&
    span > 0 &&
    (span <= MAX_TRACK_SPAN_MS ||
      (span <= CONTINUOUS_TRACK_SPAN_MS &&
        before.objects.some((object) =>
          after.objects.some(
            (next) =>
              object.trackId &&
              object.trackId === next.trackId &&
              geometryContinuity(object, next),
          ),
        )));
  if (
    (!before && distance > OBSERVATION_WINDOW_MS) ||
    (before && distance > OVERLAY_HOLD_MS && !canInterpolate)
  )
    return;

  // Prefer the observation at/before the video frame. A later result must not
  // announce a new person, changed identity or changed conclusion prematurely.
  const recent = candidates.filter(
    (frame) =>
      sameRun(frame, base) &&
      frame.sourcePts! <= base.sourcePts! &&
      (stamp.sourcePts - frame.sourcePts!) / 90 <= OVERLAY_HOLD_MS,
  );
  const known = new Map<string, { object: OverlayObject; pts: number }>();
  for (const frame of recent)
    for (const object of frame.objects) {
      if (object.trackId && describeObject(object).state !== 'unknown') {
        known.set(object.trackId, { object, pts: frame.sourcePts! });
      }
    }
  let tracked = false;
  let heldObjects = 0;
  let maxHoldAgeMs = 0;
  function holdLimit(object: OverlayObject, pts: number) {
    if (!object.trackId) return OBSERVATION_WINDOW_MS;
    const previousFrame = candidates.findLast(
      (frame) =>
        sameRun(frame, base!) &&
        frame.sourcePts! < pts &&
        (pts - frame.sourcePts!) / 90 <= MAX_TRACK_SPAN_MS &&
        frame.objects.some(
          (candidate) =>
            candidate.trackId === object.trackId &&
            candidate.class === object.class &&
            describeObject(candidate).state !== 'unknown',
        ),
    );
    const previous = previousFrame?.objects.find(
      (candidate) => candidate.trackId === object.trackId,
    );
    // Without two observations there is no evidence that the target is stationary.
    if (!previous || !previousFrame || !continuousGeometry(previous, object))
      return OBSERVATION_WINDOW_MS;
    const a = describeObject(previous).bbox;
    const b = describeObject(object).bbox;
    const movement = Math.max(
      Math.abs(b.x + b.width / 2 - a.x - a.width / 2) /
        Math.min(a.width, b.width),
      Math.abs(b.y + b.height / 2 - a.y - a.height / 2) /
        Math.min(a.height, b.height),
      Math.abs(b.width - a.width) / Math.min(a.width, b.width),
      Math.abs(b.height - a.height) / Math.min(a.height, b.height),
    );
    const interval = (pts - previousFrame.sourcePts!) / 90;
    // Permit at most 15% of a box's estimated movement error. Moving targets
    // expire quickly; stationary detections may bridge a brief missed inference.
    return Math.max(
      OBSERVATION_WINDOW_MS,
      Math.min(
        OVERLAY_HOLD_MS,
        movement > 0 ? (interval * 0.15) / movement : OVERLAY_HOLD_MS,
      ),
    );
  }
  function hold(object: OverlayObject, pts: number): OverlayObject {
    const ageMs = Math.max(0, (stamp.sourcePts - pts) / 90);
    heldObjects++;
    maxHoldAgeMs = Math.max(maxHoldAgeMs, ageMs);
    return {
      ...object,
      attributes: {
        ...object.attributes,
        overlayHeld: true,
        overlayAgeMs: ageMs,
      },
    };
  }
  const objects = base.objects.flatMap((object) => {
    const prior = object.trackId && known.get(object.trackId);
    if (
      describeObject(object).state === 'unknown' &&
      object.attributes.displayGeometryContinuity !== true &&
      prior &&
      prior.object.class === object.class &&
      describeObject(prior.object).visibleByDefault &&
      stationaryBetween(prior.object, object) &&
      (stamp.sourcePts - prior.pts) / 90 <= holdLimit(prior.object, prior.pts)
    ) {
      return [hold(prior.object, prior.pts)];
    }
    const next =
      canInterpolate && object.trackId
        ? after.objects.find(
            (candidate) =>
              candidate.trackId === object.trackId &&
              (span <= MAX_TRACK_SPAN_MS ||
                geometryContinuity(object, candidate)),
          )
        : undefined;
    const interpolated =
      next && interpolateObject(object, next, distance / span);
    if (interpolated) {
      tracked = true;
      return [interpolated];
    }
    const limit =
      next && !continuousGeometry(object, next)
        ? OBSERVATION_WINDOW_MS
        : holdLimit(object, base.sourcePts!);
    if (distance > limit) return [];
    return [
      before && distance > OBSERVATION_WINDOW_MS
        ? hold(object, base.sourcePts!)
        : object,
    ];
  });
  for (const [trackId, prior] of known) {
    if (
      !describeObject(prior.object).visibleByDefault ||
      (stamp.sourcePts - prior.pts) / 90 > holdLimit(prior.object, prior.pts) ||
      base.objects.some(
        (object) =>
          object.trackId === trackId ||
          (object.class === prior.object.class &&
            overlaps(object, prior.object)),
      )
    )
      continue;
    objects.push(hold(prior.object, prior.pts));
  }
  const nearestDistance = Math.min(
    distance,
    after ? Math.abs(after.sourcePts! - stamp.sourcePts) / 90 : distance,
  );
  return {
    frame: {
      ...base,
      sourcePts: tracked ? stamp.sourcePts : base.sourcePts,
      objects,
    },
    anchorDistanceMs: Math.max(
      tracked ? nearestDistance : distance,
      maxHoldAgeMs,
    ),
    interpolated: tracked,
    heldObjects,
    maxHoldAgeMs,
    trackingSpanMs: tracked ? span : 0,
  };
}
