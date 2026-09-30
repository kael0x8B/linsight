import type { AiVideoEventApi } from '#/api/ai-video/event';

import { describe, expect, it } from 'vitest';

import {
  eventFrame,
  firstEvidence,
  formatTime,
  originalSnapshotAvailable,
  recognitionConfidence,
  recognitionResult,
  recognitionScoreLabel,
  ruleSummary,
  settingsSummary,
} from './presentation';

const event = {
  id: 258,
  cameraId: 2,
  eventType: 'SAFETY_HELMET',
  occurredTime: 1_788_746_141_541,
  objectSnapshot: {
    class: 'person',
    confidence: 0.44,
    bbox: { x: 0.2, y: 0.3, width: 0.4, height: 0.5 },
    attributes: {
      helmet: 'absent',
      ppeConfirmedPerson: true,
      ppeConfidence: 0.88,
    },
  },
  taskSnapshot: {
    parameters: {
      ppeConfidence: 0.5,
      personConfidence: 0.3,
      unknownPolicy: 'NO_ALARM',
      sampleFps: 1,
    },
  },
  ruleSnapshot: {
    condition: {
      type: 'AND',
      children: [
        { type: 'N_OF_M', n: 2, m: 3 },
        { type: 'DURATION', seconds: 1 },
      ],
    },
  },
} as unknown as AiVideoEventApi.Event;

describe('customer event presentation', () => {
  it('shows the saved plate identity without promoting raw OCR into a confirmed result', () => {
    expect(recognitionResult({
      class: 'license_plate', attributes: { plateNumber: '吉WD0011', plateText: '贵WD0011' },
    })).toBe('吉WD0011');
    expect(recognitionResult({
      class: 'license_plate', attributes: { plateText: '贵WD0011' },
    })).toBe('车牌未确认');
    expect(recognitionResult({
      class: 'person', attributes: { displayLabel: '未佩戴安全帽' },
    })).toBe('未佩戴安全帽');
    expect(recognitionResult({
      class: 'scene', attributes: { observedCount: 3 },
    })).toBe('区域人数：3');
    expect(recognitionResult(null)).toBe('—');
  });
  it('explains absence counts without presenting a fabricated 100% detection confidence', () => {
    const absence = {
      ...event,
      eventType: 'PERSON_ABSENCE',
      objectSnapshot: {
        class: 'scene',
        confidence: 1,
        attributes: { observedCount: 0, thresholdCount: 1 },
      },
    };
    expect(recognitionScoreLabel(absence)).toBe('区域人数');
    expect(recognitionConfidence(absence)).toBe('0 人 / 门槛 1 人');
    expect(eventFrame(absence).objects).toEqual([]);
    expect(
      ruleSummary({ type: 'COUNT_BELOW', regionId: 'desk', min: 2 }, [
        { id: 'desk', name: '值班岗' },
      ]),
    ).toBe('值班岗人数少于 2 人');
    expect(ruleSummary({ type: 'COUNT', min: 3 })).toBe('目标数量达到 3 个');
  });
  it('shows the assigned-person decision without a synthetic score', () => {
    const absence = {
      ...event,
      eventType: 'PERSON_ABSENCE',
      objectSnapshot: {
        class: 'post_status',
        confidence: 1,
        attributes: {
          displayConfidence: null,
          displayLabel: '指定人员 · 身份待确认',
        },
      },
    };
    expect(recognitionScoreLabel(absence)).toBe('识别结果');
    expect(recognitionConfidence(absence)).toBe('指定人员 · 身份待确认');
  });
  it('labels entrance matching similarity separately from detection confidence', () => {
    const entrance = {
      ...event,
      eventType: 'ENTRY_IDENTITY_UNCONFIRMED',
      objectSnapshot: {
        ...event.objectSnapshot,
        similarity: 0.15,
        confidence: 0.93,
      },
    };
    expect(recognitionScoreLabel(entrance)).toBe('人脸相似度');
    expect(recognitionConfidence(entrance)).toBe('15%');
    expect(eventFrame(entrance).objects[0]?.class).toContain('相似度');
    expect(eventFrame(entrance).objects[0]?.confidence).toBe(0.15);
    expect(recognitionScoreLabel(event)).toBe('识别置信度');
  });
  it('shows Beijing time for real epoch timestamps and rejects missing dates', () => {
    expect(formatTime(1_788_746_141_541)).toBe('2026-09-07 09:55:41');
    expect(formatTime('1788746141541')).toBe(formatTime(1_788_746_141_541));
    expect(formatTime(null)).toBe('未记录');
    expect(formatTime('invalid')).toBe('未记录');
  });
  it('uses helmet confidence, not the person confidence', () => {
    expect(recognitionConfidence(event)).toBe('88%');
    expect(
      recognitionConfidence({ ...event, objectSnapshot: { attributes: {} } }),
    ).toBe('未记录');
  });
  it('explains the actual rule and unknown policy', () => {
    const settings = settingsSummary(event);
    expect(settings[0]?.value).toBe(
      '最近 3 次分析中至少 2 次符合条件，并且持续 1 秒',
    );
    expect(
      settings.find((item) => item.label === '无法确认时')?.value,
    ).toContain('不触发告警');
    expect(ruleSummary({ type: 'NEW_RULE' })).toContain('暂无法展示');
  });
  it('uses only valid historical target coordinates', () => {
    expect(eventFrame(event).objects).toHaveLength(1);
    expect(
      eventFrame({
        ...event,
        objectSnapshot: { bbox: { x: 0, y: 0, width: -1, height: 1 } },
      }).objects,
    ).toEqual([]);
  });
  it('keeps the first trigger snapshot when later evidence is also present', () => {
    const media = [
      { id: 12, mediaType: 'SNAPSHOT', status: 'READY' },
      { id: 10, mediaType: 'SNAPSHOT', status: 'FAILED' },
      { id: 11, mediaType: 'SNAPSHOT', status: 'READY' },
    ];
    const value = { ...event, media } as AiVideoEventApi.Event;
    expect(firstEvidence(value, 'SNAPSHOT')?.id).toBe(11);
    expect(value.media?.[0]?.id).toBe(12);
  });
  it('rejects overwritten historical evidence even when signature queries differ', () => {
    const value = {
      ...event,
      media: [
        {
          id: 1,
          mediaType: 'SNAPSHOT',
          status: 'READY',
          sha256: 'first',
          accessUrl: 'https://storage.invalid/snapshot.jpg?signature=one',
        },
        {
          id: 2,
          mediaType: 'SNAPSHOT',
          status: 'READY',
          sha256: 'second',
          accessUrl: 'https://storage.invalid/snapshot.jpg?signature=two',
        },
      ],
    } as AiVideoEventApi.Event;
    expect(originalSnapshotAvailable(value)).toBe(false);
    value.media![1]!.accessUrl =
      'https://storage.invalid/second-snapshot.jpg?signature=two';
    expect(originalSnapshotAvailable(value)).toBe(true);
  });
});
