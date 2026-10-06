import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { requestClient } from '#/api/request';

export interface ParameterField {
  type: 'array' | 'boolean' | 'integer' | 'number' | 'object' | 'string';
  title?: string;
  description?: string;
  enum?: Array<number | string>;
  minimum?: number;
  maximum?: number;
  minItems?: number;
  maxItems?: number;
  default?: unknown;
  'x-widget'?: 'people' | 'person-library' | 'roi';
  'x-library-field'?: string;
  properties?: Record<string, ParameterField>;
}
export interface AlgorithmManifest {
  schemaVersion: string;
  sdkVersion: string;
  outputMode?: 'STATISTICS';
  runtimeRequirements?: string[];
  code: string;
  version: string;
  name: string;
  category?: string;
  eventType?: string;
  description?: string;
  entrypoint: string;
  frameInput?: { detectorSlot: string; ocrSlot: string; type: 'PLATE_OCR' };
  models: Array<{
    decoderTypes?: string[];
    formats?: string[];
    labels?: string[];
    name?: string;
    slot: string;
    taskType?: string;
  }>;
  resources?: Array<{
    key: string;
    modelSlot: string;
    parameter: string;
    selectionParameter?: string;
    type: string;
  }>;
  parameterSchema: {
    properties: Record<string, ParameterField>;
    required?: string[];
    type: string;
  };
  defaultParameters: Record<string, unknown>;
  defaultRule?: AiVideoRuleApi.RuleAst;
}
export interface AlgorithmPackage {
  algorithmId: number;
  pipelineVersionId: number;
  sha256: string;
  manifest: AlgorithmManifest;
  status: string;
  current: boolean;
}
export interface ModelOption {
  id: number;
  modelId: number;
  name: string;
  version: string;
  format: string;
  executionProvider?: string;
  executionTarget?: string;
  executionRuntime?: string;
  minimumRuntimeVersion?: string;
  installed: boolean;
  recommended: boolean;
  deployable?: boolean;
  reason?: string;
}
export interface PackageResolution {
  manifest: AlgorithmManifest;
  bindings: Record<string, number>;
  roles: Record<string, ModelOption[]>;
  supported: boolean;
  blockers?: Record<string, string>;
  environmentReported?: boolean;
}
export const getAlgorithmPackageDownloadUrl = (pipelineVersionId: number) =>
  requestClient.get<string>('/ai-video/algorithm/package/download-url', {
    params: { pipelineVersionId },
  });
export const listAlgorithmPackages = () =>
  requestClient.get<AlgorithmPackage[]>('/ai-video/algorithm/package/list');
export const uploadAlgorithmPackage = (file: File) =>
  requestClient.upload<AlgorithmPackage>('/ai-video/algorithm/package/upload', {
    file,
  });
export const resolveAlgorithmPackage = (
  pipelineVersionId: number,
  nodeId: number,
) =>
  requestClient.get<PackageResolution>('/ai-video/algorithm/package/resolve', {
    params: { pipelineVersionId, nodeId },
  });

export const algorithmCategoryLabels: Record<string, string> = {
  PPE: '穿戴检测',
  IDENTITY: '身份比对',
  BEHAVIOR: '行为分析',
  REGION: '区域分析',
  OCR: '文字与号码',
  SCENE: '场景检测',
  GENERAL: '通用识别',
};
