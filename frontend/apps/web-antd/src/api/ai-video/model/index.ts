import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoModelApi {
  export interface ModelCapability {
    acceptanceStatus: string;
    algorithmId: number;
    capabilityKey: string;
    code: string;
    name: string;
    sceneGroup: string;
  }

  export interface Model {
    artifactFormat?: string;
    artifactSize?: number;
    code: string;
    capabilities: ModelCapability[];
    createTime?: string;
    currentVersionId?: number;
    deployedNodeCount?: number;
    description?: string;
    id?: number;
    latestVersion?: string;
    latestVersionId?: number;
    outputLabels?: string[];
    versionCount?: number;
    licenseSpdx?: string;
    name: string;
    publishStatus?: 'DRAFT' | 'PUBLISHED' | 'SUPERSEDED';
    readyNodeCount?: number;
    sourceType: 'CUSTOM' | 'PRESET';
    status: number;
    validationStatus?: 'REJECTED' | 'VERIFIED';
  }

  export interface ModelPageParams extends PageParam {
    artifactFormat?: string;
    code?: string;
    name?: string;
    publishStatus?: 'DRAFT' | 'PUBLISHED' | 'SUPERSEDED';
    sourceType?: 'CUSTOM' | 'PRESET';
    status?: number;
  }

  export interface ModelPageResult {
    list: Model[];
    total: number;
  }

  export interface ModelVersion {
    artifactFormat: string;
    artifactName: string;
    artifactSize: number;
    createTime?: string;
    id: number;
    licenseSpdx: string;
    modelId: number;
    publishStatus: 'DRAFT' | 'PUBLISHED' | 'SUPERSEDED';
    runtimeManifest?: string;
    publishedTime?: string;
    executionReadyTime?: string;
    executionStatus: 'NOT_READY' | 'READY';
    sha256: string;
    sourceRepository?: string;
    sourceRevision?: string;
    validationStatus: 'REJECTED' | 'VERIFIED';
    version: string;
  }

  export interface VersionUpload {
    file: File;
    licenseSpdx: string;
    modelId: number;
    runtimeManifest: string;
    sourceRepository?: string;
    sourceRevision?: string;
    version: string;
  }

  export interface ModelDeployment {
    modelName?: string;
    modelVersion?: string;
    actualStatus: string;
    backend?: string;
    commandId: string;
    configVersion: number;
    device?: string;
    diagnosticId?: string;
    errorCode?: string;
    errorMessage?: string;
    id: number;
    modelVersionId: number;
    nodeId: number;
    readyTime?: string;
  }

  export interface ModelTest {
    backend?: string;
    commandId: string;
    createTime: string;
    diagnosticId?: string;
    errorCode?: string;
    errorMessage?: string;
    id: number;
    imageName: string;
    inferenceMillis?: number;
    modelVersionId: number;
    nodeId: number;
    parameters: string;
    postprocessMillis?: number;
    preprocessMillis?: number;
    result?: string;
    status: 'FAILED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED';
  }
}

export function getModelPage(params: AiVideoModelApi.ModelPageParams) {
  return requestClient.get<AiVideoModelApi.ModelPageResult>(
    '/ai-video/model/page',
    { params },
  );
}

export function getModel(id: number) {
  return requestClient.get<AiVideoModelApi.Model>(
    `/ai-video/model/get?id=${id}`,
  );
}

export function createModel(data: AiVideoModelApi.Model) {
  return requestClient.post('/ai-video/model/create', data);
}

export function updateModel(data: AiVideoModelApi.Model) {
  return requestClient.put('/ai-video/model/update', data);
}

export function deleteModel(id: number) {
  return requestClient.delete(`/ai-video/model/delete?id=${id}`);
}

export function getModelVersionList(modelId: number) {
  return requestClient.get<AiVideoModelApi.ModelVersion[]>(
    `/ai-video/model/version/list?modelId=${modelId}`,
  );
}

export function uploadModelVersion(data: AiVideoModelApi.VersionUpload) {
  return requestClient.upload('/ai-video/model/version/upload', data);
}

export function publishModelVersion(id: number) {
  return requestClient.post(`/ai-video/model/version/publish?id=${id}`);
}

export function deployModelVersion(modelVersionId: number, nodeId: number) {
  return requestClient.post<number>('/ai-video/model/deployment/create', {
    modelVersionId,
    nodeId,
  });
}

export function getModelDeployments(modelVersionId: number) {
  return requestClient.get<AiVideoModelApi.ModelDeployment[]>(
    `/ai-video/model/deployment/list?modelVersionId=${modelVersionId}`,
  );
}

export function createModelTest(data: {
  confidence: number;
  image: File;
  inputHeight: number;
  inputWidth: number;
  modelVersionId: number;
  nmsThreshold: number;
  nodeId: number;
}) {
  const { image, ...parameters } = data;
  return requestClient.upload<number>('/ai-video/model/test/create', {
    ...parameters,
    file: image,
  });
}

export function getModelTest(id: number) {
  return requestClient.get<AiVideoModelApi.ModelTest>(
    `/ai-video/model/test/get?id=${id}`,
  );
}

export function getModelTests(modelVersionId: number) {
  return requestClient.get<AiVideoModelApi.ModelTest[]>(
    `/ai-video/model/test/list?modelVersionId=${modelVersionId}`,
  );
}

export function getNodeModelDeployments(nodeId: number) {
  return requestClient.get<AiVideoModelApi.ModelDeployment[]>('/ai-video/model/deployment/node-list', { params: { nodeId } });
}
export function uninstallModelVersion(modelVersionId: number, nodeId: number) {
  return requestClient.post<number>('/ai-video/model/deployment/uninstall', { modelVersionId, nodeId });
}
