import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { ExecutableModelOption } from '#/api/ai-video/model';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { modelExecutionLabel } from '../model/execution-presentation';
import { modelRoleName } from '../node/gateway-model-bindings';

export interface TaskModelRole {
  label: string;
  modelId: number;
  modelIds?: number[];
  nodeId: string;
}
const modelTypes = new Set([
  'CLASSIFIER',
  'DETECTOR',
  'OCR',
  'POSE',
  'QUALITY',
  'RECOGNIZER',
  'SEGMENTER',
]);

export function taskModelRoles(
  algorithm: AiVideoAlgorithmApi.Algorithm,
  pipeline: AiVideoAlgorithmApi.PipelineVersion,
): TaskModelRole[] {
  if (
    pipeline.id !== algorithm.currentPipelineVersionId ||
    pipeline.validationStatus !== 'PUBLISHED'
  )
    throw new Error('当前算法没有可用的已发布版本，请刷新算法目录。');
  const nodes = Array.isArray(pipeline.dag.nodes)
    ? (pipeline.dag.nodes as Record<string, unknown>[])
    : [];
  const roles = nodes
    .filter((node) => modelTypes.has(String(node.type)))
    .map((node) => {
      const alternatives = Array.isArray(node.modelIds)
        ? node.modelIds.map(Number).filter((id) => Number.isSafeInteger(id) && id > 0)
        : [];
      const modelId = Number(
        node.modelId ?? alternatives[0] ?? algorithm.defaultModelId,
      );
      const modelIds = [...new Set([modelId, ...alternatives])];
      return {
        nodeId: String(node.id),
        label: String(
          node.name ||
            modelRoleName(String(node.capabilityKey), String(node.id)),
        ),
        modelId,
        ...(modelIds.length > 1 ? { modelIds } : {}),
      };
    });
  if (!roles.length && algorithm.defaultModelId)
    roles.push({
      nodeId: 'primary',
      label: '识别模型',
      modelId: algorithm.defaultModelId,
    });
  if (
    !roles.length ||
    roles.some(
      (role) => !Number.isSafeInteger(role.modelId) || role.modelId <= 0,
    )
  )
    throw new Error('算法缺少模型依赖，请先完善算法配置。');
  return roles;
}

/** Executable catalog already limits versions to published, tested assets. */
export function taskModelOptions(
  role: TaskModelRole,
  catalog: ExecutableModelOption[],
) {
  const allowed = new Set(role.modelIds ?? [role.modelId]);
  return catalog.filter((model) => allowed.has(model.modelId));
}

export function taskModelLabel(model?: ExecutableModelOption) {
  if (!model) return '未选择';
  return `${model.name} · ${model.version} · ${modelExecutionLabel(model)}`;
}

export function compatibleTaskRules(
  rules: AiVideoRuleApi.Rule[],
  eventType?: string,
) {
  return rules.filter(
    (rule) =>
      rule.status === 0 &&
      !!rule.currentVersionId &&
      (!eventType || rule.eventType === eventType),
  );
}

export function defaultTaskRule(
  rules: AiVideoRuleApi.Rule[],
  eventType?: string,
  selectedId?: number,
) {
  const compatible = compatibleTaskRules(rules, eventType);
  if (compatible.some((rule) => rule.id === selectedId)) return selectedId;
  if (!eventType) return undefined;
  return compatible.length === 1 ? compatible[0]!.id : undefined;
}
