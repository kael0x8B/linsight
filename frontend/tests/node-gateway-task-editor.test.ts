/* eslint-disable vue/one-component-per-file -- Form/modal doubles keep the real editor and parameter renderer under test. */
import type { App } from 'vue';

import type { GatewayTask } from '../apps/web-antd/src/api/ai-video/node/gateway';

import { createApp, defineComponent, h, nextTick, ref } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import Workbench from '../apps/web-antd/src/views/ai-video/node/gateway-workbench.vue';

const state = vi.hoisted(() => ({
  forms: [] as Array<{
    schema: Array<{
      componentProps?: (() => Record<string, unknown>) | Record<string, unknown>;
      fieldName: string;
    }>;
    values: Record<string, unknown>;
  }>,
  modals: [] as Array<{
    onClosed?: () => void;
    onConfirm?: () => Promise<void>;
    title?: string;
  }>,
  error: vi.fn(),
  warning: vi.fn(),
  libraries: vi.fn(),
  people: vi.fn(),
  catalog: vi.fn(),
}));
vi.mock('../packages/effects/access/src/index.ts', () => ({
  useAccess: () => ({ hasAccessByCodes: () => true }),
}));
vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) => key,
}));
vi.mock('../apps/web-antd/src/api/ai-video/model/index.ts', () => ({
  getExecutableModelOptions: state.catalog,
}));
vi.mock(
  '../apps/web-antd/src/api/ai-video/recognition-library/index.ts',
  () => ({
    getRecognitionLibraryPage: state.libraries,
    getRecognitionEntryPage: state.people,
  }),
);
vi.mock('../apps/web-antd/src/adapter/form.ts', async () => ({
  z: (await import('../packages/@core/ui-kit/form-ui/src/index')).z,
  useVbenForm: (options: {
    schema: (typeof state.forms)[number]['schema'];
  }) => {
    const model = {
      schema: options.schema,
      values: {} as Record<string, unknown>,
    };
    state.forms.push(model);
    return [
      () => h('div'),
      {
        setState: async ({ schema }: Pick<typeof model, 'schema'>) => {
          model.schema = schema;
        },
        resetForm: async () => {
          model.values = {};
        },
        setValues: async (values: Record<string, unknown>) =>
          Object.assign(model.values, values),
        getValues: async () => model.values,
        validate: async () => ({ valid: true }),
      },
    ];
  },
}));
vi.mock('../apps/web-antd/src/adapter/vxe-table.ts', () => ({
  TableAction: () => h('div'),
  useVbenVxeGrid: () => [() => h('div'), { setGridOptions: vi.fn() }],
}));
vi.mock('../packages/effects/common-ui/src/index.ts', () => ({
  Page: defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('main', slots.default?.()),
  }),
  confirm: vi.fn(),
  useVbenModal: (options: (typeof state.modals)[number]) => {
    state.modals.push(options);
    const open = ref(false);
    return [
      defineComponent({
        setup:
          (_, { slots }) =>
          () =>
            open.value
              ? h('article', { 'data-modal': options.title }, slots.default?.())
              : null,
      }),
      {
        open: () => {
          open.value = true;
        },
        close: () => {
          open.value = false;
          options.onClosed?.();
        },
        lock: vi.fn(),
        unlock: vi.fn(),
        setState: vi.fn(),
      },
    ];
  },
}));
vi.mock('../apps/web-antd/node_modules/ant-design-vue', () => {
  const content = defineComponent({
    setup:
      (_, { slots }) =>
      () =>
        h('div', slots.default?.()),
  });
  return {
    Alert: defineComponent({
      props: { message: { type: String, default: '' } },
      setup: (props) => () => h('p', { role: 'alert' }, props.message),
    }),
    Button: content,
    Empty: content,
    Input: Object.assign(content, { TextArea: content }),
    InputNumber: content,
    Select: content,
    TabPane: defineComponent({
      props: { tab: { type: String, default: '' } },
      setup:
        (props, { slots }) =>
        () =>
          h('section', { 'data-tab': props.tab }, slots.default?.()),
    }),
    Tabs: content,
    Tag: content,
    Upload: Object.assign(content, { Dragger: content }),
    message: {
      loading: () => vi.fn(),
      error: state.error,
      warning: state.warning,
      success: vi.fn(),
      info: vi.fn(),
    },
  };
});
vi.mock(
  '../apps/web-antd/src/views/ai-video/algorithm/modules/local-package-modal.vue',
  () => ({ default: {} }),
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/algorithm/modules/plate-task-modal.vue',
  () => ({ default: {} }),
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/gateway-event-delivery.vue',
  () => ({ default: { render: () => null } }),
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/gateway-recognition-preview.vue',
  () => ({ default: { render: () => null } }),
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/image-recognition-modal.vue',
  () => ({ default: {} }),
);
vi.mock(
  '../apps/web-antd/src/components/ai-video/camera-preview-player.vue',
  () => ({ default: { render: () => null } }),
);
vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/gateway-rule-editor.vue',
  () => ({
    default: defineComponent({
      setup: (_, { expose }) => {
        expose({ validate: () => true });
        return () => h('div');
      },
    }),
  }),
);

