import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { legacyObjectPresentation } from './legacy-object-presentation';

export type DisplayState = 'alert' | 'neutral' | 'normal' | 'unknown';
export interface ObjectPresentation {
  bbox: AiVideoCameraApi.OverlayBoundingBox;
  label?: string;
  labelKey?: string;
  classKey: string;
  confidence?: number;
  state?: DisplayState;
  visibleByDefault: boolean;
}

export function frameTimestampMillis(timestamp: number | string) {
  return typeof timestamp === 'number' ? timestamp : Date.parse(timestamp);
}

export function describeObject(
  object: AiVideoCameraApi.OverlayObject,
): ObjectPresentation {
  const attrs = object.attributes;
  const hasDisplay = [
    'displayState',
    'displayConfidence',
    'displayBoxX',
    'displayBoxY',
    'displayBoxWidth',
    'displayBoxHeight',
  ].some((key) => Object.hasOwn(attrs, key));
  const legacy = hasDisplay ? undefined : legacyObjectPresentation(object);
  const label =
    typeof attrs.displayLabel === 'string'
      ? attrs.displayLabel.slice(0, 100)
      : undefined;
  const state = ['alert', 'neutral', 'normal', 'unknown'].includes(
    String(attrs.displayState),
  )
    ? (attrs.displayState as DisplayState)
    : legacy?.state;
  let confidence: number | undefined = object.confidence;
  if (Object.hasOwn(attrs, 'displayConfidence'))
    confidence = validConfidence(attrs.displayConfidence);
  else if (legacy) confidence = legacy.confidence;
  let labelKey = legacy?.labelKey;
  if (labelKey === undefined) {
    if (object.class === 'person') labelKey = 'person';
    else if (object.class === 'face') labelKey = 'face';
  }
  return {
    bbox:
      displayBox(attrs) ??
      (legacy?.boxPrefix ? displayBox(attrs, legacy.boxPrefix) : undefined) ??
      object.bbox,
    label,
    labelKey: label === undefined ? labelKey : undefined,
    classKey: legacy?.classKey ?? object.class,
    confidence: state === 'unknown' ? undefined : confidence,
    state,
    visibleByDefault:
      typeof attrs.visibleByDefault === 'boolean'
        ? attrs.visibleByDefault
        : (legacy?.visibleByDefault ??
          (state !== 'normal' && state !== 'unknown')),
  };
}

function validConfidence(value: unknown) {
  return typeof value === 'number' &&
    Number.isFinite(value) &&
    value >= 0 &&
    value <= 1
    ? value
    : undefined;
}

export function displayBox(
  attributes: AiVideoCameraApi.OverlayObject['attributes'],
  prefix = 'displayBox',
): AiVideoCameraApi.OverlayBoundingBox | undefined {
  const {
    [`${prefix}X`]: x,
    [`${prefix}Y`]: y,
    [`${prefix}Width`]: width,
    [`${prefix}Height`]: height,
  } = attributes;
  if (
    typeof x !== 'number' ||
    typeof y !== 'number' ||
    typeof width !== 'number' ||
    typeof height !== 'number' ||
    ![x, y, width, height].every((value) => Number.isFinite(value)) ||
    x < 0 ||
    y < 0 ||
    x >= 1 ||
    y >= 1 ||
    width <= 0 ||
    height <= 0 ||
    x + width > 1.000001 ||
    y + height > 1.000001
  ) {
    return undefined;
  }
  return {
    x,
    y,
    width: Math.min(width, 1 - x),
    height: Math.min(height, 1 - y),
  };
}

/** Semantic result states take precedence over the identifying layer colour. */
export function presentationColor(
  presentation: ObjectPresentation,
  layerColor?: unknown,
) {
  const semantic = {
    alert: '#fb7185',
    normal: '#34d399',
    unknown: '#fbbf24',
    neutral: undefined,
  };
  if (presentation.state && semantic[presentation.state])
    return semantic[presentation.state]!;
  if (typeof layerColor === 'string' && /^#[\da-f]{6}$/i.test(layerColor))
    return layerColor;
  let hash = 0;
  for (const c of presentation.classKey)
    hash = (hash * 31 + (c.codePointAt(0) ?? 0)) % 4_294_967_296;
  return ['#22d3ee', '#a78bfa', '#f59e0b', '#34d399', '#fb7185', '#60a5fa'][
    hash % 6
  ]!;
}

export function isFreshFrame(
  frame: AiVideoCameraApi.OverlayFrame | undefined,
  now: number,
  maxAgeMs: number,
) {
  if (!frame) return false;
  const age = now - frameTimestampMillis(frame.timestamp);
  return Number.isFinite(age) && age >= -1000 && age <= maxAgeMs;
}

export function acceptsTaskFrame(
  frame: AiVideoCameraApi.OverlayFrame,
  task:
    | Pick<
        AiVideoCameraApi.CameraCapability,
        'activeRunId' | 'effectiveStatus' | 'taskId'
      >
    | undefined,
  previous?: AiVideoCameraApi.OverlayFrame,
) {
  return (
    task?.effectiveStatus === 'RUNNING' &&
    frame.taskId === task.taskId &&
    frame.runId === task.activeRunId &&
    (!previous ||
      frameTimestampMillis(frame.timestamp) >
        frameTimestampMillis(previous.timestamp))
  );
}
