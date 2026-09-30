import type { ExecutableModelOption } from '../apps/web-antd/src/api/ai-video/model';
import type {
  GatewayConfig,
  GatewaySnapshot,
} from '../apps/web-antd/src/api/ai-video/node/gateway';

import { describe, expect, it } from 'vitest';

import {
  gatewayModelRoles,
  gatewayRoleModelId,
  gatewayRoleModelOptions,
  updateGatewayModelBindings,
} from '../apps/web-antd/src/views/ai-video/node/gateway-model-bindings';

const models: GatewaySnapshot['models'] = [
  [121, 'OBJECT_DETECTION', 'AUTO_DETECTION', ['person', 'car', 'truck']],
  [122, 'OBJECT_DETECTION', 'AUTO_DETECTION', ['person', 'car', 'truck']],
  [71, 'OBJECT_DETECTION', 'LPD_YUNET', []],
  [136, 'OBJECT_DETECTION', 'YOLO_PLATE', []],
  [138, 'OBJECT_DETECTION', 'YOLO_PLATE', []],
  [23, 'OCR', 'LPRNET', []],
  [137, 'OCR', 'CHINESE_PLATE_CTC', []],
].map(([id, taskType, decoder, labels]) => ({
  modelVersionId: Number(id),
  artifactFormat: 'ONNX',
  device: 'CPU',
  sha256: 'a'.repeat(64),
  displayName: '同名模型',
  version: `v${id}`,
  runtimeManifest: {
    taskType: String(taskType),
    decoder: { type: String(decoder), labels: labels as string[] },
  },
}));
const snapshot: GatewaySnapshot = { models, tasks: [], historyDays: 7 };
const config: GatewayConfig = {
  taskId: 33,
  cameraId: 2,
  algorithmId: 72442,
  pipelineVersionId: 82668,
  configVersion: 2,
  runId: 'test',
  modelVersionId: 121,
  modelBindings: {
    'plate-ocr': 137,
    'plate-detector': 138,
    'vehicle-detector': 121,
  },
  pipeline: {
    nodes: [
      {
        id: 'vehicle-detector',
        type: 'DETECTOR',
        capabilityKey: 'detector.vehicle',
        modelId: 71031,
      },
      {
        id: 'plate-detector',
        type: 'DETECTOR',
        capabilityKey: 'detector.license-plate',
        modelId: 71035,
      },
      {
        id: 'plate-ocr',
        type: 'OCR',
        capabilityKey: 'ocr.license-plate',
        modelId: 71036,
      },
      { id: 'tracker', type: 'TRACKER', capabilityKey: 'tracker.iou' },
    ],
  },
  parameters: {},
  rule: null,
};
const catalog: ExecutableModelOption[] = models.map((model) => ({
  id: model.modelVersionId,
  modelId:
    (
      { 121: 71031, 122: 71031, 136: 71035, 138: 71035, 137: 71036 } as Record<
        number,
        number
      >
    )[model.modelVersionId] ?? 999,
  name: '同名模型',
  version: '1',
  format: 'ONNX',
}));
const options = (
  slot: string,
  source = config,
  inventory = snapshot,
  directory = catalog,
) =>
  gatewayRoleModelOptions(
    gatewayModelRoles(source).find((role) => role.slot === slot)!,
    source,
    inventory,
    directory,
  ).map((option) => option.value);

describe('gateway algorithm model roles', () => {
  it('shows all three declared roles in pipeline order and excludes the tracker', () => {
    expect(
      gatewayModelRoles(config).map((role) => [
        role.name,
        gatewayRoleModelId(config, role.slot),
      ]),
    ).toEqual([
      ['车辆检测模型', 121],
      ['车牌定位模型', 138],
      ['车牌文字识别模型', 137],
    ]);
  });

  it('filters by published model identity and execution contract, never display name', () => {
    expect(options('vehicle-detector')).toEqual([121, 122]);
    expect(options('plate-detector')).toEqual([136, 138]);
    expect(options('plate-ocr')).toEqual([137]);
  });

  it('retains current versions when offline or model-catalog access is unavailable', () => {
    expect(options('plate-detector', config, snapshot, [])).toEqual([138]);
  });

  it('does not offer compatible but uninstalled versions', () => {
    expect(
      options('plate-detector', config, {
        ...snapshot,
        models: models.filter((model) => model.modelVersionId !== 136),
      }),
    ).toEqual([138]);
  });

  it('preserves a missing installed model explicitly rather than selecting a different model', () => {
    const inventory = {
      ...snapshot,
      models: models.filter((model) => model.modelVersionId !== 137),
    };
    const role = gatewayModelRoles(config)[2]!;
    expect(gatewayRoleModelOptions(role, config, inventory, catalog)).toEqual([
      expect.objectContaining({
        value: 137,
        disabled: true,
        label: expect.stringContaining('未安装'),
      }),
    ]);
    expect(
      updateGatewayModelBindings(
        config,
        config.modelBindings,
        inventory,
        catalog,
      ).modelBindings,
    ).toEqual(config.modelBindings);
  });

  it('offers dedicated models only for the appropriate local algorithm role', () => {
    const local = structuredClone(config);
    for (const node of local.pipeline.nodes as Record<string, unknown>[])
      delete node.modelId;
    expect(options('plate-detector', local)).toEqual([71, 136, 138]);
    expect(options('plate-ocr', local)).toEqual([23, 137]);
    expect(options('vehicle-detector', local)).toEqual([121, 122]);
  });

  it('validates package model requirements for non-plate algorithms', () => {
    const packaged = {
      ...config,
      modelBindings: { person: 121 },
      pipeline: {
        algorithmPackage: {
          manifest: {
            models: [
              {
                slot: 'person',
                name: '人员定位',
                taskType: 'OBJECT_DETECTION',
                labels: ['person'],
                formats: ['ONNX'],
              },
            ],
          },
        },
      },
    };
    expect(gatewayModelRoles(packaged)[0]?.name).toBe('人员定位');
    expect(options('person', packaged)).toEqual([121, 122]);
  });
});

