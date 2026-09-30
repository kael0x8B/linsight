import { requestClient } from '#/api/request';

export interface FaceVerificationResult {
  id: number;
  status: string;
  result: {
    backend?: string;
    device?: string;
    liveness?: string;
    matchedFrames?: number;
    reason?: string;
    sampledFrames?: number;
    similarity?: number;
    status?: string;
    validationOnly?: boolean;
  };
}

export interface FaceVerificationInput {
  cameraId: number;
  consentConfirmed: boolean;
  file: File;
  modelVersionId: number;
  nodeId: number;
  roiHeight: number;
  roiWidth: number;
  roiX: number;
  roiY: number;
  similarityThreshold: number;
}

export function createFaceVerification(data: FaceVerificationInput) {
  return requestClient.upload<number>(
    '/ai-video/task/face-verification/create',
    data,
  );
}
export function getFaceVerification(id: number) {
  return requestClient.get<FaceVerificationResult>(
    '/ai-video/task/face-verification/get',
    {
      params: { id },
    },
  );
}
