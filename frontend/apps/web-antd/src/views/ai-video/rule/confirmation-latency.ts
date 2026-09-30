export const EVENT_VISIBILITY_TARGET_SECONDS = 2;

export interface ConfirmationLatency {
  durationSeconds: number;
  minimumSeconds: number;
  n: number;
  m: number;
}

function thresholds(condition: unknown) {
  const value = { durationSeconds: 0, n: 1, m: 1 };
  const visit = (node: unknown) => {
    if (!node || typeof node !== 'object') return;
    const item = node as Record<string, unknown>;
    if (item.type === 'N_OF_M') {
      value.n = Number(item.n ?? 1);
      value.m = Number(item.m ?? value.n);
    } else if (item.type === 'DURATION') {
      value.durationSeconds = Number(item.seconds ?? 0);
    }
    if (Array.isArray(item.children)) item.children.forEach(visit);
    visit(item.child);
  };
  visit(condition);
  return value;
}

/** Theoretical lower bound; inference, upload, and rendering add more time. */
export function estimateConfirmationLatency(
  ast: null | Record<string, unknown> | undefined,
  sampleFps: number,
): ConfirmationLatency | undefined {
  if (!ast || !Number.isFinite(sampleFps) || sampleFps <= 0) return;
  const value = thresholds(ast.condition);
  const durationIntervals = Math.ceil(
    Math.max(0, value.durationSeconds * sampleFps) - 1e-12,
  );
  return {
    ...value,
    minimumSeconds: (value.n - 1 + durationIntervals) / sampleFps,
  };
}

export function conflictsWithVisibilityTarget(
  estimate: ConfirmationLatency | undefined,
) {
  return (
    !!estimate &&
    estimate.minimumSeconds > EVENT_VISIBILITY_TARGET_SECONDS + 1e-9
  );
}

export function confirmationLatencyMessage(estimate: ConfirmationLatency) {
  const seconds = Number(estimate.minimumSeconds.toFixed(2));
  return `按 ${estimate.n}/${estimate.m} 帧、持续 ${estimate.durationSeconds} 秒和当前采样率，理论最短确认时延约 ${seconds} 秒；实际还会叠加推理与上报耗时。`;
}
