import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoTaskApi {
  export interface Task {
    gatewayRevision?: number;
    gatewayConfiguration?: Record<string, unknown>;
    activeRunId?: string;
    actualStatus: string;
    algorithmId: number;
    cameraId: number;
    code: string;
    configVersion: number;
    createTime?: string;
    desiredStatus: string;
    diagnosticId?: string;
    errorCode?: string;
    errorMessage?: string;
    id: number;
    lastHeartbeatTime?: string;
    metricsSnapshot?: Record<string, number | string>;
    modelVersionId: number;
    modelBindings: Record<string, number>;
    name: string;
    nodeId: number;
    parameters: Record<string, unknown>;
    pipelineVersionId: number;
    ruleId?: number;
    ruleVersionId?: number;
    updateTime?: string;
  }

  export interface TaskPageParams extends PageParam {
    actualStatus?: string;
    algorithmId?: number;
    cameraId?: number;
    name?: string;
    nodeId?: number;
  }

  export interface TaskRun {
    commandId: string;
    configVersion: number;
    createTime: string;
    diagnosticId?: string;
    errorCode?: string;
    errorMessage?: string;
    finishTime?: string;
    id: number;
    metricsSnapshot?: Record<string, number | string>;
    runId: string;
    startTime?: string;
    status: string;
    taskId: number;
  }

  export type TaskConfiguration = Omit<TaskSave, 'cameraId' | 'code' | 'id' | 'name'>;

  export interface BatchCreate extends TaskConfiguration {
    cameraIds: number[];
    confirmSharedRegions: boolean;
    requestId: string;
  }

  export interface BatchResult {
    cameraId: number;
    taskId?: number;
    status: 'CREATED' | 'FAILED' | 'UNCHANGED';
    actualStatus?: string;
    errorCode?: number;
    message: string;
  }

  export interface TaskSave {
    algorithmId: number;
    cameraId: number;
    code: string;
    id?: number;
    modelVersionId: number;
    modelBindings: Record<string, number>;
    name: string;
    nodeId: number;
    parameters: Record<string, unknown>;
    pipelineVersionId?: number;
    ruleId?: number;
    ruleVersionId?: number;
  }
}

export function getTaskPage(params: AiVideoTaskApi.TaskPageParams) {
  return requestClient.get<{ list: AiVideoTaskApi.Task[]; total: number }>(
    '/ai-video/task/page',
    { params },
  );
}

export function createTask(data: AiVideoTaskApi.TaskSave) {
  return requestClient.post<number>('/ai-video/task/create', data);
}

export function getTask(id: number) {
  return requestClient.get<AiVideoTaskApi.Task>('/ai-video/task/get', { params: { id } });
}

export function updateTaskRule(data: { id: number; ruleId: number; ruleVersionId: number; expectedConfigVersion: number }) {
  return requestClient.put<boolean>('/ai-video/task/update-rule', data);
}

export function startTask(id: number) {
  return requestClient.post<string>(`/ai-video/task/start?id=${id}`);
}

export function stopTask(id: number) {
  return requestClient.post<string>(`/ai-video/task/stop?id=${id}`);
}

export function deleteTask(id: number) {
  return requestClient.delete(`/ai-video/task/delete?id=${id}`);
}

export function getTaskRuns(taskId: number) {
  return requestClient.get<AiVideoTaskApi.TaskRun[]>(
    `/ai-video/task/run/list?taskId=${taskId}`,
  );
}

export function batchCreateTasks(data: AiVideoTaskApi.BatchCreate) {
  return requestClient.post<AiVideoTaskApi.BatchResult[]>('/ai-video/task/batch-create', data, { timeout: 120_000 });
}