function task(packaged = false): GatewayTask {
  return {
    name: packaged ? '安全帽' : '车辆',
    revision: 16,
    appliedRevision: 16,
    enabled: true,
    status: { status: 'RUNNING', metrics: {} },
    config: {
      taskId: packaged ? 34 : 33,
      runId: 'same-running-task',
      cameraId: 2,
      algorithmId: 3,
      pipelineVersionId: 4,
      configVersion: 2,
      modelVersionId: 121,
      modelBindings: packaged ? { person: 121, ppe: 122 } : { ocr: 139 },
      pipeline: packaged
        ? {
            algorithmPackage: {
              manifest: {
                code: 'helmet',
                version: '1.0.3',
                name: '安全帽',
                models: [
                  { slot: 'person', name: '人员检测模型' },
                  { slot: 'ppe', name: '穿戴模型' },
                ],
                parameterSchema: {
                  type: 'object',
                  properties: {
                    personConfidence: { type: 'number', title: '人员置信度' },
                    ppeConfidence: { type: 'number', title: '穿戴置信度' },
                    showPersonBox: { type: 'boolean', title: '显示人员框' },
                  },
                },
                defaultParameters: {
                  personConfidence: 0.5,
                  ppeConfidence: 0.5,
                  showPersonBox: false,
                },
              },
            },
          }
        : {
            nodes: [
              { id: 'ocr', type: 'OCR', capabilityKey: 'ocr.license-plate' },
            ],
          },
      parameters: {
        schemaVersion: '1.0',
        confidence: 0.5,
        sampleFps: 4,
        personConfidence: 0.5,
        ocrMinConfidence: 0.75,
        ocrMinVotes: 3,
        ocrVoteFrames: 5,
        customRuntimeSetting: 42,
        algorithm: packaged
          ? {
              personConfidence: 0.25,
              ppeConfidence: 0.5,
              showPersonBox: false,
              custom: 'keep',
            }
          : {},
      },
      ruleId: 7,
      ruleVersionId: 8,
      rule: {
        eventType: 'SAFETY_HELMET',
        regions: [
          {
            points: [
              { x: 0.1, y: 0.2 },
              { x: 0.4, y: 0.2 },
              { x: 0.4, y: 0.5 },
            ],
          },
        ],
      },
    },
  };
}
let app: App;
let root: HTMLElement;
let actual: GatewayTask;
let capabilities: string[];
const transport = vi.fn();
const flush = async () => {
  for (let i = 0; i < 12; i++) await nextTick();
};
const form = (key: string) =>
  state.forms.find((item) =>
    item.schema.some((field) => field.fieldName === key),
  )!;
const save = () =>
  state.modals.find((item) => item.title === '编辑算法配置')!.onConfirm!();
function mounted(local = false) {
  app = createApp(Workbench, { transport, section: 'preview', local });
  return app.mount(root) as InstanceType<typeof Workbench>;
}
beforeEach(() => {
  vi.clearAllMocks();
  state.forms = [];
  state.modals = [];
  state.catalog.mockResolvedValue([]);
  actual = task();
  capabilities = [];
  transport.mockImplementation(async (action: string) => {
    if (action === 'snapshot')
      return { tasks: [actual], models: [], historyDays: 7, capabilities };
    if (action === 'overlay') return {};
    if (action === 'task.capacity.preflight') return { allowed: true };
    if (action === 'task.save')
      return { ...actual, revision: 17, appliedRevision: 17 };
    throw new Error(`Unexpected action: ${action}`);
  });
  root = document.createElement('div');
  document.body.append(root);
});
afterEach(() => {
  app?.unmount();
  root.remove();
});