describe('save gateway model bindings', () => {
  it('keeps an unchanged three-model configuration exactly intact', () => {
    expect(
      updateGatewayModelBindings(
        config,
        config.modelBindings,
        snapshot,
        catalog,
      ),
    ).toEqual({
      modelVersionId: 121,
      modelBindings: config.modelBindings,
    });
  });

  it('changes the plate detector without replacing the vehicle detector or OCR', () => {
    const result = updateGatewayModelBindings(
      config,
      { ...config.modelBindings, 'plate-detector': 136 },
      snapshot,
      catalog,
    );
    expect(result).toEqual({
      modelVersionId: 121,
      modelBindings: { ...config.modelBindings, 'plate-detector': 136 },
    });
    expect(config.modelBindings['plate-detector']).toBe(138);
  });

  it('rejects an OCR version assigned to the vehicle detector', () => {
    expect(() =>
      updateGatewayModelBindings(
        config,
        { ...config.modelBindings, 'vehicle-detector': 137 },
        snapshot,
        catalog,
      ),
    ).toThrow('不兼容');
  });

  it('rejects a different published model asset even if its decoder serves the same role', () => {
    expect(() =>
      updateGatewayModelBindings(
        config,
        { ...config.modelBindings, 'plate-ocr': 23 },
        snapshot,
        catalog,
      ),
    ).toThrow('不兼容');
  });

  it('allows an explicitly declared model asset for another hardware target', () => {
    const multiTarget = structuredClone(config);
    const ocr = (multiTarget.pipeline.nodes as Record<string, unknown>[]).find(
      (node) => node.id === 'plate-ocr',
    )!;
    ocr.modelIds = [71036, 71039];
    const rk3588Model = {
      ...models.find((entry) => entry.modelVersionId === 137)!,
      modelVersionId: 143,
    };
    const inventory = { ...snapshot, models: [...models, rk3588Model] };
    const directory = [
      ...catalog,
      {
        id: 143,
        modelId: 71039,
        name: '现场低清车牌 OCR · RK3588 NPU',
        version: 'rk3588',
        format: 'RKNN',
      },
    ];
    expect(options('plate-ocr', multiTarget, inventory, directory)).toEqual([
      137, 143,
    ]);
  });

  it('changes shared-version roles independently and keeps primary metadata consistent', () => {
    const shared = {
      ...config,
      modelBindings: { ...config.modelBindings, person: 121 },
      pipeline: {
        ...config.pipeline,
        nodes: [
          ...(config.pipeline.nodes as object[]),
          { id: 'person', type: 'DETECTOR', capabilityKey: 'detector.person' },
        ],
      },
    };
    expect(
      updateGatewayModelBindings(
        shared,
        { ...shared.modelBindings, 'vehicle-detector': 122 },
        snapshot,
        catalog,
      ),
    ).toEqual({
      modelVersionId: 122,
      modelBindings: { ...shared.modelBindings, 'vehicle-detector': 122 },
    });
  });

  it('preserves unknown historical slots and does not silently remap them', () => {
    const historical = {
      ...config,
      modelBindings: { ...config.modelBindings, 'old.slot': 42 },
    };
    expect(gatewayModelRoles(historical).at(-1)).toMatchObject({
      slot: 'old.slot',
      declared: false,
    });
    expect(
      updateGatewayModelBindings(
        historical,
        historical.modelBindings,
        snapshot,
        catalog,
      ).modelBindings['old.slot'],
    ).toBe(42);
    expect(() =>
      updateGatewayModelBindings(
        historical,
        { ...historical.modelBindings, 'old.slot': 121 },
        snapshot,
        catalog,
      ),
    ).toThrow();
  });

  it('does not silently fill missing required roles or accept invalid IDs', () => {
    expect(() =>
      updateGatewayModelBindings(config, {}, snapshot, catalog),
    ).toThrow('请选择');
    expect(() =>
      updateGatewayModelBindings(
        config,
        { ...config.modelBindings, 'plate-ocr': 1.5 },
        snapshot,
        catalog,
      ),
    ).toThrow('请选择');
  });

  it('preserves legacy single-primary configurations', () => {
    const legacy = { ...config, pipeline: {}, modelBindings: {} };
    expect(
      updateGatewayModelBindings(legacy, { primary: 121 }, snapshot),
    ).toEqual({ modelVersionId: 121, modelBindings: { primary: 121 } });
  });
});
