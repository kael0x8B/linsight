import { requestClient } from '#/api/request';

export interface AiVideoNodeSimple {
  agentVersion: string;
  code: string;
  id: number;
  name: string;
  onlineStatus: number;
  previewTunnelConnected: boolean;
  status: number;
}

export interface AiVideoNode extends AiVideoNodeSimple {
  taskCount?: number;
  modelCount?: number;
  clockOffsetMillis?: number;
  hostName?: string;
  ipAddress?: string;
  lastHeartbeatTime?: string;
  resourceSnapshot?: string;
}

export interface AiVideoNodeBootstrapToken {
  expireTime: string;
  token: string;
}

export interface AiVideoNodeUpgrade {
  action: 'ROLLBACK' | 'UPGRADE';
  commandId: string;
  configVersion: number;
  createTime: string;
  diagnosticId?: string;
  errorCode?: string;
  errorMessage?: string;
  finishTime?: string;
  id: number;
  nodeId: number;
  packageName?: string;
  resultSummary?: string;
  sha256?: string;
  stage?: string;
  status: 'AWAITING_ACTIVATION' | 'EXPIRED' | 'FAILED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED' | 'VERIFYING';
  targetVersion?: string;
}

export interface AiVideoNodeDeploymentPreflight {
  architecture: string;
  diskAvailableMb: number;
  executionMode: string;
  existingNodeCode?: string;
  existingNodeId?: number;
  existingNodeName?: string;
  ffmpegInstalled: boolean;
  hostKey: string;
  hostKeyFingerprint: string;
  hostKeyType: string;
  memoryMb: number;
  osSummary: string;
  pythonSupported: boolean;
  venvAvailable?: boolean;
  offlineDependenciesAvailable?: boolean;
  pythonVersion: string;
  rknpuAvailable: boolean;
  sudoAvailable: boolean;
  supported: boolean;
  warnings: string[];
  memoryAvailableMb?: number;
  controlPlaneUrl?: string;
  currentVersion?: string;
  previousVersion?: string;
  sourceRollbackAvailable?: boolean;
}

export interface AiVideoNodeDeployment {
  targetVersion?: string;
  previousVersion?: string;
  createTime: string;
  diagnosticId?: string;
  edgeNodeId?: number;
  finishTime?: string;
  host: string;
  id: number;
  message?: string;
  nodeCode: string;
  nodeName: string;
  operationType: 'INITIAL' | 'REDEPLOY' | 'ROLLBACK';
  osSummary?: string;
  outputLog?: string;
  logStatus?: string;
  logTruncated?: boolean;
  port: number;
  progress: number;
  pythonVersion?: string;
  runtimePackageSha256?: string;
  stage: string;
  status: 'FAILED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED';
  targetArch?: string;
  updateTime: string;
  username: string;
}

export interface AiVideoNodeDeploymentConnection {
  nodeId?: number;
  host: string;
  password: string;
  port: number;
  username: string;
}

export interface AiVideoNodeDeploymentCreate
  extends AiVideoNodeDeploymentConnection {
  controlPlaneUrl: string;
  hostKey: string;
  hostKeyFingerprint: string;
  hostKeyType: string;
  installDependencies: boolean;
  nodeCode: string;
  nodeName: string;
  requestId?: string;
  action?: 'DEPLOY' | 'ROLLBACK';
}

export function getNodeSimpleList() {
  return requestClient.get<AiVideoNodeSimple[]>('/ai-video/node/simple-list');
}

export function getNodeList(silent = false) {
  return requestClient.get<AiVideoNode[]>('/ai-video/node/list', { headers: { 'x-silent-error': String(silent) } });
}

export function createNodeBootstrapToken(data: {
  name: string;
  ttlMinutes: number;
}) {
  return requestClient.post<AiVideoNodeBootstrapToken>(
    '/ai-video/node/create-bootstrap-token',
    data,
  );
}

export function upgradeNode(data: {
  file: File;
  nodeId: number;
  signature: string;
  targetVersion: string;
}) {
  return requestClient.upload<number>('/ai-video/node/upgrade', data);
}

export function rollbackNode(nodeId: number) {
  return requestClient.post<number>(`/ai-video/node/rollback?nodeId=${nodeId}`);
}

export function getNodeUpgradeList(nodeId: number) {
  return requestClient.get<AiVideoNodeUpgrade[]>(
    `/ai-video/node/upgrade/list?nodeId=${nodeId}`,
    { headers: { 'x-silent-error': 'true' } },
  );
}

export function preflightNodeDeployment(
  data: AiVideoNodeDeploymentConnection,
) {
  return requestClient.post<AiVideoNodeDeploymentPreflight>(
    '/ai-video/node/deployment/preflight',
    data,
    { timeout: 70_000 },
  );
}

export function createNodeDeployment(data: AiVideoNodeDeploymentCreate) {
  return requestClient.post<number>('/ai-video/node/deployment/create', data, { timeout: 90_000 });
}

export function getNodeDeployment(id: number) {
  return requestClient.get<AiVideoNodeDeployment>(
    `/ai-video/node/deployment/get?id=${id}`,
    { headers: { 'x-silent-error': 'true' } },
  );
}

export function restartNode(nodeId: number) {
  return requestClient.post<string>(`/ai-video/node/restart?nodeId=${nodeId}`);
}

export function shutdownNode(nodeId: number) {
  return requestClient.post<string>(`/ai-video/node/shutdown?nodeId=${nodeId}`);
}

export function deleteNode(id: number) {
  return requestClient.delete<boolean>(`/ai-video/node/delete?id=${id}`);
}

export function getNodeDeploymentList() {
  return requestClient.get<AiVideoNodeDeployment[]>(
    '/ai-video/node/deployment/list',
  );
}
export function getNodeDeploymentPage(params: { nodeId?: number; pageNo: number; pageSize: number }) {
  return requestClient.get<{ list: AiVideoNodeDeployment[]; total: number }>('/ai-video/node/deployment/page', { params });
}

export interface AiVideoNodeCommand {
  commandId: string;
  commandType: string;
  status: string;
  createTime: string;
  finishTime?: string;
  resultSummary?: string;
  errorMessage?: string;
}

export function getNodeCommandList(nodeId: number) {
  return requestClient.get<AiVideoNodeCommand[]>(`/ai-video/node/command/list?nodeId=${nodeId}`, { headers: { 'x-silent-error': 'true' } });
}
