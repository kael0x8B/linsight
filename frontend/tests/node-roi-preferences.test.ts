import type { App, Slot } from 'vue';

import type { AiVideoCameraApi } from '../apps/web-antd/src/api/ai-video/camera';
import type { GatewayTask } from '../apps/web-antd/src/api/ai-video/node/gateway';

import { createApp, h, nextTick, ref } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import CameraRecognitionOverlay from '../apps/web-antd/src/components/ai-video/camera-recognition-overlay.vue';
import { useDisplayPreferences } from '../apps/web-antd/src/components/ai-video/use-display-preferences';
import GatewayRecognitionPreview from '../apps/web-antd/src/views/ai-video/node/modules/gateway-recognition-preview.vue';

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }));
vi.mock('../packages/stores/src/index.ts', () => ({
  useAccessStore: () => ({ tenantId: 1 }),
  useUserStore: () => ({ userInfo: { id: 1 } }),
}));
vi.mock('@vben/icons', () => ({ IconifyIcon: { render: () => h('i') } }));
vi.mock('../apps/web-antd/src/api/request.ts', () => ({ requestClient: api }));
vi.mock('../apps/web-antd/src/api/ai-video/task/entry-access.ts', () => ({
  getEntryStationStatus: vi.fn(),
}));
vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) => key,
}));
vi.mock(
  '../apps/web-antd/src/components/ai-video/camera-preview-player.vue',
  () => ({
    default: {
      setup:
        (_: unknown, { slots }: { slots: { overlay?: Slot } }) =>
        () =>
          h('div', slots.overlay?.({})),
    },
  }),
);
vi.mock(
  '../apps/web-antd/src/components/ai-video/synchronized-recognition-video.vue',
  () => ({
    default: {
      props: {
        regions: Array,
        layers: Array,
        showRegions: Boolean,
      },
      setup:
        (props: {
          layers: { visible: boolean }[];
          regions: { title: string }[];
          showRegions: boolean;
        }) =>
        () =>
          h('output', {
            'data-regions': JSON.stringify(
              props.showRegions ? props.regions.map((v) => v.title) : [],
            ),
            'data-layers': JSON.stringify(props.layers.map((v) => v.visible)),
          }),
    },
  }),
);
vi.mock('ant-design-vue', () => ({
  Alert: {
    props: ['message'],
    setup: (props: { message: string }) => () =>
      h('p', { role: 'alert' }, props.message),
  },
  Button: {
    setup:
      (_: unknown, { slots }: { slots: { default?: Slot } }) =>
      () =>
        h('button', slots.default?.()),
  },
  Tooltip: {
    setup:
      (_: unknown, { slots }: { slots: { default?: Slot } }) =>
      () =>
        h('span', slots.default?.()),
  },
  Switch: {
    props: ['checked', 'disabled'],
    emits: ['change', 'update:checked'],
    setup:
      (
        props: { checked: boolean; disabled: boolean },
        { emit }: { emit: (event: string, value: boolean) => void },
      ) =>
      () =>
        h('input', {
          type: 'checkbox',
          checked: props.checked,
          disabled: props.disabled,
          onChange: (event: Event) =>
            emit('change', (event.target as HTMLInputElement).checked),
        }),
  },
}));

