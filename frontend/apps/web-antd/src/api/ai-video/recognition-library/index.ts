import type { PageParam, PageResult } from '@vben/request';

import { requestClient } from '#/api/request';

export namespace AiVideoRecognitionLibraryApi {
  export type LibraryType = 'FACE' | 'PLATE' | 'POSE';
  export type MatchMode = 'CLASSIFICATION' | 'EXACT' | 'ONE_TO_N';

  export interface Library {
    code: string;
    createTime?: string;
    description?: string;
    engineModelVersionId?: number;
    entryCount: number;
    featureDimension?: number;
    id: number;
    libraryType: LibraryType;
    matchMode: MatchMode;
    name: string;
    status: number;
    updateTime?: string;
  }

  export interface LibrarySave {
    code: string;
    description?: string;
    engineModelVersionId?: number;
    featureDimension?: number;
    id?: number;
    libraryType: LibraryType;
    matchMode: MatchMode;
    name: string;
    status: number;
  }

  export interface Entry {
    attributes: Record<string, unknown>;
    createTime?: string;
    externalCode?: string;
    featureStatus: 'FAILED' | 'PENDING' | 'READY';
    id: number;
    libraryId: number;
    mediaRef?: string;
    name: string;
    status: number;
    updateTime?: string;
  }

  export interface EntrySave {
    attributes: Record<string, unknown>;
    externalCode?: string;
    featureStatus: 'FAILED' | 'PENDING' | 'READY';
    id?: number;
    libraryId: number;
    mediaRef?: string;
    name: string;
    status: number;
  }

  export interface LibraryPageParams extends PageParam {
    libraryType?: LibraryType;
    name?: string;
    status?: number;
  }

  export interface EntryPageParams extends PageParam {
    featureStatus?: string;
    libraryId: number;
    name?: string;
    status?: number;
  }
}

const base = '/ai-video/algorithm/library';

export function getRecognitionLibraryPage(
  params: AiVideoRecognitionLibraryApi.LibraryPageParams,
) {
  return requestClient.get<PageResult<AiVideoRecognitionLibraryApi.Library>>(
    `${base}/page`,
    { params },
  );
}

export function createRecognitionLibrary(
  data: AiVideoRecognitionLibraryApi.LibrarySave,
) {
  return requestClient.post<number>(`${base}/create`, data);
}

export function updateRecognitionLibrary(
  data: AiVideoRecognitionLibraryApi.LibrarySave,
) {
  return requestClient.put(`${base}/update`, data);
}

export function deleteRecognitionLibrary(id: number) {
  return requestClient.delete(`${base}/delete?id=${id}`);
}

export function getRecognitionEntryPage(
  params: AiVideoRecognitionLibraryApi.EntryPageParams,
) {
  return requestClient.get<PageResult<AiVideoRecognitionLibraryApi.Entry>>(
    `${base}/entry/page`,
    { params },
  );
}

export function createRecognitionEntry(
  data: AiVideoRecognitionLibraryApi.EntrySave,
) {
  return requestClient.post<number>(`${base}/entry/create`, data);
}

export function updateRecognitionEntry(
  data: AiVideoRecognitionLibraryApi.EntrySave,
) {
  return requestClient.put(`${base}/entry/update`, data);
}

export function deleteRecognitionEntry(id: number) {
  return requestClient.delete(`${base}/entry/delete?id=${id}`);
}
