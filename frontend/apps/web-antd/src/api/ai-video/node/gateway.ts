
import { $t } from '#/locales';
export interface GatewayConfig {
  taskId: number;
  runId: string;
  cameraId: number;
  algorithmId: number;
  pipelineVersionId: number;
  modelVersionId: number;
  configVersion: number;
  modelBindings: Record<string, number>;
  pipeline: Record<string, unknown>;
  parameters: Record<string, unknown>;
  ruleId?: null | number;
  ruleVersionId?: null | number;
  rule: null | Record<string, unknown>;
  sourceUrl?: string;
}
export interface GatewayTask {
  platformManaged?: boolean;
  name: string;
  revision: number;
  appliedRevision: number;
  enabled: boolean;
  config: GatewayConfig;
  status: { errorMessage?: string; metrics: Record<string, unknown>; runId?: string; status: string; };
}
export interface GatewaySnapshot {
  capabilities?: string[];
  names?: {
    cameras: Record<string, string>;
    models: Record<string, { name: string; version: string }>;
    tasks: Record<string, string>;
  };
  tasks: GatewayTask[];
  models: { artifactFormat: string; device: string; modelVersionId: number; sha256: string }[];
  historyDays: number;
}
export interface GatewayEvent {
  sourceEventId: string;
  payload: Record<string, unknown>;
  delivered: boolean;
  localOnly?: boolean;
  hasSnapshot: boolean;
  hasVideo: boolean;
}
export interface GatewayOverlay {
  imageBase64?: string;
  timestamp: string;
  sourceWidth: number;
  sourceHeight: number;
  objects: { attributes?: Record<string, boolean | null | number | string>; bbox: { height: number; width: number; x: number; y: number; }; class: string; confidence: number; }[];
}
export type GatewayTransport = <T>(action: string, payload?: Record<string, unknown>) => Promise<T>;

export async function localGateway<T>(action: string, payload: Record<string, unknown> = {}): Promise<T> {
  const response = await fetch('/gateway-api/rpc', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  });
  if (response.status === 401) throw new Error($t('ai-video-gateway.mf3b638c155'));
  const result = await response.json();
  if (!response.ok || !result.ok) throw new Error(result.message || result.detail || $t('ai-video-gateway.m78b96d93c7'));
  return result.data as T;
}

export async function platformGateway<T>(nodeId: number, action: string, payload: Record<string, unknown> = {}): Promise<T> {
  const { requestClient } = await import('#/api/request');
  const operation = action.startsWith('preview.') ? 'preview' : action === 'model.uninstall' ? 'model-update' : ['access.password', 'task.save'].includes(action) ? 'update' : 'query';
  const result = await requestClient.post<{ data: T; message?: string; ok: boolean; }>(
    `/ai-video/node/gateway/${operation}`, { nodeId, action, payload }, { timeout: 180_000 },
  );
  if (!result.ok) throw new Error(result.message || $t('ai-video-gateway.m0941db964d'));
  return result.data;
}