let app: App | undefined;
let root: HTMLElement;
let cameraId = 100;
let stored: string[];
beforeEach(() => {
  vi.clearAllMocks();
  const storage = new Map<string, string>();
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
  });
  stored = ['entry-77'];
  api.get.mockImplementation(async () => [...stored]);
  api.put.mockImplementation(
    async (_path: string, value: { hiddenLayers: string[] }) => {
      stored = [...value.hiddenLayers];
    },
  );
});
afterEach(() => {
  app?.unmount();
  root?.remove();
  vi.unstubAllGlobals();
});
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
}
async function mount(local = false) {
  const id = ++cameraId;
  const tasks: GatewayTask[] = ['车牌识别', '安全帽识别'].map(
    (name, index) => ({
      name,
      revision: 1,
      appliedRevision: 1,
      enabled: true,
      status: { status: 'RUNNING', metrics: {} },
      config: {
        taskId: 33 + index,
        cameraId: id,
        runId: `run-${index}`,
        algorithmId: index + 1,
        pipelineVersionId: 1,
        modelVersionId: 1,
        configVersion: 1,
        modelBindings: {},
        pipeline: {},
        parameters: {},
        rule: {
          regions: [
            {
              id: `region-${index}`,
              name,
              points: [
                { x: 0.1, y: 0.1 },
                { x: 0.8, y: 0.1 },
                { x: 0.8, y: 0.8 },
                { x: 0.1, y: 0.8 },
              ],
            },
          ],
        },
      },
    }),
  );
  const camera: AiVideoCameraApi.Camera = {
    id,
    code: `camera-${id}`,
    name: '摄像头',
    groupId: 1,
    protocol: 'RTSP',
    host: 'camera',
    port: 554,
    status: 0,
    recognitionCapabilities: tasks.map((task) => ({
      taskId: task.config.taskId,
      taskName: task.name,
      algorithmName: task.name,
      nodeId: 1,
      actualStatus: 'RUNNING',
      desiredStatus: 'RUNNING',
      effectiveStatus: 'RUNNING',
      validationOnly: true,
      regions: task.config.rule
        ?.regions as AiVideoCameraApi.CameraCapability['regions'],
    })),
  };
  let prefs!: ReturnType<typeof useDisplayPreferences>;
  root = document.createElement('div');
  document.body.append(root);
  app = createApp({
    setup() {
      prefs = useDisplayPreferences(ref(id), local);
      return () =>
        h('div', [
          h(CameraRecognitionOverlay, { camera, frames: {} }),
          h(GatewayRecognitionPreview, {
            task: tasks[0]!,
            tasks,
            cameraName: camera.name,
            title: '预览',
            local,
            transport: vi.fn(),
          }),
        ]);
    },
  });
  app.mount(root);
  await settle();
  return { prefs, id };
}
function regions() {
  return [...root.querySelectorAll('output')].map((element) =>
    JSON.parse(element.dataset.regions || '[]'),
  );
}
async function toggle(name: string) {
  const input = root.querySelector<HTMLInputElement>(
    `input[aria-label="${name}"]`,
  );
  expect(input).not.toBeNull();
  input!.click();
  await settle();
}

describe('per-algorithm recognition region preferences', () => {
  it('toggles only one algorithm across live preview and gateway, preserves annotations and reloads saved preferences', async () => {
    const { prefs } = await mount();
    expect(regions()).toEqual([
      ['车牌识别', '安全帽识别'],
      ['车牌识别', '安全帽识别'],
    ]);
    await toggle('车牌识别识别区域');
    expect(regions()).toEqual([['安全帽识别'], ['安全帽识别']]);
    expect(stored).toEqual(['entry-77', 'roi-task-33']);
    expect(
      [...root.querySelectorAll('output')].map((el) => el.dataset.layers),
    ).toEqual(['[true,true]', '[true,true]']);
    await toggle('安全帽识别识别区域');
    expect(regions()).toEqual([[], []]);
    await toggle('车牌识别识别区域');
    expect(regions()).toEqual([['车牌识别'], ['车牌识别']]);
    expect(stored).toEqual(['entry-77', 'roi-task-34']);
    await prefs.reload();
    await settle();
    expect(regions()).toEqual([['车牌识别'], ['车牌识别']]);
    await toggle('车牌识别图层');
    expect(regions()).toEqual([['车牌识别'], ['车牌识别']]);
  });

  it('retires the legacy all-algorithm switch without losing individual preferences', async () => {
    stored = ['recognition-regions', 'roi-task-33', 'entry-77'];
    await mount();
    expect(regions()).toEqual([['安全帽识别'], ['安全帽识别']]);
    await toggle('安全帽识别识别区域');
    expect(stored).toEqual(['roi-task-33', 'entry-77', 'roi-task-34']);
  });

  it('restores only the failed preference and reports a save failure', async () => {
    await mount();
    api.put.mockRejectedValueOnce(new Error('offline'));
    await toggle('车牌识别识别区域');
    expect(regions()).toEqual([
      ['车牌识别', '安全帽识别'],
      ['车牌识别', '安全帽识别'],
    ]);
    expect(root.querySelector('[role="alert"]')?.textContent).toContain(
      '保存失败',
    );
    expect(stored).toEqual(['entry-77']);
  });

  it('keeps local gateway preferences independent of the platform and saves each algorithm locally', async () => {
    const { id, prefs } = await mount(true);
    await toggle('车牌识别识别区域');
    expect(regions()).toEqual([['车牌识别', '安全帽识别'], ['安全帽识别']]);
    expect(
      JSON.parse(localStorage.getItem(`edge-display:${id}`) || '[]'),
    ).toEqual(['roi-task-33']);
    expect(api.put).not.toHaveBeenCalled();
    await prefs.reload();
    await settle();
    expect(regions()).toEqual([['车牌识别', '安全帽识别'], ['安全帽识别']]);
  });
});
