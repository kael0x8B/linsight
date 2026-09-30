import type { AlgorithmManifest } from '#/api/ai-video/algorithm/package';
import type { ExecutableModelOption } from '#/api/ai-video/model';
import type {
  GatewayConfig,
  GatewaySnapshot,
} from '#/api/ai-video/node/gateway';

type InstalledModel = GatewaySnapshot['models'][number];
export interface GatewayModelRole {
  slot: string;
  name: string;
  capability?: string;
  modelId?: number;
  modelIds?: number[];
  requirement?: AlgorithmManifest['models'][number];
  declared: boolean;
}
interface PipelineNode {
  id: string;
  type: string;
  name?: string;
  modelId?: number;
  modelIds?: number[];
  capabilityKey?: string;
}
const capabilityNames: Record<string, string> = {
  'detector.object': '目标检测模型',
  'detector.person': '人员检测模型',
  'detector.vehicle': '车辆检测模型',
  'detector.license-plate': '车牌定位模型',
  'ocr.license-plate': '车牌文字识别模型',
  'ppe.helmet': '安全帽识别模型',
  'ppe.reflective-vest': '反光衣识别模型',
  'behavior.phone-call': '接打电话识别模型',
  'behavior.smoking': '吸烟识别模型',
  'behavior.fall': '跌倒识别模型',
};
export function modelRoleName(capability?: string, fallback = '识别模型') {
  return capabilityNames[capability ?? ''] || fallback;
}
const modelNodeTypes = new Set([
  'CLASSIFIER',
  'DETECTOR',
  'OCR',
  'POSE',
  'QUALITY',
  'RECOGNIZER',
  'SEGMENTER',
]);

/** Model roles come from the algorithm contract, never from model display names. */
export function gatewayModelRoles(config: GatewayConfig): GatewayModelRole[] {
  const descriptor = config.pipeline.algorithmPackage as
    | undefined
    | { manifest?: AlgorithmManifest };
  const nodes = (config.pipeline.nodes ?? []) as PipelineNode[];
  const roles: GatewayModelRole[] = descriptor?.manifest?.models
    ? descriptor.manifest.models.map((role) => ({
        slot: role.slot,
        name: role.name || role.slot,
        requirement: role,
        declared: true,
      }))
    : nodes
        .filter((node) => modelNodeTypes.has(node.type))
        .map((node) => ({
          slot: node.id,
          name: node.name || modelRoleName(node.capabilityKey, node.id),
          capability: node.capabilityKey,
          modelId: node.modelId,
          modelIds: node.modelIds,
          declared: true,
        }));
  for (const slot of Object.keys(config.modelBindings ?? {})) {
    if (!roles.some((role) => role.slot === slot))
      roles.push({
        slot,
        name: slot === 'primary' ? '识别模型' : `已有绑定 · ${slot}`,
        declared: false,
      });
  }
  if (!roles.length)
    roles.push({ slot: 'primary', name: '识别模型', declared: false });
  return roles;
}

export function gatewayRoleModelId(config: GatewayConfig, slot: string) {
  return (
    config.modelBindings?.[slot] ??
    (slot === 'primary' ? config.modelVersionId : undefined)
  );
}

