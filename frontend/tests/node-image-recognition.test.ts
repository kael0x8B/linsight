/* eslint-disable vue/one-component-per-file, vue/require-prop-types -- Minimal host components keep tests focused on the image workflow. */
import type { App } from 'vue';

import { createApp, h, nextTick } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import ImageRecognition from '../apps/web-antd/src/views/ai-video/node/modules/image-recognition-modal.vue';

vi.mock(
  '../apps/web-antd/src/views/ai-video/node/modules/image-validation-panel.vue',
  () => ({ default: () => null }),
);

const state = vi.hoisted(() => ({
  open: (_value: boolean) => {},
  select: (_file: File): unknown => undefined,
  supported: true,
  transport: vi.fn(),
}));
vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) => key,
}));
vi.mock('../packages/effects/common-ui/src/index.ts', () => ({
  useVbenModal(options: { onOpenChange: (value: boolean) => void }) {
    state.open = options.onOpenChange;
    return [
      (_props: unknown, { slots }: { slots: { default: () => unknown } }) =>
        h('div', slots.default()),
      {
        getData: () => ({
          supported: state.supported,
          task: { name: 'Vehicle', config: { taskId: 17 } },
        }),
      },
    ];
  },
}));
vi.mock('ant-design-vue', async () => {
  const { defineComponent, h } = await import('vue');
  const content = defineComponent({
    props: ['message'],
    setup:
      (props, { slots }) =>
      () =>
        h('div', [props.message, slots.default?.()]),
  });
  const button = defineComponent({
    props: ['disabled', 'loading'],
    setup:
      (props, { slots, attrs }) =>
      () =>
        h(
          'button',
          { ...attrs, disabled: props.disabled || props.loading },
          slots.default?.(),
        ),
  });
  const dragger = defineComponent({
    props: ['beforeUpload'],
    setup(props) {
      state.select = (file) => props.beforeUpload(file);
      return () => h('div');
    },
  });
  return {
    Alert: content,
    Button: button,
    Empty: content,
    Switch: content,
    Tag: content,
    Upload: { Dragger: dragger, LIST_IGNORE: 'ignore' },
  };
});
vi.mock(
  '../apps/web-antd/src/components/ai-video/recognition-frame.vue',
  async () => {
    const { defineComponent, h } = await import('vue');
    return {
      default: defineComponent({
        props: ['frame'],
        setup: (props) => () =>
          h('div', { 'data-preview': '', 'data-frame': props.frame?.frameId }),
      }),
    };
  },
);
vi.mock('../apps/web-antd/src/adapter/vxe-table.ts', async () => {
  const { h, reactive } = await import('vue');
  return {
    useVbenVxeGrid({ gridOptions }: { gridOptions: Record<string, unknown> }) {
      const options = reactive(gridOptions) as {
        columns: { field: string }[];
        data: { class: string }[];
      };
      return [
        () =>
          h('table', [
            h(
              'thead',
              options.columns.map((column) => h('th', column.field)),
            ),
            h(
              'tbody',
              options.data.map((object) => h('tr', object.class)),
            ),
          ]),
        {
          setGridOptions: (values: Record<string, unknown>) =>
            Object.assign(options, values),
        },
      ];
    },
  };
});

const response = {
  taskId: 17,
  cameraId: 1,
  frameId: 'image-1',
  timestamp: '2026-09-22T01:00:00Z',
  sourceWidth: 320,
  sourceHeight: 180,
  totalMillis: 7,
  revision: 2,
  backend: 'ONNX_RUNTIME',
  device: 'CPU',
  diagnosticId: 'image-test',
  observationValid: true,
  objects: [
    {
      class: 'license_plate',
      confidence: 0.95,
      bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.2 },
      attributes: { plateText: '粤BF27861' },
    },
  ],
};

describe('gateway image recognition', () => {
  let app: App;
  let root: HTMLElement;
  let revoked: ReturnType<typeof vi.spyOn>;
  const button = (label: string) =>
    [...root.querySelectorAll('button')].find(
      (item) => item.textContent === `image-recognition.${label}`,
    )!;

  beforeEach(async () => {
    state.supported = true;
    state.transport.mockReset();
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:image-test');
    revoked = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    root = document.createElement('div');
    document.body.append(root);
    app = createApp({
      render: () => h(ImageRecognition, { transport: state.transport }),
    });
    app.mount(root);
    state.open(true);
    await nextTick();
  });
  afterEach(() => {
    app.unmount();
    root.remove();
    vi.restoreAllMocks();
  });
  async function select() {
    state.select(
      new File(['sample-image-bytes'], 'sample.png', { type: 'image/png' }),
    );
    await nextTick();
  }

  it('uses the chosen task and updates both the image frame and result table', async () => {
    expect(button('start').disabled).toBe(true);
    state.transport.mockResolvedValue(response);
    await select();
    const preview = root.querySelector('[data-preview]');
    button('start').click();
    await vi.waitFor(() => expect(root.textContent).toContain('ONNX_RUNTIME'));
    expect(state.transport).toHaveBeenCalledWith('task.recognize-image', {
      taskId: 17,
      imageBase64: btoa('sample-image-bytes'),
    });
    expect(root.querySelector('[data-preview]')).not.toBe(preview);
    expect(
      root.querySelector('[data-preview]')?.getAttribute('data-frame'),
    ).toBe('image-1');
    expect(root.querySelectorAll('th')).toHaveLength(4);
    expect(root.querySelector('tbody')?.textContent).toContain('license_plate');
  });

  it('ignores a late result after closing and clears the image URL', async () => {
    let finish!: (value: typeof response) => void;
    state.transport.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    await select();
    button('start').click();
    await vi.waitFor(() => expect(state.transport).toHaveBeenCalledTimes(1));
    state.open(false);
    state.open(true);
    finish(response);
    await nextTick();
    await nextTick();
    expect(root.textContent).not.toContain('ONNX_RUNTIME');
    expect(root.querySelector('table')).toBeNull();
    expect(button('start').disabled).toBe(true);
    expect(revoked).toHaveBeenCalledWith('blob:image-test');
  });

  it('shows inference errors and permits retry without an old result', async () => {
    state.transport
      .mockRejectedValueOnce(new Error('gateway busy'))
      .mockResolvedValueOnce(response);
    await select();
    button('start').click();
    await vi.waitFor(() => expect(root.textContent).toContain('gateway busy'));
    expect(root.querySelector('table')).toBeNull();
    button('start').click();
    await vi.waitFor(() => expect(root.textContent).toContain('ONNX_RUNTIME'));
    expect(root.textContent).not.toContain('gateway busy');
  });

  it('rejects invalid uploads and blocks unsupported gateways', async () => {
    state.select(new File(['invalid'], 'test.gif', { type: 'image/gif' }));
    await nextTick();
    expect(root.textContent).toContain('image-recognition.invalidType');
    expect(button('start').disabled).toBe(true);
    state.supported = false;
    state.open(true);
    await select();
    expect(button('start').disabled).toBe(true);
    expect(state.transport).not.toHaveBeenCalled();
  });
});
