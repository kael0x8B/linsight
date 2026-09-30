import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { describe, expect, it } from 'vitest';

import sharedDisplayFixture from '../../../../../../../../runtime/tests/fixtures/algorithm-display.json';
import {
  acceptsTaskFrame,
  describeObject,
  frameTimestampMillis,
  isFreshFrame,
  presentationColor,
} from './overlay-presentation';

const object: AiVideoCameraApi.OverlayObject = {
  class: 'person',
  confidence: 0.8,
  bbox: { x: 0.1, y: 0.1, width: 0.2, height: 0.4 },
  attributes: {
    ppeConfirmedPerson: true,
    helmet: 'absent',
    ppeConfidence: 0.65,
  },
};
const frame: AiVideoCameraApi.OverlayFrame = {
  cameraId: 2,
  taskId: 3,
  runId: 'current',
  sessionId: 's',
  frameId: 'current:1',
  sourceWidth: 640,
  sourceHeight: 480,
  timestamp: '2026-09-06T10:00:00.000Z',
  objects: [object],
};
const task: AiVideoCameraApi.CameraCapability = {
  taskId: 3,
  taskName: 'helmet',
  algorithmId: 10,
  nodeId: 1,
  actualStatus: 'RUNNING',
  desiredStatus: 'RUNNING',
  effectiveStatus: 'RUNNING',
  activeRunId: 'current',
  validationOnly: true,
};

describe('recognition display', () => {
  it('does not present person confidence as a helmet conclusion when helmet status is unknown', () => {
    const result = describeObject({
      ...object,
      confidence: 0.45,
      attributes: { helmet: 'unknown', ppeConfirmedPerson: true },
    });
    expect(result).toMatchObject({
      labelKey: 'helmetUnknown',
      classKey: 'helmet_unknown',
      confidence: undefined,
      bbox: object.bbox,
    });
  });
  it('draws the actual PPE region while keeping the person box for unknown and legacy results', () => {
    const head = { x: 0.12, y: 0.11, width: 0.08, height: 0.09 };
    const attributes = {
      ...object.attributes,
      ppeBoxX: head.x,
      ppeBoxY: head.y,
      ppeBoxWidth: head.width,
      ppeBoxHeight: head.height,
    };
    for (const helmet of ['absent', 'present']) {
      expect(
        describeObject({ ...object, attributes: { ...attributes, helmet } })
          .bbox,
      ).toEqual(head);
    }
    expect(
      describeObject({
        ...object,
        attributes: { ...attributes, helmet: 'unknown' },
      }).bbox,
    ).toEqual(object.bbox);
    expect(describeObject(object).bbox).toEqual(object.bbox);
    for (const invalid of [
      Number.NaN,
      Number.POSITIVE_INFINITY,
      -0.1,
      1,
      2,
      '0.12',
    ]) {
      expect(
        describeObject({
          ...object,
          attributes: { ...attributes, ppeBoxX: invalid },
        }).bbox,
      ).toEqual(object.bbox);
    }
    expect(
      describeObject({
        ...object,
        attributes: { ...attributes, ppeBoxWidth: 0 },
      }).bbox,
    ).toEqual(object.bbox);
    expect(object.bbox).toEqual({ x: 0.1, y: 0.1, width: 0.2, height: 0.4 });
  });
  it('labels the PPE conclusion with PPE confidence and hides normal/unknown results by default', () => {
    expect(describeObject(object)).toMatchObject({
      labelKey: 'noHelmet',
      confidence: 0.65,
      visibleByDefault: true,
    });
    for (const helmet of ['present', 'unknown']) {
      expect(
        describeObject({
          ...object,
          attributes: { ...object.attributes, helmet },
        }).visibleByDefault,
      ).toBe(false);
    }
    expect(describeObject({ ...object, attributes: {} }).labelKey).toBe(
      'person',
    );
  });
  it('expires boxes by source time and rejects invalid or future timestamps', () => {
    const now = frameTimestampMillis(frame.timestamp) + 1000;
    expect(isFreshFrame(frame, now, 750)).toBe(false);
    expect(isFreshFrame(frame, now, 15_000)).toBe(true);
    expect(isFreshFrame({ ...frame, timestamp: now - 1000 }, now, 15_000)).toBe(
      true,
    );
    expect(isFreshFrame({ ...frame, timestamp: 'invalid' }, now, 15_000)).toBe(
      false,
    );
    expect(isFreshFrame(frame, now - 10_000, 15_000)).toBe(false);
  });
  it('isolates camera tasks and runs, drops duplicates/out-of-order results and stopped tasks', () => {
    expect(acceptsTaskFrame(frame, task)).toBe(true);
    expect(acceptsTaskFrame(frame, { ...task, taskId: 9 })).toBe(false);
    expect(acceptsTaskFrame(frame, { ...task, activeRunId: 'old' })).toBe(
      false,
    );
    expect(acceptsTaskFrame(frame, { ...task, effectiveStatus: 'STALE' })).toBe(
      false,
    );
    expect(acceptsTaskFrame(frame, task, frame)).toBe(false);
    expect(
      acceptsTaskFrame(
        { ...frame, timestamp: '2026-09-06T09:59:00Z' },
        task,
        frame,
      ),
    ).toBe(false);
  });
});

