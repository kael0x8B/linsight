import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { requestClient } from '#/api/request';
export interface EntryAccess {
  id: number;
  name: string;
  cameraId: number;
  nodeId: number;
  libraryId: number;
  modelVersionId: number;
  enabled: boolean;
  version: number;
  similarityThreshold: number;
  ambiguityMargin: number;
  triggerMode: 'FACE_ZONE' | 'MANUAL';
  temporalN: number;
  temporalM: number;
  allowedEntryIds: number[];
  roi: { height: number; width: number; x: number; y: number };
}
export interface FaceReference {
  id: number;
  entryId: number;
  name: string;
  externalCode: string;
  status: string;
  validUntil: string;
  modelVersionId: number;
}
export interface EntryScan {
  id: number;
  entryAccessId?: number;
  mode: string;
  status: string;
  eventId?: number;
  createTime: string;
  result: {
    backend?: string;
    decision?: string;
    device?: string;
    externalCode?: string;
    liveness?: string;
    matchedFrames?: number;
    personName?: string;
    reason?: string;
    sampledFrames?: number;
    similarity?: number;
    status?: string;
  };
}
const base = '/ai-video/task/entry-access';
export const listEntryAccess = (cameraId?: number, nodeId?: number) =>
  requestClient.get<EntryAccess[]>(`${base}/list`, {
    params: { cameraId, nodeId },
  });
export interface EntryStationStatus {
  state: string;
  nodeId?: number;
  entryAccessId?: number;
  cameraId: number;
  version: number;
  roi: AiVideoCameraApi.OverlayBoundingBox;
  latestScan?: EntryScan;
  frame?: Omit<AiVideoCameraApi.OverlayFrame, 'objects' | 'sessionId'> & {
    faces: (AiVideoCameraApi.OverlayBoundingBox & {
      confidence: number;
      trackId?: string;
    })[];
  };
}
export const getEntryStationStatus = (id: number, nodeId?: number) =>
  requestClient.get<EntryStationStatus>(`${base}/station-status`, {
    params: { id, nodeId },
  });
export const saveEntryAccess = (data: Record<string, unknown>) =>
  requestClient.post<number>(`${base}/save`, data);
export const stopEntryAccess = (id: number, nodeId?: number) =>
  requestClient.post(`${base}/stop`, null, { params: { id, nodeId } });
export const deleteEntryAccess = (id: number, nodeId?: number) =>
  requestClient.delete(`${base}/delete`, { params: { id, nodeId } });
export const enrollEntryFace = (
  data: Record<string, unknown> & { file: File },
) => requestClient.upload<number>(`${base}/enroll`, data);
export const getExtractionStatus = (id: number) =>
  requestClient.get<EntryScan>(`${base}/extraction-status`, { params: { id } });
export const extractEntryFace = (data: Record<string, unknown>) =>
  requestClient.post<number>(`${base}/extract`, {
    ...data,
    validUntil: new Date(String(data.validUntil)).getTime(),
  });
export const startEntryScan = (entryAccessId: number) =>
  requestClient.post<number>(`${base}/start`, {
    entryAccessId,
    consentConfirmed: true,
  });
export const cancelEntryScan = (id: number) =>
  requestClient.post(`${base}/cancel`, null, { params: { id } });
export const getEntryScan = (id: number) =>
  requestClient.get<EntryScan>(`${base}/get`, { params: { id } });
export const entryScanHistory = () =>
  requestClient.get<EntryScan[]>(`${base}/history`);
export const listFaceReferences = (libraryId: number) =>
  requestClient.get<FaceReference[]>(
    '/ai-video/algorithm/face-reference/list',
    { params: { libraryId } },
  );
export const revokeFaceReference = (id: number) =>
  requestClient.post('/ai-video/algorithm/face-reference/revoke', null, {
    params: { id },
  });

export const enableEntryAccess = (id: number, nodeId?: number) =>
  requestClient.post(`${base}/enable`, null, { params: { id, nodeId } });
