import { requestClient } from '#/api/request';

export namespace AiVideoCameraApi {
  export interface CameraGroup {
    id?: number;
    name: string;
    parentId: number;
    path?: string;
    sort: number;
    status: number;
    createTime?: string;
    children?: CameraGroup[];
  }

  export interface Camera {
    recognitionCapabilities?: CameraCapability[];
    id?: number;
    name: string;
    code: string;
    groupId: number;
    protocol: 'ONVIF' | 'RTSP';
    host: string;
    port: number;
    mainStreamUri?: string;
    subStreamUri?: string;
    username?: string;
    password?: string;
    maskedStreamEndpoint?: string;
    credentialConfigured?: boolean;
    onlineStatus?: number;
    lastOnlineTime?: string;
    lastCheckTime?: string;
    lastErrorCode?: string;
    lastErrorMessage?: string;
    status: number;
    version?: number;
    createTime?: string;
  }

  export interface CameraCapability {
    taskId?: null | number;
    errorCode?: null | string;
    errorMessage?: null | string;
    entryAccessId?: null | number;
    stationState?: string;
    taskName: string;
    algorithmId?: null | number;
    algorithmName?: string;
    capabilityKey?: string;
    nodeId: number;
    nodeName?: string;
    actualStatus: string;
    desiredStatus: string;
    effectiveStatus: string;
    activeRunId?: string;
    lastHeartbeatTime?: number | string;
    validationOnly: boolean;
    sampleFps?: number;
    executionBackend?: string;
    analysisFps?: number;
    totalLatencyMillis?: number;
  }

  export interface CameraPageParams {
    ids?: number[];
    pageNo: number;
    pageSize: number;
    name?: string;
    code?: string;
    groupId?: number;
    protocol?: 'ONVIF' | 'RTSP';
    onlineStatus?: number;
    status?: number;
  }

  export interface CameraPageResult {
    list: Camera[];
    total: number;
  }

  export interface PreviewSession {
    cameraId: number;
    nodeId: number;
    diagnosticId: string;
    answerSdp?: string;
    answerType?: 'answer';
    manifestUrl?: string;
    overlayMessageType: string;
    protocol: 'HLS' | 'WEBRTC';
    sessionId: string;
    state: 'CLOSED' | 'CONNECTING' | 'FAILED' | 'READY' | 'RECONNECTING' | 'STARTING';
    subscriberCount: number;
  }

  export interface OverlayBoundingBox {
    height: number;
    width: number;
    x: number;
    y: number;
  }

  export interface OverlayObject {
    attributes: Record<string, boolean | null | number | string>;
    bbox: OverlayBoundingBox;
    class: string;
    confidence: number;
    trackId?: string;
  }

  export interface OverlayFrame {
    nodeId?: number;
    frameKey?: string;
    streamId?: string;
    sourcePts?: number;
    taskId?: number;
    runId?: string;
    imageBase64?: string;
    cameraId: number;
    frameId: string;
    objects: OverlayObject[];
    sessionId: string;
    sourceHeight: number;
    sourceWidth: number;
    timestamp: number | string;
  }

  export interface OverlayEnvelope {
    data: OverlayFrame;
    messageId: string;
    occurredAt: string;
    traceId?: string;
    type: 'preview.overlay.frame';
    version: '1.0';
  }

  export interface VideoWallLayout {
    id: number;
    slotIndex: number;
    name: string;
    splitCount: 1 | 4 | 9 | 16;
    schemaVersion: '1.0' | '1.1' | '1.2';
    nodeId?: number;
    cameraIds: Array<null | number>;
    active: boolean;
    updateTime?: string;
  }

  export interface VideoWallLayoutSave {
    id?: number;
    slotIndex: number;
    name: string;
    splitCount: 1 | 4 | 9 | 16;
    nodeId?: number;
    cameraIds: Array<null | number>;
  }
}

export function getCameraGroupList(params?: {
  name?: string;
  status?: number;
}) {
  return requestClient.get<AiVideoCameraApi.CameraGroup[]>(
    '/ai-video/camera/group/list',
    { params },
  );
}

export function getCameraGroup(id: number) {
  return requestClient.get<AiVideoCameraApi.CameraGroup>(
    `/ai-video/camera/group/get?id=${id}`,
  );
}

export function createCameraGroup(data: AiVideoCameraApi.CameraGroup) {
  return requestClient.post('/ai-video/camera/group/create', data);
}

export function updateCameraGroup(data: AiVideoCameraApi.CameraGroup) {
  return requestClient.put('/ai-video/camera/group/update', data);
}

export function deleteCameraGroup(id: number) {
  return requestClient.delete(`/ai-video/camera/group/delete?id=${id}`);
}

export function getCameraPage(params: AiVideoCameraApi.CameraPageParams) {
  return requestClient.get<AiVideoCameraApi.CameraPageResult>(
    '/ai-video/camera/page',
    { params },
  );
}

export function getCamera(id: number) {
  return requestClient.get<AiVideoCameraApi.Camera>(
    `/ai-video/camera/get?id=${id}`,
  );
}

export function createCamera(data: AiVideoCameraApi.Camera) {
  return requestClient.post('/ai-video/camera/create', data);
}

export function updateCamera(data: AiVideoCameraApi.Camera) {
  return requestClient.put('/ai-video/camera/update', data);
}

export function deleteCamera(id: number) {
  return requestClient.delete(`/ai-video/camera/delete?id=${id}`);
}

export function createPreviewSession(data: {
  cameraId: number;
  nodeId: number;
  streamType: 'MAIN' | 'SUB';
}) {
  return requestClient.post<AiVideoCameraApi.PreviewSession>(
    '/ai-video/camera/preview/create',
    data,
  );
}

export function createWebRtcPreviewSession(data: {
  cameraId: number;
  nodeId: number;
  offerSdp: string;
  offerType: 'offer';
}) {
  return requestClient.post<AiVideoCameraApi.PreviewSession>(
    '/ai-video/camera/preview/webrtc/offer',
    data,
  );
}

export function getPreviewSession(sessionId: string) {
  return requestClient.get<AiVideoCameraApi.PreviewSession>(
    `/ai-video/camera/preview/get?sessionId=${encodeURIComponent(sessionId)}`,
    { headers: { 'x-silent-error': 'true' } },
  );
}

export function releasePreviewSession(sessionId: string) {
  return requestClient.delete(
    `/ai-video/camera/preview/delete?sessionId=${encodeURIComponent(sessionId)}`,
    { headers: { 'x-silent-error': 'true' } },
  );
}

export function getVideoWallLayouts() {
  return requestClient.get<AiVideoCameraApi.VideoWallLayout[]>(
    '/ai-video/camera/wall-layout/list',
  );
}

export function createVideoWallLayout(
  data: AiVideoCameraApi.VideoWallLayoutSave,
) {
  return requestClient.post<number>('/ai-video/camera/wall-layout/create', data);
}

export function updateVideoWallLayout(
  data: AiVideoCameraApi.VideoWallLayoutSave,
) {
  return requestClient.put('/ai-video/camera/wall-layout/update', data);
}

export function activateVideoWallLayout(id: number) {
  return requestClient.put(
    `/ai-video/camera/wall-layout/activate?id=${id}`,
  );
}

export function deleteVideoWallLayout(id: number) {
  return requestClient.delete(
    `/ai-video/camera/wall-layout/delete?id=${id}`,
  );
}
