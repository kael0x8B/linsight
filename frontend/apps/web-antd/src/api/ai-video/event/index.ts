import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoEventApi {
  export interface EventMedia {
    accessUrl?: string;
    originalContentAvailable?: boolean;
    captureEndTime?: number | string;
    captureStartTime?: number | string;
    fileName: string;
    fileSize: number;
    id: number;
    mediaType: 'SNAPSHOT' | 'VIDEO';
    mimeType: string;
    sha256: string;
    status: string;
  }

  export interface EventAction {
    actionType: string;
    assigneeId?: number;
    createTime: number | string;
    fromStatus?: string;
    id: number;
    operatorId?: number;
    reasonCode?: string;
    remark?: string;
    toStatus: string;
  }

  export interface Event {
    actions?: EventAction[];
    algorithmId: number;
    assigneeId?: number;
    cameraId: number;
    cameraName?: string;
    taskName?: string;
    closeTime?: number | string;
    createTime: number | string;
    durationMs: number;
    eventNo: string;
    eventType: string;
    evidenceStatus: string;
    falsePositiveReason?: string;
    firstSeenTime: number | string;
    handlingResult?: string;
    id: number;
    lastSeenTime: number | string;
    maxConfidence?: number;
    media?: EventMedia[];
    modelSnapshot?: Record<string, unknown>;
    modelVersionId: number;
    nodeId: number;
    objectSnapshot?: Record<string, unknown>;
    occurredTime: number | string;
    pipelineSnapshot?: Record<string, unknown>;
    pipelineVersionId: number;
    ruleId: number;
    ruleSnapshot?: Record<string, unknown>;
    ruleVersionId: number;
    severity: string;
    sourceEventId: string;
    status: string;
    taskId: number;
    taskRunId: string;
    taskSnapshot?: Record<string, unknown>;
    trackId?: string;
    updateTime: number | string;
  }

  export interface EventPageParams extends PageParam {
    algorithmId?: number;
    cameraId?: number;
    eventNo?: string;
    eventType?: string;
    severity?: string;
    status?: string;
    taskId?: number;
  }

  export interface EventActionRequest {
    assigneeId?: number;
    reasonCode?: string;
    remark?: string;
  }
}

export function getEventPage(params: AiVideoEventApi.EventPageParams) {
  return requestClient.get<{ list: AiVideoEventApi.Event[]; total: number }>(
    '/ai-video/event/page',
    { params },
  );
}

export function getEvent(id: number) {
  return requestClient.get<AiVideoEventApi.Event>('/ai-video/event/get', {
    params: { id },
  });
}

export function assignEvent(
  id: number,
  data: AiVideoEventApi.EventActionRequest,
) {
  return requestClient.post<boolean>(`/ai-video/event/assign?id=${id}`, data);
}

export function handleEvent(
  id: number,
  data: AiVideoEventApi.EventActionRequest,
) {
  return requestClient.post<boolean>(`/ai-video/event/handle?id=${id}`, data);
}

export function closeEvent(
  id: number,
  data: AiVideoEventApi.EventActionRequest,
) {
  return requestClient.post<boolean>(`/ai-video/event/close?id=${id}`, data);
}

export function markEventFalsePositive(
  id: number,
  data: AiVideoEventApi.EventActionRequest,
) {
  return requestClient.post<boolean>(
    `/ai-video/event/false-positive?id=${id}`,
    data,
  );
}