function matchesRole(
  role: GatewayModelRole,
  model: InstalledModel,
  current?: InstalledModel,
) {
  const manifest = model.runtimeManifest;
  const requirement = role.requirement;
  if (requirement) {
    return (
      (!requirement.formats?.length ||
        requirement.formats.includes(model.artifactFormat)) &&
      (!requirement.taskType || requirement.taskType === manifest?.taskType) &&
      (requirement.labels ?? []).every((label) =>
        manifest?.decoder?.labels?.includes(label),
      )
    );
  }
  if (!role.declared) return false;
  switch (role.capability) {
    case 'detector.license-plate':
      return (
        manifest?.taskType === 'OBJECT_DETECTION' &&
        ['LPD_YUNET', 'YOLO_PLATE'].includes(manifest.decoder?.type ?? '')
      );
    case 'detector.object':
      return manifest?.taskType === 'OBJECT_DETECTION';
    case 'detector.person':
      return (
        manifest?.taskType === 'OBJECT_DETECTION' &&
        !!manifest.decoder?.labels?.includes('person')
      );
    case 'detector.vehicle':
      return (
        manifest?.taskType === 'OBJECT_DETECTION' &&
        !!manifest.decoder?.labels?.some((label) =>
          ['bus', 'car', 'cargo_truck', 'heavy_truck', 'truck'].includes(label),
        )
      );
    case 'ocr.license-plate':
      return (
        manifest?.taskType === 'OCR' &&
        ['CHINESE_PLATE_CTC', 'LPRNET'].includes(manifest.decoder?.type ?? '')
      );
    default: {
      // For other legacy pipelines, only offer the same documented output contract.
      const previous = current?.runtimeManifest;
      return (
        !!previous?.taskType &&
        !!previous.decoder?.type &&
        previous.taskType === manifest?.taskType &&
        previous.decoder.type === manifest.decoder?.type &&
        (previous.decoder.labels ?? []).every((label) =>
          manifest.decoder?.labels?.includes(label),
        )
      );
    }
  }
}

export function gatewayRoleModelOptions(
  role: GatewayModelRole,
  config: GatewayConfig,
  snapshot: GatewaySnapshot,
  catalog: ExecutableModelOption[] = [],
) {
  const currentId = gatewayRoleModelId(config, role.slot);
  const current = snapshot.models.find(
    (model) => model.modelVersionId === currentId,
  );
  const options = snapshot.models
    .filter((model) => {
      if (model.modelVersionId === currentId) return true;
      // A published pipeline can pin the model asset, not just its output type.
      // Without authoritative catalog metadata, retain the current binding only.
      const allowedModelIds = role.modelIds?.length
        ? role.modelIds
        : role.modelId
          ? [role.modelId]
          : [];
      if (
        allowedModelIds.length &&
        !catalog.some(
          (entry) =>
            entry.id === model.modelVersionId &&
            allowedModelIds.includes(entry.modelId),
        )
      )
        return false;
      return matchesRole(role, model, current);
    })
    .map((model) => ({
      value: model.modelVersionId,
      label: `${snapshot.names?.models[model.modelVersionId]?.name || model.displayName || `模型 #${model.modelVersionId}`} · ${snapshot.names?.models[model.modelVersionId]?.version || model.version || model.artifactFormat} · ${model.device === 'RKNPU' ? 'NPU' : model.device}`,
      disabled: false,
    }));
  if (currentId && !current)
    options.unshift({
      value: currentId,
      label: `${snapshot.names?.models[currentId]?.name || `模型 #${currentId}`}（本机未安装，保留原绑定）`,
      disabled: true,
    });
  return options;
}

/** Change slots independently, including when two roles share the same version. */
export function updateGatewayModelBindings(
  config: GatewayConfig,
  selection: Record<string, unknown>,
  snapshot: GatewaySnapshot,
  catalog: ExecutableModelOption[] = [],
) {
  const roles = gatewayModelRoles(config);
  const bindings = { ...config.modelBindings };
  for (const role of roles) {
    const selected = selection[role.slot];
    const version = Number(selected);
    if (!Number.isSafeInteger(version) || version <= 0)
      throw new Error(`请选择${role.name}`);
    if (
      version !== gatewayRoleModelId(config, role.slot) &&
      !gatewayRoleModelOptions(role, config, snapshot, catalog).some(
        (option) => option.value === version && !option.disabled,
      )
    )
      throw new Error(`${role.name}所选版本与算法不兼容，或尚未安装到本机`);
    bindings[role.slot] = version;
  }
  const primaryRole =
    roles.find(
      (role) =>
        role.slot === 'primary' &&
        gatewayRoleModelId(config, role.slot) === config.modelVersionId,
    ) ??
    roles.find(
      (role) => gatewayRoleModelId(config, role.slot) === config.modelVersionId,
    );
  return {
    modelVersionId: primaryRole
      ? bindings[primaryRole.slot]!
      : config.modelVersionId,
    modelBindings: bindings,
  };
}