describe('one gateway editor for deployed pipelines and packages', () => {
  it.each([false, true])('switches a stored stream through either entrance (local=%s)', async (local) => {
    capabilities = ['task.stream-switch.v1'];
    actual.platformManaged = true;
    actual.availableStreamTypes = ['MAIN', 'SUB'];
    actual.config.parameters.streamType = 'MAIN';
    const vm = mounted(local);
    await flush();
    await vm.edit(actual);
    await flush();
    const streamField = form('streamType').schema.find((item) => item.fieldName === 'streamType')!;
    expect(typeof streamField.componentProps === 'function' && streamField.componentProps().disabled).toBe(false);
    form('streamType').values.streamType = 'SUB';
    await save();
    const payload = transport.mock.calls.find(([action]) => action === 'task.save')![1];
    expect(payload.configuration.parameters.streamType).toBe('SUB');
    expect(payload.expectedRevision).toBe(16);
    expect(payload).not.toHaveProperty('syncStreamUrls');
    if (local) expect(payload).not.toHaveProperty('streamTypeChanged');
    else expect(payload.streamTypeChanged).toBe(false); // Device resolves its own saved address.
  });

  it('seeds missing addresses only through the platform and keeps entered addresses in the same save', async () => {
    capabilities = ['task.stream-switch.v1'];
    actual.platformManaged = true;
    const vm = mounted(false);
    await flush();
    await vm.edit(actual);
    await flush();
    form('mainStreamUrl').values.mainStreamUrl = 'rtsp://camera/custom-main';
    form('streamType').values.streamType = 'MAIN';
    await save();
    for (const action of ['task.capacity.preflight', 'task.save']) {
      const payload = transport.mock.calls.find(([name]) => name === action)![1];
      expect(payload.syncStreamUrls).toBe(true);
      expect(payload.configuration.streamUrls).toEqual({ MAIN: 'rtsp://camera/custom-main' });
    }
  });

  it.each([false, true])(
    'keeps platform routing hints out of local saves (local=%s)',
    async (local) => {
      actual.platformManaged = true;
      actual.config.parameters.streamType = 'MAIN';
      const vm = mounted(local);
      await flush();
      await vm.edit(actual);
      await flush();
      form('streamType').values.streamType = 'SUB';
      form('ocrMinConfidence').values.ocrMinConfidence = 0.8;
      await save();
      const payload = transport.mock.calls.find(
        ([action]) => action === 'task.save',
      )![1];
      expect(payload.configuration.parameters.ocrMinConfidence).toBe(0.8);
      expect(payload.expectedRevision).toBe(16);
      if (local) {
        expect(payload).not.toHaveProperty('platformManaged');
        expect(payload).not.toHaveProperty('streamTypeChanged');
        expect(payload.configuration.parameters.streamType).toBe('MAIN');
      } else {
        expect(payload).toMatchObject({
          platformManaged: true,
          streamTypeChanged: true,
        });
        expect(payload.configuration.parameters.streamType).toBe('SUB');
      }
    },
  );

  it('refreshes actual parameters and revision before saving a legacy pipeline', async () => {
    const stale = task();
    stale.revision = 1;
    stale.config.parameters.sampleFps = 1;
    const vm = mounted();
    await flush();
    await vm.edit(stale);
    await flush();
    expect(form('sampleFps').values.sampleFps).toBe(4);
    expect(
      [...root.querySelectorAll('[data-modal="编辑算法配置"] [data-tab]')].map(
        (el) => el.getAttribute('data-tab'),
      ),
    ).toEqual(['识别参数', '告警条件', '高级设置']);
    form('ocrMinConfidence').values.ocrMinConfidence = 0.8;
    await save();
    const payload = transport.mock.calls.find(
      ([action]) => action === 'task.save',
    )![1];
    expect(payload).toMatchObject({
      taskId: 33,
      expectedRevision: 16,
      name: '车辆',
      requestId: expect.any(String),
    });
    expect(payload.enabled).toBeUndefined();
    expect(payload.configuration).toMatchObject({
      runId: actual.config.runId,
      cameraId: 2,
      algorithmId: 3,
      pipelineVersionId: 4,
      modelBindings: actual.config.modelBindings,
      ruleId: 7,
      ruleVersionId: 8,
      rule: actual.config.rule,
      parameters: {
        sampleFps: 4,
        ocrMinConfidence: 0.8,
        customRuntimeSetting: 42,
        algorithm: {},
      },
    });
    expect(payload.configuration.parameters.name).toBeUndefined();
    expect(payload.configuration.sourceUrl).toBeUndefined();
  });

  it.each([false, true])(
    'edits a running package in the same editor (local=%s)',
    async (local) => {
      actual = task(true);
      const vm = mounted(local);
      await flush();
      await vm.edit(actual);
      await flush();
      expect(form('personConfidence').values.personConfidence).toBe(0.25);
      expect(root.querySelector('[data-tab="高级设置"]')).not.toBeNull();
      form('personConfidence').values.personConfidence = 0.3;
      form('showPersonBox').values.showPersonBox = true;
      await save();
      const payload = transport.mock.calls.find(
        ([action]) => action === 'task.save',
      )![1];
      expect(payload.configuration.parameters).toMatchObject({
        personConfidence: 0.5,
        algorithm: {
          personConfidence: 0.3,
          ppeConfidence: 0.5,
          showPersonBox: true,
          custom: 'keep',
        },
      });
      expect(payload.configuration.modelBindings).toEqual({
        person: 121,
        ppe: 122,
      });
      expect(state.warning).not.toHaveBeenCalled();
      if (local) expect(state.catalog).not.toHaveBeenCalled();
    },
  );

  it('uses synced gateway library choices and preserves unexposed nested settings', async () => {
    actual = task(true);
    const manifest = (
      actual.config.pipeline.algorithmPackage as {
        manifest: Record<string, unknown>;
      }
    ).manifest;
    manifest.parameterSchema = {
      type: 'object',
      properties: {
        libraryId: { type: 'integer', 'x-widget': 'person-library' },
        peopleIds: {
          type: 'array',
          'x-widget': 'people',
          'x-library-field': 'libraryId',
        },
        tuning: {
          type: 'object',
          properties: { threshold: { type: 'number' } },
        },
      },
    };
    actual.config.parameters.algorithm = {
      libraryId: 1,
      peopleIds: [11],
      tuning: { threshold: 0.4, hidden: 42 },
    };
    actual.resourceOptions = {
      libraryId: [{ label: '本机人员库', value: 1 }],
      peopleIds: [{ label: '已同步人员', value: 11 }],
    };
    const vm = mounted();
    await flush();
    await vm.edit(actual);
    await flush();
    const parameters = form('libraryId');
    expect(
      parameters.schema.find((item) => item.fieldName === 'libraryId')
        ?.componentProps,
    ).toMatchObject({
      disabled: true,
      options: actual.resourceOptions.libraryId,
    });
    expect(state.libraries).not.toHaveBeenCalled();
    expect(state.people).not.toHaveBeenCalled();
    parameters.values.tuning__threshold = 0.6;
    await save();
    expect(
      transport.mock.calls.find(([action]) => action === 'task.save')![1]
        .configuration.parameters.algorithm,
    ).toEqual({
      libraryId: 1,
      peopleIds: [11],
      tuning: { threshold: 0.6, hidden: 42 },
    });
  });

  it.each(['offline', 'removed'])(
    'does not open stale configuration when the gateway is %s',
    async (reason) => {
      const vm = mounted();
      await flush();
      if (reason === 'offline')
        transport.mockRejectedValueOnce(new Error('网关离线'));
      else
        transport.mockResolvedValueOnce({
          tasks: [],
          models: [],
          historyDays: 7,
        });
      await vm.edit(actual);
      await flush();
      expect(state.error).toHaveBeenCalledOnce();
      expect(root.querySelector('[data-modal="编辑算法配置"]')).toBeNull();
      expect(
        transport.mock.calls.some(([action]) => action === 'task.save'),
      ).toBe(false);
    },
  );

  it('retains the draft and surfaces revision conflicts without retrying an overwrite', async () => {
    const vm = mounted();
    await flush();
    await vm.edit(actual);
    await flush();
    transport.mockImplementation(async (action: string) => {
      if (action === 'task.capacity.preflight') return { allowed: true };
      if (action === 'task.save')
        throw new Error('配置版本已变更，请刷新后重试');
    });
    await save();
    await flush();
    expect(root.querySelector('[data-modal="编辑算法配置"]')).not.toBeNull();
    expect(root.textContent).toContain('配置版本已变更，请刷新后重试');
    expect(
      transport.mock.calls.filter(([action]) => action === 'task.save'),
    ).toHaveLength(1);
  });

  it('rejects a plate vote count larger than its window before sending configuration', async () => {
    const vm = mounted();
    await flush();
    await vm.edit(actual);
    await flush();
    form('ocrMinVotes').values.ocrMinVotes = 8;
    await save();
    await flush();
    expect(root.textContent).toContain('一致识别帧数不能超过投票窗口帧数');
    expect(
      transport.mock.calls.some(([action]) => action === 'task.save'),
    ).toBe(false);
  });
});
