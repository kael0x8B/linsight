import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { describe, expect, it } from 'vitest';

import { acceptsTaskFrame, describeObject, frameTimestampMillis, isFreshFrame } from './overlay-presentation';

const object: AiVideoCameraApi.OverlayObject = { class: 'person', confidence: 0.8,
  bbox: { x: 0.1, y: 0.1, width: 0.2, height: 0.4 },
  attributes: { ppeConfirmedPerson: true, helmet: 'absent', ppeConfidence: 0.65 } };
const frame: AiVideoCameraApi.OverlayFrame = { cameraId: 2, taskId: 3, runId: 'current',
  sessionId: 's', frameId: 'current:1', sourceWidth: 640, sourceHeight: 480,
  timestamp: '2026-09-06T10:00:00.000Z', objects: [object] };
const task: AiVideoCameraApi.CameraCapability = { taskId: 3, taskName: 'helmet',
  algorithmId: 10, nodeId: 1, actualStatus: 'RUNNING', desiredStatus: 'RUNNING',
  effectiveStatus: 'RUNNING', activeRunId: 'current', validationOnly: true };

describe('recognition display', () => {
  it('does not present person confidence as a helmet conclusion when helmet status is unknown', () => {
    const result = describeObject({ ...object, confidence: 0.45,
      attributes: { helmet: 'unknown', ppeConfirmedPerson: true } });
    expect(result).toMatchObject({ labelKey: 'helmetUnknown', classKey: 'helmet_unknown',
      confidence: undefined, bbox: object.bbox });
  });
  it('draws the actual PPE region while keeping the person box for unknown and legacy results', () => {
    const head = { x: 0.12, y: 0.11, width: 0.08, height: 0.09 };
    const attributes = { ...object.attributes, ppeBoxX: head.x, ppeBoxY: head.y,
      ppeBoxWidth: head.width, ppeBoxHeight: head.height };
    for (const helmet of ['absent', 'present']) {
      expect(describeObject({ ...object, attributes: { ...attributes, helmet } }).bbox).toEqual(head);
    }
    expect(describeObject({ ...object, attributes: { ...attributes, helmet: 'unknown' } }).bbox).toEqual(object.bbox);
    expect(describeObject(object).bbox).toEqual(object.bbox);
    for (const invalid of [Number.NaN, Number.POSITIVE_INFINITY, -0.1, 1, 2, '0.12']) {
      expect(describeObject({ ...object, attributes: { ...attributes, ppeBoxX: invalid } }).bbox).toEqual(object.bbox);
    }
    expect(describeObject({ ...object, attributes: { ...attributes, ppeBoxWidth: 0 } }).bbox).toEqual(object.bbox);
    expect(object.bbox).toEqual({ x: 0.1, y: 0.1, width: 0.2, height: 0.4 });
  });
  it('labels the PPE conclusion with PPE confidence and hides normal/unknown results by default', () => {
    expect(describeObject(object)).toMatchObject({ labelKey: 'noHelmet', confidence: 0.65, visibleByDefault: true });
    for (const helmet of ['present', 'unknown']) {
      expect(describeObject({ ...object, attributes: { ...object.attributes, helmet } }).visibleByDefault).toBe(false);
    }
    expect(describeObject({ ...object, attributes: {} }).labelKey).toBe('person');
  });
  it('expires boxes by source time and rejects invalid or future timestamps', () => {
    const now = frameTimestampMillis(frame.timestamp) + 1000;
    expect(isFreshFrame(frame, now, 750)).toBe(false);
    expect(isFreshFrame(frame, now, 15000)).toBe(true);
    expect(isFreshFrame({ ...frame, timestamp: now - 1000 }, now, 15000)).toBe(true);
    expect(isFreshFrame({ ...frame, timestamp: 'invalid' }, now, 15000)).toBe(false);
    expect(isFreshFrame(frame, now - 10000, 15000)).toBe(false);
  });
  it('isolates camera tasks and runs, drops duplicates/out-of-order results and stopped tasks', () => {
    expect(acceptsTaskFrame(frame, task)).toBe(true);
    expect(acceptsTaskFrame(frame, { ...task, taskId: 9 })).toBe(false);
    expect(acceptsTaskFrame(frame, { ...task, activeRunId: 'old' })).toBe(false);
    expect(acceptsTaskFrame(frame, { ...task, effectiveStatus: 'STALE' })).toBe(false);
    expect(acceptsTaskFrame(frame, task, frame)).toBe(false);
    expect(acceptsTaskFrame({ ...frame, timestamp: '2026-09-06T09:59:00Z' }, task, frame)).toBe(false);
  });
});

it('labels reflective vest states and does not confuse unknown with a violation',()=>{
  const candidate={...object,attributes:{ppeConfirmedPerson:true,vest:'absent',ppeConfidence:.72}};
  expect(describeObject(candidate)).toMatchObject({labelKey:'noVest',confidence:.72,visibleByDefault:true});
  expect(describeObject({...candidate,attributes:{...candidate.attributes,vest:'present'}})).toMatchObject({labelKey:'vest',visibleByDefault:false});
  expect(describeObject({...candidate,attributes:{...candidate.attributes,vest:'unknown'}})).toMatchObject({labelKey:'vestUnknown',visibleByDefault:false,confidence:undefined});
});
