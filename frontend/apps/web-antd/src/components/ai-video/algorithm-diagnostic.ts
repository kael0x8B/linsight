export interface AlgorithmDiagnostic {
  code: string;
  diagnosticId: string;
  exceptionType: string;
  frames: Array<{ file: string; function: string; line: number }>;
  message: string;
  packageCode: string;
  packageSha256: string;
  packageVersion: string;
  stage: string;
  timestampMillis?: number;
}

export function algorithmDiagnostic(
  value: unknown,
): AlgorithmDiagnostic | undefined {
  if (!value || typeof value !== 'object') return;
  const data = value as Record<string, unknown>;
  if (
    data.schemaVersion !== '1.0' ||
    ![
      'code',
      'diagnosticId',
      'exceptionType',
      'message',
      'packageCode',
      'packageSha256',
      'packageVersion',
      'stage',
    ].every((key) => typeof data[key] === 'string')
  )
    return;
  const frames = Array.isArray(data.frames)
    ? data.frames
        .filter(
          (frame) =>
            frame &&
            typeof frame.file === 'string' &&
            typeof frame.line === 'number',
        )
        .slice(-6)
    : [];
  return { ...data, frames } as unknown as AlgorithmDiagnostic;
}
