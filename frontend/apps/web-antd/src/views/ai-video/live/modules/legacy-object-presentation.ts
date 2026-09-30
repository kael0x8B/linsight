import type { AiVideoCameraApi } from '#/api/ai-video/camera';

export function legacyStateSignature(object: AiVideoCameraApi.OverlayObject) {
  return JSON.stringify([object.attributes.helmet, object.attributes.vest]);
}

/** Compatibility for pre-SDK PPE frames. New algorithms use the display contract. */
export function legacyObjectPresentation(
  object: AiVideoCameraApi.OverlayObject,
) {
  const attribute = ['helmet', 'vest'].find((key) =>
    ['absent', 'present', 'unknown'].includes(String(object.attributes[key])),
  );
  if (
    object.class !== 'person' ||
    object.attributes.ppeConfirmedPerson !== true ||
    !attribute
  )
    return;
  const state = String(object.attributes[attribute]);
  const keys =
    attribute === 'vest'
      ? { absent: 'noVest', present: 'vest', unknown: 'vestUnknown' }
      : { absent: 'noHelmet', present: 'helmet', unknown: 'helmetUnknown' };
  let confidence: number | undefined = object.confidence;
  if (state === 'unknown') confidence = undefined;
  else if (typeof object.attributes.ppeConfidence === 'number')
    confidence = object.attributes.ppeConfidence;
  let displayState: 'alert' | 'normal' | 'unknown' = 'unknown';
  if (state === 'absent') displayState = 'alert';
  else if (state === 'present') displayState = 'normal';
  return {
    labelKey: keys[state as keyof typeof keys],
    classKey: `${attribute}_${state}`,
    confidence,
    visibleByDefault: state === 'absent',
    state: displayState,
    boxPrefix: state === 'unknown' ? undefined : 'ppeBox',
  };
}
