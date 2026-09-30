/* eslint-disable vue/one-component-per-file -- Minimal component doubles exercise the modal's deployment orchestration. */
import type { App } from 'vue';

import { createApp, h, nextTick } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Deployment from '../apps/web-antd/src/views/ai-video/algorithm/modules/package-task-modal.vue';

const state = vi.hoisted(() => ({
  forms: [] as Array<{
    schema: Array<{
      componentProps?:
        | (() => Record<string, unknown>)
        | Record<string, unknown>;
      fieldName: string;
    }>;
    values: Record<string, unknown>;
  }>,
  options: {} as {
    onConfirm: () => Promise<void>;
    onOpenChange: (open: boolean) => Promise<void>;
  },
  modalState: {} as Record<string, unknown>,
  getDeployments: vi.fn(),
  deploy: vi.fn(),
  create: vi.fn(),
  start: vi.fn(),
  resolve: vi.fn(),
  can: vi.fn(),
  close: vi.fn(),
  selectPipeline: vi.fn(),
  warnings: vi.fn(),
}));
const manifest = {
  name: '安全帽识别',
  version: '1.0.3',
  eventType: 'SAFETY_HELMET',
  models: [{ slot: 'person' }, { slot: 'ppe' }],
  parameterSchema: { properties: {} },
  defaultParameters: { personConfidence: 0.5, ppeConfidence: 0.5 },
};
vi.mock('../apps/web-antd/src/api/ai-video/algorithm/package.ts', () => ({
  listAlgorithmPackages: async () => [
    {
      algorithmId: 2,
      pipelineVersionId: 3,
      status: 'PUBLISHED',
      current: true,
      manifest,
    },
  ],
  resolveAlgorithmPackage: state.resolve,
}));
vi.mock('../apps/web-antd/src/api/ai-video/algorithm/index.ts', () => ({
  getRunnableAlgorithms: async () => [
    { id: 2, capabilityKey: 'package.helmet' },
    {
      id: 72442,
      name: '厂区车辆识别',
      capabilityKey: 'ocr.license-plate',
      eventType: 'VEHICLE_PLATE_RECOGNIZED',
      currentPipelineVersionId: 82668,
      pipelineAcceptanceStatus: 'PENDING',
      status: 0,
    },
  ],
}));
vi.mock('../apps/web-antd/src/api/ai-video/camera/index.ts', () => ({
  getCameraPage: async () => ({
    list: [{ id: 4, name: '摄像头', status: 0 }],
    total: 1,
  }),
}));
vi.mock('../apps/web-antd/src/api/ai-video/node/index.ts', () => ({
  getNodeSimpleList: async () => [
    { id: 5, name: '新盒子', status: 0, onlineStatus: 1 },
  ],
}));
vi.mock('../apps/web-antd/src/api/ai-video/node/gateway.ts', () => ({
  gatewayRequestId: () => 'stable-test-id',
  platformGateway: vi.fn(),
}));
vi.mock('../apps/web-antd/src/api/ai-video/model/index.ts', () => ({
  deployModelVersion: state.deploy,
  getNodeModelDeployments: state.getDeployments,
}));
vi.mock('../apps/web-antd/src/api/ai-video/task/index.ts', () => ({
  createTask: state.create,
  startTask: state.start,
  updateTask: vi.fn(),
}));
vi.mock('../apps/web-antd/src/api/ai-video/rule/index.ts', () => ({
  getPublishedRules: async () => [],
  getRuleVersions: vi.fn(),
  createRule: vi.fn(),
  publishRuleVersion: vi.fn(),
  saveRuleVersion: vi.fn(),
  validateRuleVersion: vi.fn(),
}));
vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) => key,
}));
vi.mock('../packages/effects/access/src/index.ts', () => ({
  useAccess: () => ({ hasAccessByCodes: state.can }),
}));
vi.mock('../apps/web-antd/src/adapter/form.ts', () => ({
  useVbenForm: (options: {
    schema: (typeof state.forms)[number]['schema'];
  }) => {
    const values: Record<string, unknown> = {};
    state.forms.push({ ...options, values });
    return [
      () => h('div'),
      {
        resetForm: async () => {
          Object.keys(values).forEach((key) => delete values[key]);
        },
        setValues: async (input: Record<string, unknown>) =>
          Object.assign(values, input),
        setFieldValue: async (key: string, value: unknown) => {
          values[key] = value;
        },
        getValues: async () => values,
        validate: async () => ({ valid: true }),
      },
    ];
  },
}));
vi.mock('../packages/effects/common-ui/src/index.ts', () => ({
  useVbenModal: (options: typeof state.options) => {
    state.options = options;
    return [
      (_props: unknown, { slots }: { slots: { default: () => unknown } }) =>
        h('div', slots.default()),
      {
        getData: () => ({
          nodeId: 5,
          nodeName: '新盒子',
          pipelineVersionId: 3,
        }),
        setState: (values: Record<string, unknown>) =>
          Object.assign(state.modalState, values),
        lock: vi.fn(),
        unlock: vi.fn(),
        close: state.close,
      },
    ];
  },
}));
vi.mock('ant-design-vue', async () => {
  const { defineComponent, h } = await import('vue');
  const content = defineComponent({
    setup:
      (_props, { slots }) =>
      () =>
        h('div', slots.default?.()),
  });
  return {
    Alert: content,
    Button: content,
    Select: content,
    TabPane: content,
    Tabs: content,
    message: { warning: state.warnings, success: vi.fn() },
  };
});
vi.mock(
  '../apps/web-antd/src/views/ai-video/algorithm/modules/package-parameters.vue',
  async () => {
    const { defineComponent, h } = await import('vue');
    return {
      default: defineComponent({
        setup: (_props, { expose }) => {
          expose({ values: async () => manifest.defaultParameters });
          return () => h('div');
        },
      }),
    };
  },
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/gateway-rule-editor.vue',
  async () => {
    const { defineComponent, h } = await import('vue');
    return {
      default: defineComponent({
        setup: (_props, { expose }) => {
          expose({ validate: () => true });
          return () => h('div');
        },
      }),
    };
  },
);

