import type { GatewayTransport } from '#/api/ai-video/node/gateway';

export interface ApplicationUpgradeJob {
  action: string;
  id: string;
  message: string;
  notes?: string;
  phase: string;
  version?: string;
}
export interface ApplicationUpgradeStatus {
  current?: { id: string; version: string };
  job?: ApplicationUpgradeJob;
  lastError?: { at: number; message: string };
  message?: string;
  rollbackAvailable?: boolean;
  supported: boolean;
}

export const upgradeBusy = (phase?: string) =>
  !!phase && !['FAILED', 'READY', 'RECOVERY_FAILED', 'ROLLED_BACK', 'SUCCEEDED'].includes(phase);

export async function uploadApplication(
  file: File,
  id: string,
  transport: GatewayTransport,
  progress: (percent: number) => void,
  cancelled: () => boolean,
) {
  if (!file.name.endsWith('.lup') || file.size < 1 || file.size > 2 * 1024 ** 3) {
    throw new Error('INVALID_PACKAGE');
  }
  const initial = await transport<{ offset: number }>('app-upgrade.upload.begin', {
    id, size: file.size,
  });
  let offset = initial.offset;
  if (!Number.isInteger(offset) || offset < 0 || offset > file.size) throw new Error('INVALID_OFFSET');
  while (offset < file.size) {
    if (cancelled()) return false;
    const end = Math.min(offset + 256 * 1024, file.size);
    const bytes = new Uint8Array(await file.slice(offset, end).arrayBuffer());
    let binary = '';
    for (const byte of bytes) binary += String.fromCodePoint(byte);
    const result = await transport<{ offset: number }>('app-upgrade.upload.chunk', {
      data: btoa(binary), id, offset,
    });
    if (result.offset !== end) throw new Error('INVALID_OFFSET');
    offset = result.offset;
    progress(Math.floor((offset / file.size) * 100));
  }
  if (cancelled()) return false;
  await transport('app-upgrade.upload.finish', { id });
  return true;
}
