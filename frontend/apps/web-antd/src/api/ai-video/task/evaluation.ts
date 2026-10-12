import type { PageParam } from '@vben/request';

import { requestClient } from '#/api/request';

export interface EvaluationMetrics {
  averageFps: number;
  endToEndP95Ms: number;
  eventPrecision: number;
  eventRecall: number;
  falsePositivesPerStreamHour: number;
  missedEvents: number;
}
export interface EvaluationThresholds {
  maxEndToEndP95Ms: number;
  maxFalsePositivesPerStreamHour: number;
  maxMissedEvents: number;
  minAverageFps: number;
  minEventPrecision: number;
  minEventRecall: number;
}
export interface EvaluationCreate {
  cooldownDedupPass: boolean;
  datasetSha256: string;
  datasetVersion: string;
  environmentDescription: string;
  evidenceRef: string;
  expectedConfigVersion: number;
  expectedGatewayRevision: number;
  measuredAtMillis: number;
  metrics: EvaluationMetrics;
  note?: string;
  requestId: string;
  resourceUsage: {
    acceleratorMemoryPeakMiB: number;
    cpuPeakPercent: number;
    memoryPeakMiB: number;
  };
  taskId: number;
  thresholds: EvaluationThresholds;
}
export interface TaskEvaluation {
  configurationSnapshot?: Record<string, unknown>;
  configVersion: number;
  createTime: string;
  creator: string;
  datasetSha256: string;
  datasetVersion: string;
  evidenceRef: string;
  failedChecks: string[];
  id: number;
  measuredAtMillis: number;
  measurement?: EvaluationCreate;
  source: 'MANUAL_VIDEO';
  status: 'FAIL' | 'PASS';
  taskId: number;
  taskName: string;
}

export function createTaskEvaluation(data: EvaluationCreate) {
  return requestClient.post<number>('/ai-video/task/evaluation/create', data);
}
export function getTaskEvaluation(id: number) {
  return requestClient.get<TaskEvaluation>('/ai-video/task/evaluation/get', {
    params: { id },
  });
}
export function getTaskEvaluationPage(
  params: PageParam & { status?: string; taskId?: number },
) {
  return requestClient.get<{ list: TaskEvaluation[]; total: number }>(
    '/ai-video/task/evaluation/page',
    { params },
  );
}