let app: App;
let root: HTMLElement;
beforeEach(() => {
  vi.clearAllMocks();
  state.forms = [];
  state.modalState = {};
  state.can.mockReturnValue(true);
  state.resolve.mockResolvedValue({
    manifest,
    supported: true,
    bindings: { person: 121, ppe: 122 },
    roles: {
      person: [{ id: 121, installed: false, deployable: true }],
      ppe: [{ id: 122, installed: false, deployable: true }],
    },
  });
  state.create.mockResolvedValue(8);
  state.getDeployments.mockResolvedValue(
    [121, 122].map((id) => ({
      modelVersionId: id,
      actualStatus: 'READY',
      configVersion: 1,
    })),
  );
  root = document.createElement('div');
  document.body.append(root);
  app = createApp({
    render: () => h(Deployment, { onSelectPipeline: state.selectPipeline }),
  });
  app.mount(root);
});
afterEach(() => {
  app.unmount();
  root.remove();
});

describe('gateway algorithm deployment modal', () => {
  it('offers the published vehicle pipeline and routes it to the pipeline configurator for this box', async () => {
    await state.options.onOpenChange(true);
    const field = state.forms[0]?.schema.find(
      (item) => item.fieldName === 'packageId',
    );
    const props = (field?.componentProps as () => {
      onChange: (value: number) => void;
      options: Array<{ label: string; value: number }>;
    })();
    expect(props.options).toContainEqual(
      expect.objectContaining({
        label: '厂区车辆识别 · 内置编排',
        searchText: expect.stringContaining('车号'),
        value: -72442,
      }),
    );
    props.onChange(-72442);
    expect(state.close).toHaveBeenCalled();
    expect(state.selectPipeline).toHaveBeenCalledWith(72442, 5, 4);
    expect(state.deploy).not.toHaveBeenCalled();
    expect(state.create).not.toHaveBeenCalled();
  });

  it('installs dependencies and starts with defaults without visiting advanced settings', async () => {
    await state.options.onOpenChange(true);
    await nextTick();
    state.getDeployments.mockResolvedValueOnce([]);
    await state.options.onConfirm();
    expect(state.deploy.mock.calls).toEqual([
      [121, 5],
      [122, 5],
    ]);
    expect(state.create).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '安全帽识别',
        nodeId: 5,
        cameraId: 4,
        pipelineVersionId: 3,
        modelBindings: { person: 121, ppe: 122 },
        parameters: expect.objectContaining({
          algorithm: manifest.defaultParameters,
          sampleFps: 2,
        }),
      }),
    );
    expect(state.start).toHaveBeenCalledWith(8);
  });

  it('reuses installed dependencies', async () => {
    await state.options.onOpenChange(true);
    await nextTick();
    await state.options.onConfirm();
    expect(state.deploy).not.toHaveBeenCalled();
    expect(state.start).toHaveBeenCalledWith(8);
  });

  it('does not create or start a task after an installation failure', async () => {
    await state.options.onOpenChange(true);
    await nextTick();
    state.getDeployments.mockResolvedValue([
      {
        modelVersionId: 121,
        actualStatus: 'FAILED',
        configVersion: 1,
        errorMessage: '校验失败',
      },
    ]);
    await state.options.onConfirm();
    expect(state.create).not.toHaveBeenCalled();
    expect(state.start).not.toHaveBeenCalled();
    expect(state.close).not.toHaveBeenCalled();
  });

  it('blocks incomplete or incompatible resources before sending deployment commands', async () => {
    state.resolve.mockResolvedValue({
      manifest,
      supported: true,
      bindings: { person: 121 },
      roles: { person: [{ id: 121, deployable: true }], ppe: [] },
    });
    await state.options.onOpenChange(true);
    await nextTick();
    expect(state.modalState.confirmDisabled).toBe(true);
    await state.options.onConfirm();
    expect(state.deploy).not.toHaveBeenCalled();
    expect(state.create).not.toHaveBeenCalled();
  });

  it('does not deploy without model deployment permission', async () => {
    state.can.mockImplementation(
      (codes: string[]) => !codes.includes('ai-video:model:deploy'),
    );
    await state.options.onOpenChange(true);
    await nextTick();
    await state.options.onConfirm();
    expect(state.deploy).not.toHaveBeenCalled();
    expect(state.create).not.toHaveBeenCalled();
  });
});
