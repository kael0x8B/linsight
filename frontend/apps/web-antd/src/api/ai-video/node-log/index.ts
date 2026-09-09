import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoNodeLogApi {
  export interface Log {
    component: string;
    contextJson?: string;
    diagnosticId?: string;
    id: number;
    level: 'DEBUG' | 'ERROR' | 'INFO' | 'WARN';
    loggedAt: string;
    message: string;
    nodeId: number;
    runId?: string;
    taskId?: number;
  }

  export interface Diagnostic {
    accessUrl?: string;
    createTime: string;
    errorMessage?: string;
    expiresAt: string;
    fileName?: string;
    id: number;
    logCount: number;
    nodeId: number;
    rangeEnd: string;
    rangeStart: string;
    status: 'FAILED' | 'QUEUED' | 'READY' | 'RUNNING';
    taskId?: number;
  }

  export interface LogPageParams extends PageParam {
    afterId?: number;
    snapshotMaxId?: number;
    component?: string;
    diagnosticId?: string;
    keyword?: string;
    level?: string;
    loggedAt?: string[];
    nodeId: number;
    taskId?: number;
  }
}

export function getNodeLogPage(params: AiVideoNodeLogApi.LogPageParams, silent = false) {
  return requestClient.get<PageResult<AiVideoNodeLogApi.Log>>(
    '/ai-video/node-log/page',
    { params, headers: { 'x-silent-error': silent ? 'true' : 'false' } },
  );
}

export function getNodeLogSnapshot(nodeId: number) {
  return requestClient.get<number>('/ai-video/node-log/snapshot', { params: { nodeId } });
}

export function getNodeLogContext(id: number) {
  return requestClient.get<AiVideoNodeLogApi.Log[]>(
    '/ai-video/node-log/context',
    { params: { after: 100, before: 100, id } },
  );
}

export function createNodeDiagnostic(data: {
  nodeId: number;
  rangeEnd: string;
  rangeStart: string;
  taskId?: number;
}) {
  return requestClient.post<number>('/ai-video/node-log/diagnostic/create', data);
}

export function getNodeDiagnostic(id: number) {
  return requestClient.get<AiVideoNodeLogApi.Diagnostic>(
    '/ai-video/node-log/diagnostic/get',
    { params: { id } },
  );
}

export function getNodeDiagnostics(nodeId: number) {
  return requestClient.get<AiVideoNodeLogApi.Diagnostic[]>(
    '/ai-video/node-log/diagnostic/list',
    { params: { nodeId } },
  );
}
