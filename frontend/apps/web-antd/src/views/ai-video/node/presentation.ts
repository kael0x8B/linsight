import type { AiVideoNode } from '#/api/ai-video/node';

export interface NodeExecutionProviderView {
  code: string;
  deviceType: string;
  formats: string[];
  runtime: string;
  runtimeVersion?: string;
  targets: string[];
  vendor: string;
}

export function nodeResources(value?: string) {
  let data: Record<string, unknown> = {};
  try {
    data = JSON.parse(value || '{}') ?? {};
  } catch {
    /* Unknown heartbeat data remains unavailable. */
  }
  const number = (key: string) =>
    typeof data[key] === 'number' && Number.isFinite(data[key])
      ? (data[key] as number)
      : null;
  const ratio = (used: string, total: string) => {
    const a = number(used);
    const b = number(total);
    return a !== null && b !== null && b > 0 ? (a / b) * 100 : null;
  };
  const gpu = number('gpuUsage');
  const npu = number('npuUsage');
  let accelerator = gpu;
  if (gpu === null) accelerator = npu;
  else if (npu !== null) accelerator = Math.max(gpu, npu);
  const cleanupStatus =
    typeof data.diskCleanupStatus === 'string' ? data.diskCleanupStatus : null;
  const cleanupFreed = number('diskCleanupFreedBytes');
  const cleanupAfter = number('diskCleanupAfterPercent');
  let cleanupSummary: null | string = null;
  if (cleanupStatus === 'RECLAIMED')
    cleanupSummary = `自动处置已回收 ${formatBytes(cleanupFreed)}，磁盘降至 ${cleanupAfter ?? '—'}%`;
  else if (cleanupStatus === 'STILL_HIGH')
    cleanupSummary = `自动处置后磁盘仍为 ${cleanupAfter ?? '—'}%，需要扩容或人工核查`;
  const environment = record(data.modelEnvironment);
  const modelFormats = strings(environment?.formats);
  const legacyTargets = strings(environment?.rknnTargets);
  const executionProviders = Array.isArray(environment?.providers)
    ? environment.providers
        .map(executionProvider)
        .filter((provider): provider is NodeExecutionProviderView => !!provider)
    : [];
  const executionSummary = executionProviders.length
    ? executionProviders.map(executionProviderLabel).join('；')
    : modelFormats.length
      ? `旧版能力上报${legacyTargets.length ? `（${legacyTargets.join('、')}）` : ''}`
      : null;
  return {
    cpu: number('cpuUsage'),
    gpu,
    npu,
    accelerator,
    memory: ratio('memoryUsedBytes', 'memoryTotalBytes'),
    disk: ratio('diskUsedBytes', 'diskTotalBytes'),
    cleanupStatus,
    cleanupSummary,
    executionProviders,
    executionSummary,
    modelFormats,
    modelFormatSummary: modelFormats.length ? modelFormats.join('、') : null,
    data,
  };
}

function record(value: unknown) {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function strings(value: unknown) {
  return Array.isArray(value)
    ? [
        ...new Set(
          value.filter((item): item is string => typeof item === 'string'),
        ),
      ]
    : [];
}

function executionProvider(value: unknown): NodeExecutionProviderView | null {
  const provider = record(value);
  if (
    !provider ||
    typeof provider.code !== 'string' ||
    typeof provider.deviceType !== 'string' ||
    typeof provider.vendor !== 'string' ||
    typeof provider.runtime !== 'string'
  )
    return null;
  return {
    code: provider.code,
    deviceType: provider.deviceType,
    vendor: provider.vendor,
    targets: strings(provider.targets),
    formats: strings(provider.formats),
    runtime: provider.runtime,
    ...(typeof provider.runtimeVersion === 'string'
      ? { runtimeVersion: provider.runtimeVersion }
      : {}),
  };
}

function executionProviderLabel(provider: NodeExecutionProviderView) {
  const names: Record<string, string> = {
    'nvidia-tensorrt': 'NVIDIA TensorRT',
    onnxruntime: 'ONNX Runtime CPU',
    'python-cpu': '隔离 CPU 环境',
    rknpu2: 'Rockchip NPU',
  };
  const target = provider.targets.length
    ? ` / ${provider.targets.join('、')}`
    : '';
  const version = provider.runtimeVersion ? ` ${provider.runtimeVersion}` : '';
  return `${names[provider.code] || provider.code}${target}（${provider.runtime}${version}）`;
}
function formatBytes(value: null | number) {
  if (value === null) return '—';
  if (value >= 1024 ** 3) return `${(value / 1024 ** 3).toFixed(1)} GiB`;
  return `${Math.round(value / 1024 ** 2)} MiB`;
}
export function gatewayLocation(
  id: number,
  tab = 'algorithms',
  cameraId?: number,
) {
  return {
    path: `/ai-video/node/${id}`,
    query: { tab, ...(cameraId ? { cameraId: String(cameraId) } : {}) },
  };
}
export function nodeStatus(node: AiVideoNode) {
  if (node.onlineStatus === 1) return '在线';
  if (node.onlineStatus === 2) return '离线';
  return '状态未知';
}
