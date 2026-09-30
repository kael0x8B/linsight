export const DEFAULT_PREVIEW_BUFFER_MS = 500;
export const MAX_PREVIEW_BUFFER_MS = 1800;

export function normalizePreviewBuffer(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value)
    ? Math.max(0, Math.min(MAX_PREVIEW_BUFFER_MS, Math.round(value)))
    : DEFAULT_PREVIEW_BUFFER_MS;
}
