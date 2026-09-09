import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoRuleApi {
  export interface Point {
    x: number;
    y: number;
  }

  export interface Region {
    id: string;
    name: string;
    overlapThreshold: number;
    pointMode: 'CENTROID' | 'FOOT' | 'OVERLAP';
    points: Point[];
    sourceHeight: number;
    sourceWidth: number;
    type: 'POLYGON';
  }

  export interface RuleAst {
    condition: Record<string, unknown>;
    cooldownSeconds: number;
    dedup: { scope: 'CAMERA_TASK_TYPE' | 'TRACK'; windowSeconds: number };
    eventType: string;
    recoverySeconds: number;
    regions: Region[];
    schedule: {
      timezone: string;
      weekly: Array<{ days: number[]; end: string; start: string }>;
    };
    schemaVersion: '1.0';
    severity: 'CRITICAL' | 'INFO' | 'MAJOR' | 'MINOR';
  }

  export interface Rule {
    code: string;
    createTime?: string;
    currentVersionId?: number;
    description?: string;
    eventType: string;
    id: number;
    name: string;
    status: number;
  }

  export interface RuleVersion {
    ast: RuleAst;
    createTime: string;
    id: number;
    naturalSummary?: string;
    publishedTime?: string;
    ruleId: number;
    validationErrors?: string[];
    validationStatus: string;
    version: number;
  }

  export interface RulePageParams extends PageParam {
    eventType?: string;
    name?: string;
    status?: number;
  }

  export interface RuleSave {
    code: string;
    description?: string;
    eventType: string;
    id?: number;
    name: string;
    status: number;
  }

  export interface DryRunResult {
    confirmedAtMillis?: number;
    frames: Array<{
      matchedFrames: number;
      roiMatched: boolean;
      state: string;
      timestampMillis: number;
    }>;
    matched: boolean;
  }
}

export function getRulePage(params: AiVideoRuleApi.RulePageParams) {
  return requestClient.get<{ list: AiVideoRuleApi.Rule[]; total: number }>(
    '/ai-video/rule/page',
    { params },
  );
}

export function getPublishedRules() {
  return requestClient.get<AiVideoRuleApi.Rule[]>('/ai-video/rule/simple-list');
}

export function createRule(data: AiVideoRuleApi.RuleSave) {
  return requestClient.post<number>('/ai-video/rule/create', data);
}

export function getRuleVersions(ruleId: number) {
  return requestClient.get<AiVideoRuleApi.RuleVersion[]>(
    '/ai-video/rule/version/list',
    { params: { ruleId } },
  );
}

export function saveRuleVersion(ruleId: number, ast: AiVideoRuleApi.RuleAst) {
  return requestClient.post<number>('/ai-video/rule/version/save', {
    ast,
    ruleId,
  });
}

export function validateRuleVersion(id: number) {
  return requestClient.post<string[]>(
    `/ai-video/rule/version/validate?id=${id}`,
  );
}

export function publishRuleVersion(id: number) {
  return requestClient.post<boolean>(`/ai-video/rule/version/publish?id=${id}`);
}

export interface RuleDetectionFrame {
  timestampMillis: number;
  objects: Array<{
    class: string;
    trackId?: string;
    confidence?: number;
    bbox: { x: number; y: number; width: number; height: number };
  }>;
}

export function dryRunRule(
  ruleVersionId: number,
  nodeId: number,
  cameraId: number,
  frames: RuleDetectionFrame[],
) {
  return requestClient.post<{
    confirmed: boolean;
    transitions: Array<{
      state: string;
      occurredAtMillis: number;
      trackId?: string;
    }>;
  }>('/ai-video/rule/runtime-dry-run', {
    ruleVersionId,
    nodeId,
    cameraId,
    frames,
  });
}
