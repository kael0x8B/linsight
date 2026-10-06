import { requestClient } from '#/api/request';

export interface ReleaseBuildConfiguration {
  label: string;
  architecture: string;
  devices: string[];
  ready: boolean;
}
export interface ApplicationRelease {
  id: number;
  profileId: string;
  profileLabel: string;
  architecture: string;
  devices: string;
  keyId: string;
  version: string;
  notes: string;
  status: 'BUILDING' | 'FAILED' | 'QUEUED' | 'STORING' | 'SUCCEEDED';
  message: string;
  attempt: number;
  fileName?: string;
  size?: number;
  sha256?: string;
  bootstrapSha256?: string;
  sourceSha256?: string;
  createTime: string;
  finishTime?: string;
}
export interface CreateRelease {
  version: string;
  notes: string;
  requestId: string;
}
const base = '/ai-video/node/application-release';
export const getReleaseConfiguration = () =>
  requestClient.get<ReleaseBuildConfiguration>(`${base}/configuration`);
export const getReleasePage = (params: { pageNo: number; pageSize: number }) =>
  requestClient.get<{ list: ApplicationRelease[]; total: number }>(
    `${base}/page`,
    { params },
  );
export const createRelease = (data: CreateRelease) =>
  requestClient.post<number>(`${base}/create`, data);
export const retryRelease = (id: number) =>
  requestClient.post(`${base}/retry`, undefined, { params: { id } });
export const getReleaseDownloadUrl = (
  id: number,
  artifact: 'bootstrap' | 'bundle' | 'public-key',
) =>
  requestClient.get<string>(`${base}/download-url`, {
    params: { id, artifact },
  });
