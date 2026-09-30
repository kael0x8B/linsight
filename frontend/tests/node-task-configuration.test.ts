import type { AiVideoAlgorithmApi } from '../apps/web-antd/src/api/ai-video/algorithm';
import type { ExecutableModelOption } from '../apps/web-antd/src/api/ai-video/model';
import type { AiVideoRuleApi } from '../apps/web-antd/src/api/ai-video/rule';

import { describe, expect, it } from 'vitest';

import {
  compatibleTaskRules,
  defaultTaskRule,
  taskModelLabel,
  taskModelOptions,
  taskModelRoles,
} from '../apps/web-antd/src/views/ai-video/task/configuration-options';

const algorithm = {
  currentPipelineVersionId: 50,
  defaultModelId: 1,
} as AiVideoAlgorithmApi.Algorithm;
const pipeline = {
  id: 50,
  validationStatus: 'PUBLISHED',
  dag: {
    nodes: [
      {
        id: 'vehicle',
        type: 'DETECTOR',
        capabilityKey: 'detector.vehicle',
        modelId: 1,
      },
      {
        id: 'plate',
        type: 'DETECTOR',
        capabilityKey: 'detector.license-plate',
        modelId: 2,
      },
      {
        id: 'ocr',
        type: 'OCR',
        capabilityKey: 'ocr.license-plate',
        modelId: 3,
      },
      { id: 'tracker', type: 'TRACKER' },
    ],
  },
} as AiVideoAlgorithmApi.PipelineVersion;
const model = {
  id: 121,
  modelId: 1,
  name: '通用目标检测',
  version: 'person-int8-rk3566',
  format: 'RKNN',
} as ExecutableModelOption;
const rules: AiVideoRuleApi.Rule[] = [
  {
    id: 1,
    name: '普通车牌',
    code: 'plate',
    eventType: 'LICENSE_PLATE',
    currentVersionId: 10,
    status: 0,
  },
  {
    id: 2,
    name: '厂区车辆',
    code: 'yard',
    eventType: 'VEHICLE_PLATE_RECOGNIZED',
    currentVersionId: 20,
    status: 0,
  },
  {
    id: 3,
    name: '未发布',
    code: 'draft',
    eventType: 'LICENSE_PLATE',
    status: 0,
  },
  {
    id: 4,
    name: '已停用',
    code: 'disabled',
    eventType: 'LICENSE_PLATE',
    currentVersionId: 40,
    status: 1,
  },
];

describe('task creation models', () => {
  it('shows every actual pipeline model by its purpose', () => {
    expect(taskModelRoles(algorithm, pipeline)).toEqual([
      { nodeId: 'vehicle', modelId: 1, label: '车辆检测模型' },
      { nodeId: 'plate', modelId: 2, label: '车牌定位模型' },
      { nodeId: 'ocr', modelId: 3, label: '车牌文字识别模型' },
    ]);
  });
  it('requires the current published pipeline, preventing stale catalog defaults', () => {
    expect(() => taskModelRoles(algorithm, { ...pipeline, id: 49 })).toThrow(
      '已发布',
    );
    expect(() =>
      taskModelRoles(algorithm, { ...pipeline, validationStatus: 'DRAFT' }),
    ).toThrow('已发布');
  });
  it('supports explicit model dependencies even without a default primary model', () => {
    expect(
      taskModelRoles({ ...algorithm, defaultModelId: undefined }, pipeline),
    ).toHaveLength(3);
  });
  it('does not fall back to another model family with a similar name', () => {
    expect(
      taskModelOptions(taskModelRoles(algorithm, pipeline)[0]!, [
        model,
        { ...model, id: 138, modelId: 2 },
      ]),
    ).toEqual([model]);
  });
  it('offers explicitly declared hardware-specific model assets for one role', () => {
    const multiTarget = structuredClone(pipeline);
    (multiTarget.dag.nodes as Record<string, unknown>[])[0]!.modelIds = [1, 4];
    const rk3588 = { ...model, id: 141, modelId: 4 };
    const role = taskModelRoles(algorithm, multiTarget)[0]!;
    expect(role.modelIds).toEqual([1, 4]);
    expect(taskModelOptions(role, [model, rk3588])).toEqual([model, rk3588]);
  });
  it('does not report NPU because rknn appears in a version name', () => {
    expect(taskModelLabel(model)).toContain('NPU · RKNN');
    expect(
      taskModelLabel({ ...model, version: 'lprnet-rknn-zoo', format: 'ONNX' }),
    ).toContain('CPU 推理 · ONNX');
  });
  it('retains generic roles for non-plate pipelines', () => {
    expect(
      taskModelRoles(algorithm, {
        ...pipeline,
        dag: {
          nodes: [
            {
              id: 'helmet',
              type: 'DETECTOR',
              modelId: 1,
              capabilityKey: 'ppe.helmet',
            },
          ],
        },
      })[0]?.label,
    ).toBe('安全帽识别模型');
  });
});

describe('task creation rules', () => {
  it('only offers enabled published rules for the exact algorithm event type', () => {
    expect(
      compatibleTaskRules(rules, 'LICENSE_PLATE').map((rule) => rule.id),
    ).toEqual([1]);
    expect(
      compatibleTaskRules(rules, 'VEHICLE_PLATE_RECOGNIZED').map(
        (rule) => rule.id,
      ),
    ).toEqual([2]);
  });
  it('selects a sole compatible rule and clears an incompatible previous choice', () => {
    expect(defaultTaskRule(rules, 'LICENSE_PLATE', 2)).toBe(1);
    expect(defaultTaskRule(rules, 'VEHICLE_PLATE_RECOGNIZED', 1)).toBe(2);
    expect(defaultTaskRule(rules, 'SMOKE', 1)).toBeUndefined();
  });
  it('does not guess between multiple compatible rules or overwrite a valid choice', () => {
    const choices = [...rules, { ...rules[0]!, id: 5 }];
    expect(defaultTaskRule(choices, 'LICENSE_PLATE')).toBeUndefined();
    expect(defaultTaskRule(choices, 'LICENSE_PLATE', 5)).toBe(5);
  });
  it('does not automatically add event rules to an algorithm without events', () => {
    expect(defaultTaskRule([rules[0]!])).toBeUndefined();
  });
});
