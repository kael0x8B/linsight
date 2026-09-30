import type { App, Slot } from 'vue';

import type { AiVideoRuleApi } from '../apps/web-antd/src/api/ai-video/rule';

import { createApp, h, nextTick, ref } from 'vue';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import translations from '../apps/web-antd/src/locales/langs/zh-CN/rule-canvas.json';
import GatewayRuleEditor from '../apps/web-antd/src/views/ai-video/node/modules/gateway-rule-editor.vue';
import { createRuleAst } from '../apps/web-antd/src/views/ai-video/rule/modules/rule-state';

const api = vi.hoisted(() => ({
  rules: vi.fn(),
  versions: vi.fn(),
  warning: vi.fn(),
  setRegionVisible: vi.fn(),
}));
const hiddenLayers = ref<string[]>([]);
vi.mock(
  '../apps/web-antd/src/components/ai-video/use-display-preferences.ts',
  () => ({
    recognitionRegionKey: (key: string) => `roi-${key}`,
    useDisplayPreferences: () => ({
      hidden: hiddenLayers,
      ready: { value: true },
      saving: { value: false },
      error: { value: '' },
      setVisible: api.setRegionVisible,
      reload: vi.fn(),
    }),
  }),
);
vi.mock('../apps/web-antd/src/api/ai-video/rule/index.ts', () => ({
  getPublishedRules: api.rules,
  getRuleVersions: api.versions,
}));
vi.mock('../apps/web-antd/src/locales/index.ts', () => ({
  $t: (key: string) =>
    translations[
      key.replace('rule-canvas.', '') as keyof typeof translations
    ] ?? key,
}));
vi.mock('../apps/web-antd/src/adapter/form.ts', () => ({
  useVbenForm: () => [
    { render: () => h('div') },
    { updateSchema: vi.fn(), setValues: vi.fn() },
  ],
}));
vi.mock(
  '../apps/web-antd/src/components/ai-video/camera-preview-player.vue',
  () => ({
    default: { render: () => h('div') },
  }),
);
vi.mock('ant-design-vue', () => ({
  Button: {
    inheritAttrs: false,
    setup:
      (
        _: unknown,
        { attrs, slots }: { attrs: object; slots: { default?: Slot } },
      ) =>
      () =>
        h('button', attrs, slots.default?.()),
  },
  Select: {
    props: ['value', 'options'],
    emits: ['update:value', 'change'],
    setup:
      (
        props: {
          options: { label: string; value: number | string }[];
          value?: number | string;
        },
        { emit }: { emit: (event: string, value: unknown) => void },
      ) =>
      () =>
        h(
          'select',
          {
            value: props.value,
            onChange: (event: Event) => {
              const raw = (event.target as HTMLSelectElement).value;
              const value = props.options.find(
                (option) => String(option.value) === raw,
              )?.value;
              emit('update:value', value);
              emit('change', value);
            },
          },
          [
            h('option', { value: '' }, ''),
            ...props.options.map((option) =>
              h('option', { value: option.value }, option.label),
            ),
          ],
        ),
  },
  Switch: {
    props: ['checked'],
    emits: ['change'],
    setup:
      (
        props: { checked: boolean },
        { emit }: { emit: (name: string, value: boolean) => void },
      ) =>
      () =>
        h('input', {
          type: 'checkbox',
          checked: props.checked,
          onChange: (event: Event) =>
            emit('change', (event.target as HTMLInputElement).checked),
        }),
  },
  Alert: {
    props: ['message'],
    setup: (props: { message: string }) => () =>
      h('p', { role: 'alert' }, props.message),
  },
  message: { warning: api.warning },
}));

