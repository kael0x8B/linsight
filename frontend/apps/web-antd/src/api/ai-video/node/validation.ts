import type {
  GatewayImageResult,
  GatewaySnapshot,
  GatewayTask,
  GatewayTransport,
} from './gateway';

export interface ValidationExpected {
  category: string;
  confidence: number;
  count: number;
  text: string;
}
export interface ValidationSample {
  expected: ValidationExpected;
  id: string;
  mime: string;
  name: string;
  note: string;
  sha256: string;
}
export interface ValidationSet {
  count?: number;
  createdAt: string;
  id: string;
  name: string;
  revision: number;
  samples: ValidationSample[];
}
export interface ValidationItem extends ValidationSample {
  actualCount?: number;
  diagnosticId?: string;
  error?: string;
  finishedAt?: string;
  result?: GatewayImageResult;
  status: 'ERROR' | 'FAIL' | 'INCONCLUSIVE' | 'PASS' | 'PENDING' | 'RUNNING';
}
export interface ValidationAlgorithm {
  manifest?: { code: string; name: string; version: string };
  sha256: string;
  status: string;
}
export interface ValidationTarget {
  algorithm?: null | Omit<ValidationAlgorithm, 'status'>;
  modelBindings: Record<string, number>;
  models: GatewaySnapshot['models'];
  name: string;
  parameters: Record<string, unknown>;
  pipelineVersionId: number;
  taskId: number;
  taskRevision: number;
}
export interface ValidationRun {
  createdAt: string;
  id: string;
  items: ValidationItem[];
  schemaVersion: string;
  setId: string;
  setName: string;
  setRevision: number;
  target: ValidationTarget;
}
export interface ValidationOptions {
  algorithms: ValidationAlgorithm[];
  models: GatewaySnapshot['models'];
  tasks: GatewayTask[];
}
export interface ValidationImage {
  imageBase64: string;
  mime: string;
}

/** Chunked reads fit both the local entrance and the platform reverse-channel limit. */
export async function readValidationImage(
  transport: GatewayTransport,
  id: string,
  sampleId: string,
  active: () => boolean = () => true,
): Promise<ValidationImage> {
  let offset = 0;
  const parts: string[] = [];
  while (active()) {
    const chunk = await transport<
      ValidationImage & { length: number; offset: number; size: number }
    >('validation.image', { id, sampleId, offset });
    if (!active()) throw new Error('Cancelled');
    if (
      chunk.offset !== offset ||
      chunk.length <= 0 ||
      chunk.size > 4 * 1024 * 1024
    )
      throw new Error('Invalid image chunk');
    parts.push(chunk.imageBase64);
    offset += chunk.length;
    if (offset >= chunk.size) return { imageBase64: parts.join(''), mime: chunk.mime };
  }
  throw new Error('Cancelled');
}

export type ValidationHistory = Pick<ValidationRun, 'createdAt' | 'id' | 'setRevision'> & {
  target: Pick<ValidationTarget, 'name'>;
};
