import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoAlgorithmApi {
  export interface Algorithm {
    capabilityKey: string;
    category: 'CORE' | 'CUSTOM' | 'EXTENSION';
    code: string;
    currentPipelineVersionId?: number;
    defaultModelId?: number;
    defaultParameters: Record<string, unknown>;
    description?: string;
    eventType?: string;
    id: number;
    implementationType:
      | 'CLASSICAL_CV'
      | 'COMPOSITE'
      | 'MODEL_DIRECT'
      | 'MODEL_FILTER'
      | 'TRACK_RULE';
    name: string;
    parameterSchema: Record<string, unknown>;
    pipelineAcceptanceStatus: string;
    requiredCapabilities: string[];
    sceneGroup: string;
    status: number;
  }

  export interface AlgorithmPageParams extends PageParam {
    category?: string;
    code?: string;
    implementationType?: string;
    name?: string;
    sceneGroup?: string;
    status?: number;
  }

  export interface PipelineVersion {
    algorithmId: number;
    createTime: string;
    dag: Record<string, unknown>;
    id: number;
    publishedTime?: string;
    validationErrors: string[];
    validationStatus: 'DRAFT' | 'PUBLISHED' | 'VALID';
    version: number;
  }
}

export function getAlgorithmPage(
  params: AiVideoAlgorithmApi.AlgorithmPageParams,
) {
  return requestClient.get<{
    list: AiVideoAlgorithmApi.Algorithm[];
    total: number;
  }>('/ai-video/algorithm/page', { params });
}

export function getRunnableAlgorithms() {
  return requestClient.get<AiVideoAlgorithmApi.Algorithm[]>(
    '/ai-video/algorithm/simple-list',
  );
}

export function createAlgorithm(
  data: Omit<
    AiVideoAlgorithmApi.Algorithm,
    'currentPipelineVersionId' | 'id' | 'pipelineAcceptanceStatus'
  >,
) {
  return requestClient.post<number>('/ai-video/algorithm/create', data);
}

export function updateAlgorithm(
  data: Omit<AiVideoAlgorithmApi.Algorithm, 'pipelineAcceptanceStatus'>,
) {
  return requestClient.put('/ai-video/algorithm/update', data);
}

export function getPipelineVersions(algorithmId: number) {
  return requestClient.get<AiVideoAlgorithmApi.PipelineVersion[]>(
    `/ai-video/algorithm/pipeline/list?algorithmId=${algorithmId}`,
  );
}

export function savePipeline(data: {
  algorithmId: number;
  dag: Record<string, unknown>;
}) {
  return requestClient.post<number>('/ai-video/algorithm/pipeline/save', data);
}

export function validatePipeline(id: number) {
  return requestClient.post<string[]>(
    `/ai-video/algorithm/pipeline/validate?id=${id}`,
  );
}

export function publishPipeline(id: number) {
  return requestClient.post(`/ai-video/algorithm/pipeline/publish?id=${id}`);
}

export function getAlgorithm(id: number) {
  return requestClient.get<AiVideoAlgorithmApi.Algorithm>(
    '/ai-video/algorithm/get',
    { params: { id } },
  );
}
