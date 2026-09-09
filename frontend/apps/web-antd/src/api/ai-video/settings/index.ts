import { requestClient } from '#/api/request';

export namespace AiVideoSettingsApi {
  export interface Settings {
    defaultConfidence: number;
    defaultFps: number;
    evidenceRetentionDays: number;
    evidenceStorageMode: 'OBJECT_STORAGE';
    nodeOfflineThresholdSeconds: number;
    notificationsEnabled: boolean;
    recordAfterSeconds: number;
    recordBeforeSeconds: number;
    schemaVersion: '1.0';
  }

  export interface Current {
    settings: Settings;
    versionNo: number;
  }

  export interface Version {
    affectedTaskCount: number;
    appliedAt: string;
    applyScope: 'ALL_RUNNING' | 'GRAY' | 'NEW_TASKS';
    commandCount: number;
    creator: string;
    diff: Record<string, { after: unknown; before: unknown }>;
    grayTaskIds: number[];
    id: number;
    settings: Settings;
    status: 'APPLIED' | 'DISPATCHED' | 'PARTIAL';
    versionNo: number;
  }

  export interface SaveRequest {
    applyScope: 'ALL_RUNNING' | 'GRAY' | 'NEW_TASKS';
    expectedVersionNo: number;
    grayTaskIds?: number[];
    settings: Settings;
  }
}

export function getGlobalSettings() {
  return requestClient.get<AiVideoSettingsApi.Current>('/ai-video/settings/get');
}

export function saveGlobalSettings(data: AiVideoSettingsApi.SaveRequest) {
  return requestClient.post<AiVideoSettingsApi.Version>('/ai-video/settings/save', data);
}

export function getGlobalSettingsVersions() {
  return requestClient.get<AiVideoSettingsApi.Version[]>(
    '/ai-video/settings/version/list',
  );
}