const roi = [
  { x: 0.3114, y: 0.641 },
  { x: 0.6269, y: 0.6363 },
  { x: 0.642, y: 0.8702 },
  { x: 0.3149, y: 0.8821 },
];
const templateAst = createRuleAst('LICENSE_PLATE');
templateAst.regions = [
  {
    ...(templateAst.regions[0] as AiVideoRuleApi.Region),
    id: 'plate-area',
    name: '车牌识别区域',
    sourceWidth: 640,
    sourceHeight: 480,
    pointMode: 'CENTROID',
    points: roi,
  },
];
const template: AiVideoRuleApi.Rule = {
  id: 73018,
  code: 'plate',
  name: '车牌号码确认',
  eventType: 'LICENSE_PLATE',
  currentVersionId: 73123,
  status: 0,
};
const version: AiVideoRuleApi.RuleVersion = {
  id: 73123,
  ruleId: 73018,
  version: 2,
  validationStatus: 'PUBLISHED',
  ast: templateAst,
  createTime: '',
};
let app: App | undefined;
let root: HTMLElement;
beforeEach(() => {
  vi.clearAllMocks();
  hiddenLayers.value = [];
  api.setRegionVisible.mockImplementation((key: string, visible: boolean) => {
    hiddenLayers.value = visible
      ? hiddenLayers.value.filter((value) => value !== key)
      : [...new Set([...hiddenLayers.value, key])];
  });
  api.rules.mockResolvedValue([template]);
  api.versions.mockResolvedValue([
    version,
    { ...version, id: 73124, version: 3, validationStatus: 'VALID' },
  ]);
});
afterEach(() => {
  app?.unmount();
  app = undefined;
  root?.remove();
});
async function settle() {
  await new Promise((resolve) => setTimeout(resolve, 0));
  await nextTick();
}
async function mount(
  options: {
    allowTemplateImport?: boolean;
    camera?: boolean;
    imageSize?: { height: number; width: number };
    taskId?: number;
  } = {},
) {
  const initial = createRuleAst('VEHICLE_PLATE_RECOGNIZED');
  const text = ref(JSON.stringify(initial, null, 2));
  const editor = ref<InstanceType<typeof GatewayRuleEditor>>();
  root = document.createElement('div');
  document.body.append(root);
  app = createApp({
    render: () =>
      h(GatewayRuleEditor, {
        ref: editor,
        modelValue: text.value,
        allowTemplateImport: options.allowTemplateImport ?? true,
        camera: options.camera
          ? { id: 2, name: 'Camera', code: 'camera-2', status: 0 }
          : undefined,
        imageSize: options.imageSize,
        taskId: options.taskId,
        'onUpdate:modelValue': (value: string) => {
          text.value = value;
        },
      }),
  });
  app.mount(root);
  await settle();
  async function button(label: string) {
    const el = [...root.querySelectorAll('button')].find(
      (item) => item.textContent?.trim() === label,
    );
    if (!el) throw new Error(`Missing button: ${label}`);
    el.click();
    await settle();
  }
  async function select(label: string, value: number) {
    const el = root.querySelector<HTMLSelectElement>(
      `select[aria-label="${label}"]`,
    );
    if (!el) throw new Error(`Missing selector: ${label}`);
    el.value = String(value);
    el.dispatchEvent(new Event('change', { bubbles: true }));
    await settle();
  }
  return {
    initial,
    text,
    editor,
    button,
    select,
    ast: () => JSON.parse(text.value) as AiVideoRuleApi.RuleAst,
  };
}