it('labels reflective vest states and does not confuse unknown with a violation', () => {
  const candidate = {
    ...object,
    attributes: {
      ppeConfirmedPerson: true,
      vest: 'absent',
      ppeConfidence: 0.72,
    },
  };
  expect(describeObject(candidate)).toMatchObject({
    labelKey: 'noVest',
    confidence: 0.72,
    visibleByDefault: true,
  });
  expect(
    describeObject({
      ...candidate,
      attributes: { ...candidate.attributes, vest: 'present' },
    }),
  ).toMatchObject({ labelKey: 'vest', visibleByDefault: false });
  expect(
    describeObject({
      ...candidate,
      attributes: { ...candidate.attributes, vest: 'unknown' },
    }),
  ).toMatchObject({
    labelKey: 'vestUnknown',
    visibleByDefault: false,
    confidence: undefined,
  });
});

it('renders supplier labels as plain bounded text without a new business branch', () => {
  const result = describeObject({
    ...object,
    class: 'supplier-new-result',
    attributes: { displayLabel: '<external>区域结果', eventCandidate: true },
  });
  expect(result).toMatchObject({
    label: '<external>区域结果',
    visibleByDefault: true,
    bbox: object.bbox,
  });
  expect(
    describeObject({
      ...object,
      attributes: { displayLabel: 'x'.repeat(200), visibleByDefault: false },
    }),
  ).toMatchObject({ label: 'x'.repeat(100), visibleByDefault: false });
});

describe('algorithm-neutral display contract', () => {
  const head = { x: 0.12, y: 0.11, width: 0.08, height: 0.09 };
  const attributes = {
    displayLabel: '外部算法结果',
    displayState: 'alert',
    displayConfidence: 0.93,
    displayBoxX: head.x,
    displayBoxY: head.y,
    displayBoxWidth: head.width,
    displayBoxHeight: head.height,
  };
  it('renders the exact object verified by the real Python package worker', () => {
    expect(describeObject(sharedDisplayFixture.expected)).toMatchObject({
      bbox: { x: 0.17, y: 0.12, width: 0.1, height: 0.15 },
      label: '未佩戴安全帽',
      confidence: 0.93,
      state: 'alert',
      visibleByDefault: true,
    });
    expect(sharedDisplayFixture.expected.bbox.height).toBe(0.8);
  });
  it('uses the supplied display box and score even for unknown algorithm types and custom labels', () => {
    for (const name of [
      'supplier-new-class',
      'person',
      'fall',
      'bus',
      'face',
    ]) {
      const result = describeObject({
        ...object,
        class: name,
        confidence: 0.66,
        attributes,
      });
      expect(result).toMatchObject({
        bbox: head,
        label: '外部算法结果',
        confidence: 0.93,
        state: 'alert',
        visibleByDefault: true,
      });
      expect(presentationColor(result, '#34d399')).toBe('#fb7185');
    }
    expect(object.bbox.height).toBe(0.4);
  });
  it('treats label, score, geometry and state as independent fields with safe fallbacks', () => {
    expect(
      describeObject({
        ...object,
        attributes: {
          ...attributes,
          helmet: 'unknown',
          ppeConfirmedPerson: true,
        },
      }).confidence,
    ).toBe(0.93);
    for (const score of [
      null,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      -0.1,
      1.1,
      '0.9',
    ]) {
      expect(
        describeObject({
          ...object,
          attributes: { ...attributes, displayConfidence: score },
        }).confidence,
      ).toBeUndefined();
    }
    for (const x of [
      -0.1,
      1,
      0.99,
      Number.NaN,
      Number.POSITIVE_INFINITY,
      '0.12',
    ]) {
      expect(
        describeObject({
          ...object,
          attributes: { ...attributes, displayBoxX: x },
        }).bbox,
      ).toEqual(object.bbox);
    }
    const partial = {
      displayBoxX: 0.1,
      displayState: 'alert',
      displayLabel: '局部字段',
    };
    expect(describeObject({ ...object, attributes: partial }).bbox).toEqual(
      object.bbox,
    );
    const unknown = describeObject({
      ...object,
      attributes: { ...attributes, displayState: 'unknown' },
    });
    expect(unknown).toMatchObject({
      state: 'unknown',
      confidence: undefined,
      visibleByDefault: false,
    });
    expect(presentationColor(unknown, '#34d399')).toBe('#fbbf24');
    expect(
      describeObject({
        ...object,
        attributes: { ...attributes, displayState: 'normal' },
      }).visibleByDefault,
    ).toBe(false);
  });
  it('continues to display older SDK packages without new fields', () => {
    const legacy = describeObject({
      ...object,
      class: 'external',
      attributes: { displayLabel: '旧算法' },
    });
    expect(legacy).toMatchObject({
      label: '旧算法',
      bbox: object.bbox,
      confidence: 0.8,
      visibleByDefault: true,
    });
  });
});
