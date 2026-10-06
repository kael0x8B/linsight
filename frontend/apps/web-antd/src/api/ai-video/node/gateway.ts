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
  streamUrls?: Partial<Record<'MAIN' | 'SUB', string>>;
  displayNames?: GatewayDisplayNames;
}
export interface GatewayDisplayNames {
  algorithm?: string;
  camera?: string;
  task?: string;
}
export interface GatewayTask {
  availableStreamTypes?: Array<'MAIN' | 'SUB'>;
  displayNames?: GatewayDisplayNames;
  resourceOptions?: Record<string, { label: string; value: number }[]>;
  platformManaged?: boolean;
  name: string;
  revision: number;
  appliedRevision: number;
  enabled: boolean;
  config: GatewayConfig;
  status: {
    errorMessage?: string;
    metrics: Record<string, unknown>;
    runId?: string;
    status: string;
  };
}
export interface GatewayCapacityPreflight {
  schemaVersion: '1.0';
  allowed: boolean;
  code?: null | string;
  message: string;
  taskId: number;
  slotLimit: number;
  currentSlotCount: number;
  projectedSlotCount: number;
  sharedModelCount: number;
  currentMemoryBudgetBytes: number;
  projectedMemoryBudgetBytes: number;
  memoryTotalBytes: number;
  memoryAvailableBytes: number;
  memoryAvailableAfterBytes: number;
  memorySafetyReserveBytes: number;
  memoryBudgetBasis: 'VERIFIED_ARTIFACT_X2_MIN_64_MIB';
  conflictTasks: { modelVersionIds: number[]; name: string; taskId: number }[];
  models: {
    artifactBytes: number;
    memoryBudgetBytes: number;
    modelVersionId: number;
    requested: boolean;
    shared: boolean;
    taskIds: number[];
  }[];
}
export interface GatewaySnapshot {
  capabilities?: string[];
  names?: {
    algorithms?: Record<string, string>;
    cameras: Record<string, string>;
    models: Record<string, { name: string; version: string }>;
    tasks: Record<string, string>;
  };
  tasks: GatewayTask[];
  models: {
    artifactFormat: string;
    device: string;
    displayName?: string;
    modelVersionId: number;
    runtimeManifest?: {
      decoder?: { labels?: string[]; type?: string };
      taskType?: string;
    };
    sha256: string;
    version?: string;
  }[];
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
export interface GatewayEventStreamStatus {
  clients: number;
  enabled: boolean;
  host: string;
  key?: null | string;
  imageHttpEnabled: boolean;
  imageHttpPort: number;
  listening: boolean;
  port: number;
  revision: number;
}
export interface GatewayOverlay {
  imageBase64?: string;
  timestamp: string;
  sourceWidth: number;
  sourceHeight: number;
  objects: {
    attributes?: Record<string, boolean | null | number | string>;
    bbox: { height: number; width: number; x: number; y: number };
    class: string;
    confidence: number;
  }[];
}
export interface PlatformConnection {
  platformUrl: string;
  source: 'DEPLOYMENT' | 'LOCAL_OVERRIDE';
  updatedAt?: null | string;
}
export interface GatewayImageResult extends GatewayOverlay {
  schemaVersion: '1.0';
  taskId: number;
  cameraId: number;
  frameId: string;
  diagnosticId: string;
  revision: number;
  backend: string;
  device: string;
  preprocessMillis: number;
  inferenceMillis: number;
  postprocessMillis: number;
  totalMillis: number;
  observationValid: boolean;
}
export interface PlatformConnectionProbe {
  checkedAt: string;
  httpStatus?: null | number;
  latencyMs: number;
  message: string;
  platformUrl: string;
  reachable: boolean;
}
export interface PlatformConnectionSave extends PlatformConnection {
  probe: PlatformConnectionProbe;
}
export type GatewayTransport = <T>(
  action: string,
  payload?: Record<string, unknown>,
) => Promise<T>;

export async function localGateway<T>(
  action: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const response = await fetch('/gateway-api/rpc', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action, payload }),
  });
  if (response.status === 401) {
    window.dispatchEvent(new Event('gateway-session-expired'));
    throw new Error($t('ai-video-gateway.mf3b638c155'));
  }
  const result = await response.json();
  if (!response.ok || !result.ok)
    throw new Error(
      gatewayErrorMessage(result, $t('ai-video-gateway.m78b96d93c7')),
    );
  return result.data as T;
}