describe('gateway ROI editing and template reuse', () => {
  it('changes only the live display preference and keeps the editing polygon visible and unchanged', async () => {
    hiddenLayers.value = ['roi-task-34'];
    const ui = await mount({ camera: true, taskId: 33 });
    const before = ui.text.value;
    const checkbox = root.querySelector<HTMLInputElement>(
      'input[aria-label="显示识别区域"]',
    );
    expect(checkbox?.checked).toBe(true);
    checkbox?.click();
    await settle();
    expect(api.setRegionVisible).toHaveBeenCalledWith('roi-task-33', false);
    expect(checkbox?.checked).toBe(false);
    expect(hiddenLayers.value).toEqual(['roi-task-34', 'roi-task-33']);
    checkbox?.click();
    await settle();
    expect(hiddenLayers.value).toEqual(['roi-task-34']);
    expect(ui.text.value).toBe(before);
    expect(root.querySelector('svg polygon')).not.toBeNull();
    expect(
      root.querySelectorAll('svg circle[fill="transparent"]'),
    ).toHaveLength(4);
    expect(root.querySelector('svg polygon')?.getAttribute('stroke')).toBe(
      '#38bdf8',
    );
  });

  it('copies the published ROI without changing task conditions, IDs or event type and supports undo/redo', async () => {
    const ui = await mount();
    await ui.button('从规则模板复制区域');
    await ui.select('规则模板', 73018);
    const versions = root.querySelector('select[aria-label="模板版本"]');
    expect(versions?.textContent).toContain('v2');
    expect(versions?.textContent).not.toContain('v3');
    await ui.button('复制到当前区域');
    expect(ui.ast().regions[0]?.points).toEqual(roi);
    expect(ui.ast().regions[0]?.id).toBe('main');
    expect(ui.ast().regions[0]?.sourceWidth).toBe(640);
    expect(ui.ast().regions[0]?.pointMode).toBe('FOOT');
    expect(ui.ast().eventType).toBe('VEHICLE_PLATE_RECOGNIZED');
    expect(ui.ast().condition).toEqual(ui.initial.condition);
    expect(ui.ast().schedule).toEqual(ui.initial.schedule);
    expect(root.querySelector('[role="status"]')?.textContent).toContain(
      '保存当前识别配置后生效',
    );
    await ui.button('撤销');
    expect(ui.ast()).toEqual(ui.initial);
    await ui.button('重做');
    expect(ui.ast().regions[0]?.points).toEqual(roi);
    expect(templateAst.regions[0]?.points).toEqual(roi);
  });

  it('uses actual snapshot dimensions while retaining normalized template coordinates', async () => {
    const ui = await mount({ imageSize: { width: 1280, height: 720 } });
    await ui.button('从规则模板复制区域');
    await ui.select('规则模板', 73018);
    await ui.button('复制到当前区域');
    expect(ui.ast().regions[0]).toMatchObject({
      sourceWidth: 1280,
      sourceHeight: 720,
      points: roi,
    });
    expect(root.querySelector('svg')?.getAttribute('viewBox')).toBe(
      '0 0 1280 720',
    );
  });

  it('exposes the shared draggable canvas without a snapshot and rejects saving an unfinished drawing', async () => {
    const ui = await mount();
    expect(root.querySelectorAll('circle[fill="transparent"]')).toHaveLength(4);
    await ui.button('绘制四边形');
    expect(ui.editor.value?.validate()).toBe(false);
    expect(api.warning).toHaveBeenCalledWith('请先完成或取消正在绘制的区域。');
    await ui.button('取消绘制');
    expect(ui.editor.value?.validate()).toBe(true);
    expect(ui.ast()).toEqual(ui.initial);
  });

  it('validates geometry entered through the advanced rule field', async () => {
    const ui = await mount();
    const rule = ui.ast();
    const region = rule.regions[0];
    if (!region) throw new Error('Missing fixture region');
    region.points = [
      { x: 0, y: 0 },
      { x: 1, y: 1 },
      { x: 1, y: 0 },
      { x: 0, y: 1 },
    ];
    ui.text.value = JSON.stringify(rule);
    await settle();
    expect(ui.editor.value?.validate()).toBe(false);
    expect(api.warning).toHaveBeenCalledWith(
      expect.stringContaining('边线不能交叉'),
    );
  });

  it('keeps the local/offline editor independent of platform template queries', async () => {
    await mount({ allowTemplateImport: false });
    expect(root.textContent).not.toContain('从规则模板复制区域');
    expect(root.textContent).toContain('绘制四边形');
    expect(api.rules).not.toHaveBeenCalled();
    expect(api.versions).not.toHaveBeenCalled();
  });

  it('shows template load failures without replacing the current region', async () => {
    api.rules.mockRejectedValueOnce(new Error('offline'));
    const ui = await mount();
    await ui.button('从规则模板复制区域');
    expect(root.querySelector('[role="alert"]')?.textContent).toContain(
      '模板读取失败',
    );
    expect(ui.ast()).toEqual(ui.initial);
  });

  it('ignores an older template response after the selection changes', async () => {
    let resolveOlder: (value: AiVideoRuleApi.RuleVersion[]) => void = () => {};
    api.rules.mockResolvedValue([
      template,
      { ...template, id: 73019, name: '其他模板', currentVersionId: 73125 },
    ]);
    api.versions.mockImplementation((id: number) =>
      id === 73018
        ? new Promise<AiVideoRuleApi.RuleVersion[]>((resolve) => {
            resolveOlder = resolve;
          })
        : Promise.resolve([
            { ...version, ruleId: 73019, id: 73125, version: 4 },
          ]),
    );
    const ui = await mount();
    await ui.button('从规则模板复制区域');
    await ui.select('规则模板', 73018);
    await ui.select('规则模板', 73019);
    resolveOlder([version]);
    await settle();
    expect(
      root.querySelector('select[aria-label="模板版本"]')?.textContent,
    ).toContain('v4');
    expect(
      root.querySelector('select[aria-label="模板版本"]')?.textContent,
    ).not.toContain('v2');
  });

  it('clears a previously selected template when reopening the picker fails', async () => {
    const ui = await mount();
    await ui.button('从规则模板复制区域');
    await ui.select('规则模板', 73018);
    await ui.button('收起');
    api.rules.mockRejectedValueOnce(new Error('offline'));
    await ui.button('从规则模板复制区域');
    const apply = [...root.querySelectorAll('button')].find(
      (item) => item.textContent?.trim() === '复制到当前区域',
    );
    expect(apply?.disabled).toBe(true);
    expect(ui.ast()).toEqual(ui.initial);
  });
});
