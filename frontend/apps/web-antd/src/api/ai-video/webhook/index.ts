import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoWebhookApi {
  export interface Endpoint {
    createTime: string;
    eventTypes: string[];
    failureCount: number;
    id: number;
    lastError?: string;
    lastFailureTime?: string;
    lastSuccessTime?: string;
    maxAttempts: number;
    name: string;
    secretMasked: string;
    severities: string[];
    status: number;
    successCount: number;
    successRate?: number;
    timeoutMs: number;
    url: string;
  }

  export interface SaveEndpoint {
    eventTypes?: string[];
    id?: number;
    maxAttempts: number;
    name: string;
    secret?: string;
    severities?: string[];
    status: number;
    timeoutMs: number;
    url: string;
  }

  export interface Delivery {
    attempts: number;
    createTime: string;
    durationMs?: number;
    endpointId: number;
    eventId?: number;
    eventType: string;
    id: number;
    idempotencyKey: string;
    isTest: boolean;
    lastAttemptTime?: string;
    lastError?: string;
    messageId: string;
    nextAttemptTime: string;
    payload: string;
    responseBody?: string;
    responseStatus?: number;
    severity?: string;
    status: 'DEAD' | 'PENDING' | 'RETRY' | 'SUCCEEDED';
  }

  export interface EndpointPageParams extends PageParam {
    name?: string;
    status?: number;
  }

  export interface DeliveryPageParams extends PageParam {
    endpointId?: number;
    isTest?: boolean;
    status?: string;
  }
}

export function getWebhookPage(params: AiVideoWebhookApi.EndpointPageParams) {
  return requestClient.get<PageResult<AiVideoWebhookApi.Endpoint>>(
    '/ai-video/webhook/page',
    { params },
  );
}

export function getWebhook(id: number) {
  return requestClient.get<AiVideoWebhookApi.Endpoint>(
    '/ai-video/webhook/get',
    {
      params: { id },
    },
  );
}

export function createWebhook(data: AiVideoWebhookApi.SaveEndpoint) {
  return requestClient.post<{ id: number; secret: string }>(
    '/ai-video/webhook/create',
    data,
  );
}

export function updateWebhook(data: AiVideoWebhookApi.SaveEndpoint) {
  return requestClient.put('/ai-video/webhook/update', data);
}

export function deleteWebhook(id: number) {
  return requestClient.delete('/ai-video/webhook/delete', { params: { id } });
}

export function updateWebhookStatus(id: number, status: number) {
  return requestClient.put('/ai-video/webhook/update-status', undefined, {
    params: { id, status },
  });
}

export function testWebhook(id: number) {
  return requestClient.post<number>('/ai-video/webhook/test', undefined, {
    params: { id },
  });
}

export function getWebhookDeliveryPage(
  params: AiVideoWebhookApi.DeliveryPageParams,
) {
  return requestClient.get<PageResult<AiVideoWebhookApi.Delivery>>(
    '/ai-video/webhook/delivery/page',
    { params },
  );
}

export function getWebhookDelivery(id: number) {
  return requestClient.get<AiVideoWebhookApi.Delivery>(
    '/ai-video/webhook/delivery/get',
    { params: { id } },
  );
}

export function replayWebhookDelivery(id: number) {
  return requestClient.post('/ai-video/webhook/delivery/replay', undefined, {
    params: { id },
  });
}