async function localConnectionRequest<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(path, init);
  const result = await response.json();
  if (response.status === 401) {
    window.dispatchEvent(new Event('gateway-session-expired'));
    throw new Error($t('ai-video-gateway.mf3b638c155'));
  }
  if (!response.ok)
    throw new Error(result.detail || $t('ai-video-gateway.m78b96d93c7'));
  return result as T;
}

export function getLocalPlatformConnection() {
  return localConnectionRequest<PlatformConnection>(
    '/gateway-api/platform-connection',
  );
}

export function testLocalPlatformConnection(platformUrl: string) {
  return localConnectionRequest<PlatformConnectionProbe>(
    '/gateway-api/platform-connection/test',
    {
      body: JSON.stringify({ platformUrl }),
      headers: { 'Content-Type': 'application/json' },
      method: 'POST',
    },
  );
}

export function saveLocalPlatformConnection(platformUrl: string) {
  return localConnectionRequest<PlatformConnectionSave>(
    '/gateway-api/platform-connection',
    {
      body: JSON.stringify({ platformUrl }),
      headers: { 'Content-Type': 'application/json' },
      method: 'PUT',
    },
  );
}

export async function platformGateway<T>(
  nodeId: number,
  action: string,
  payload: Record<string, unknown> = {},
): Promise<T> {
  const { requestClient } = await import('#/api/request');
  let operation = 'query';
  if (action.startsWith('app-upgrade.')) operation = 'application-upgrade';
  else if (action.startsWith('preview.')) operation = 'preview';
  else if (action.startsWith('validation.')) operation = 'image-validation';
  else if (action === 'task.recognize-image') operation = 'image-test';
  else if (action === 'model.uninstall') operation = 'model-update';
  else if (
    ['access.password', 'event-stream.configure', 'task.save'].includes(action)
  )
    operation = 'update';
  const result = await requestClient.post<{
    data: T;
    diagnosticId?: string;
    message?: string;
    ok: boolean;
  }>(
    `/ai-video/node/gateway/${operation}`,
    { nodeId, action, payload },
    { timeout: 180_000 },
  );
  if (!result.ok)
    throw new Error(
      gatewayErrorMessage(result, $t('ai-video-gateway.m0941db964d')),
    );
  return result.data;
}

function gatewayErrorMessage(
  result: { detail?: string; diagnosticId?: string; message?: string },
  fallback: string,
) {
  const message = result.message || result.detail || fallback;
  return result.diagnosticId ? `${message} (${result.diagnosticId})` : message;
}

/** LAN HTTP origins do not expose crypto.randomUUID, but getRandomValues is available. */
export function gatewayRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 15) | 64;
  bytes[8] = ((bytes[8] ?? 0) & 63) | 128;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export async function checkLocalGatewaySession() {
  const response = await fetch('/gateway-api/session');
  if (response.status === 401) return false;
  if (!response.ok) throw new Error($t('ai-video-gateway.sessionUnavailable'));
  return true;
}

export async function loginLocalGateway(password: string) {
  const response = await fetch('/gateway-api/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ password }),
  });
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      typeof result.detail === 'string'
        ? result.detail
        : $t('ai-video-gateway.maeb6c8a818'),
    );
}

export async function logoutLocalGateway() {
  const response = await fetch('/gateway-api/logout', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: '{}',
  });
  if (!response.ok && response.status !== 401)
    throw new Error($t('ai-video-gateway.logoutFailed'));
}
