import type {
  AlgorithmManifest,
  ParameterField,
} from '#/api/ai-video/algorithm/package';
import type { GatewayConfig } from '#/api/ai-video/node/gateway';

export type ParameterDefinition = Pick<
  AlgorithmManifest,
  'defaultParameters' | 'parameterSchema'
>;

export function gatewayPackageManifest(
  config: GatewayConfig,
): AlgorithmManifest | undefined {
  return (
    config.pipeline.algorithmPackage as
      | undefined
      | { manifest: AlgorithmManifest }
  )?.manifest;
}

/** Older pipelines declare capabilities; adapt those contracts to the same schema form. */
export function gatewayParameterDefinition(
  config: GatewayConfig,
): ParameterDefinition {
  const manifest = gatewayPackageManifest(config);
  if (manifest) return manifest;
  const capabilities = (
    (config.pipeline.nodes ?? []) as { capabilityKey?: string }[]
  ).map((node) => node.capabilityKey ?? '');
  const properties: Record<string, ParameterField> = {};
  const defaults: Record<string, unknown> = {};
  const field = (
    key: string,
    title: string,
    value: unknown,
    schema: ParameterField,
  ) => {
    properties[key] = { title, ...schema };
    defaults[key] = value;
  };
  const confidence: ParameterField = {
    type: 'number',
    minimum: 0.01,
    maximum: 1,
  };
  if (
    capabilities.some(
      (value) => value.startsWith('ppe.') || value.startsWith('behavior.'),
    )
  )
    field('personConfidence', '人员置信度', 0.5, confidence);
  if (capabilities.some((value) => value.startsWith('ppe.')))
    field('ppeConfidence', '穿戴置信度', 0.5, confidence);
  if (capabilities.includes('ocr.license-plate')) {
    field('ocrMinConfidence', '车牌最低置信度', 0.75, confidence);
    field('ocrMinVotes', '一致识别帧数', 3, {
      type: 'integer',
      minimum: 2,
      maximum: 30,
      description: '在投票窗口内，同一车牌达到一致识别帧数后，再判断告警条件。',
    });
    field('ocrVoteFrames', '投票窗口帧数', 5, {
      type: 'integer',
      minimum: 2,
      maximum: 30,
    });
    field('ocrVoteMaxAgeSeconds', '投票有效时间（秒）', 10, {
      type: 'number',
      minimum: 1,
      maximum: 60,
    });
    field('plateUseRuleRoi', '在告警区域内检测车牌', false, {
      type: 'boolean',
    });
    field('plateMaxCandidates', '每帧最多识别车牌数', 10, {
      type: 'integer',
      minimum: 1,
      maximum: 30,
    });
  }
  return {
    parameterSchema: {
      type: 'object',
      properties,
      required: Object.keys(properties),
    },
    defaultParameters: defaults,
  };
}

export function gatewaySpecificParameters(
  config: GatewayConfig,
): Record<string, unknown> {
  return gatewayPackageManifest(config)
    ? ((config.parameters.algorithm as Record<string, unknown> | undefined) ??
        {})
    : config.parameters;
}

function mergeValues(
  current: Record<string, unknown>,
  changes: Record<string, unknown>,
): Record<string, unknown> {
  const result = { ...current };
  for (const [key, value] of Object.entries(changes)) {
    const previous = current[key];
    result[key] =
      value &&
      typeof value === 'object' &&
      !Array.isArray(value) &&
      previous &&
      typeof previous === 'object' &&
      !Array.isArray(previous)
        ? mergeValues(
            previous as Record<string, unknown>,
            value as Record<string, unknown>,
          )
        : value;
  }
  return result;
}

/** Preserve fields outside this editor and keep package thresholds in their owned namespace. */
export function mergeGatewayParameters(
  config: GatewayConfig,
  common: Record<string, unknown>,
  specific: Record<string, unknown>,
) {
  if (gatewayPackageManifest(config))
    return {
      ...config.parameters,
      ...common,
      algorithm: mergeValues(gatewaySpecificParameters(config), specific),
    };
  const parameters = { ...config.parameters, ...common, ...specific };
  if (Number(parameters.ocrMinVotes) > Number(parameters.ocrVoteFrames))
    throw new Error('一致识别帧数不能超过投票窗口帧数。');
  return parameters;
}
