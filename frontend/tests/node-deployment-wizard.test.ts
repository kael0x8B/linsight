import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest';
import { createApp, h, nextTick } from 'vue';
import type { App } from 'vue';
import { FormApi } from '../packages/@core/ui-kit/form-ui/src/form-api';

const state = vi.hoisted(() => ({
  forms: [] as any[], options: {} as any, drawer: {} as any, data: {} as any,
  locked: false, preflight: vi.fn(), create: vi.fn(), get: vi.fn(),
}));
vi.mock('#/api/ai-video/node', () => ({
  preflightNodeDeployment: state.preflight, createNodeDeployment: state.create, getNodeDeployment: state.get,
}));
vi.mock('#/adapter/form', async () => {
  const { defineComponent, h, onMounted, onBeforeUnmount } = await import('vue');
  const { FormApi } = await import('../packages/@core/ui-kit/form-ui/src/form-api');
  const chain: any = new Proxy(() => chain, { get: () => chain });
  return {
    z: chain,
    useVbenForm: (options: any) => {
      const api = new FormApi(options);
      const values: Record<string, any> = Object.fromEntries(options.schema.map((field: any) => [field.fieldName, undefined]));
      const actions = { meta: {}, values, validate: async () => ({ valid: true }),
        resetForm: () => Object.keys(values).forEach(key => values[key] = undefined),
        setValues: (input: any) => Object.assign(values, input),
        setFieldValue: (key: string, value: any) => values[key] = value };
      state.forms.push(api);
      const component = defineComponent({ setup() {
        onMounted(() => api.mount(actions as any));
        onBeforeUnmount(() => api.unmount());
        return () => h('div', { 'data-form': options.schema[0].fieldName });
      } });
      return [component, api];
    },
  };
});
vi.mock('@vben/common-ui', async () => {
  const { defineComponent, h } = await import('vue');
  return { useVbenDrawer: (options: any) => {
    state.options = options;
    state.drawer = { lock: () => state.locked = true, unlock: () => state.locked = false,
      close: () => options.onOpenChange(false), getData: () => state.data };
    return [defineComponent({ setup(_props, { slots }) { return () => h('div', [slots.default?.(), slots['prepend-footer']?.()]); } }), state.drawer];
  } };
});
vi.mock('@vben/icons', () => ({ IconifyIcon: { render: () => null } }));
vi.mock('ant-design-vue', async () => {
  const { defineComponent, h } = await import('vue');
  const content = defineComponent({ props: ['message', 'title'], setup(props, { slots }) { return () => h('div', [props.message, props.title, slots.default?.()]); } });
  const checkbox = defineComponent({ props: ['checked'], emits: ['update:checked'], setup(props, { emit }) { return () => h('input', { type: 'checkbox', checked: props.checked, onChange: () => emit('update:checked', true) }); } });
  return { Alert: content, Button: content, Checkbox: checkbox, Descriptions: content, DescriptionsItem: content, Progress: content, Result: content, Steps: content, Tag: content };
});
vi.mock('#/views/ai-video/node/modules/deployment-terminal.vue', () => ({ default: { render: () => null } }));
import Wizard from '../apps/web-antd/src/views/ai-video/node/modules/deployment-drawer.vue';

describe('deployment wizard with real FormApi mount waits', () => {
  let app: App; let host: HTMLDivElement;
  beforeEach(async () => {
    state.forms = []; state.data = {}; state.locked = false;
    state.preflight.mockReset(); state.create.mockReset(); state.get.mockReset();
    host = document.createElement('div'); document.body.append(host);
    app = createApp({ render: () => h(Wizard) }); app.mount(host);
    await nextTick(); await state.options.onOpenChange(true);
    await state.forms[0].setValues({ host: 'edge.example', port: 22, username: 'linaro', password: 'test-only' });
  });
  afterEach(() => { app.unmount(); host.remove(); vi.useRealTimers(); });
  async function inspect(existing = true) {
    state.preflight.mockResolvedValue({ supported: true, warnings: [], hostKey: 'key', hostKeyType: 'ssh-ed25519', hostKeyFingerprint: 'SHA256:test',
      ...(existing ? { existingNodeId: 8, existingNodeCode: 'edge-1', existingNodeName: 'Edge', controlPlaneUrl: 'http://control.example' } : {}) });
    await state.options.onConfirm(); await nextTick();
  }
  it('keeps both forms mounted and unlocks after an existing-node response', async () => {
    expect(state.forms.every((api: FormApi) => api.isMounted)).toBe(true);
    await inspect();
    expect(state.locked).toBe(false);
    expect((await state.forms[1].getValues()).nodeCode).toBe('edge-1');
    expect((host.querySelector('[data-form="host"]')!.parentElement!.parentElement as HTMLElement).style.display).toBe('none');
  });
  it('new-host preflight also completes, and errors unlock for retry', async () => {
    state.preflight.mockRejectedValueOnce(new Error('denied'));
    await state.options.onConfirm();
    expect(state.locked).toBe(false);
    expect(host.textContent).toContain('denied');
    await inspect(false);
    expect(state.locked).toBe(false);
  });
  it('starts polling after create, clears credentials, and stops at terminal state', async () => {
    await inspect();
    host.querySelector('input')!.dispatchEvent(new Event('change'));
    await nextTick();
    state.create.mockResolvedValue(99);
    state.get.mockResolvedValue({ id: 99, status: 'SUCCEEDED', outputLog: 'persisted output' });
    vi.useFakeTimers();
    await state.options.onConfirm();
    expect(state.locked).toBe(false);
    expect((await state.forms[0].getValues()).password).toBe('');
    expect(state.create.mock.calls[0][0].nodeId).toBe(8);
    await vi.advanceTimersByTimeAsync(1500);
    expect(state.get).toHaveBeenCalledWith(99);
    await vi.advanceTimersByTimeAsync(6000);
    expect(state.get).toHaveBeenCalledTimes(1);
  });
  it('a failed create keeps the wizard usable; closing and reopening resets it', async () => {
    await inspect();
    host.querySelector('input')!.dispatchEvent(new Event('change'));
    await nextTick();
    state.create.mockRejectedValueOnce(new Error('busy'));
    await state.options.onConfirm();
    expect(state.locked).toBe(false);
    expect(state.get).not.toHaveBeenCalled();
    await state.options.onOpenChange(false);
    await state.options.onOpenChange(true);
    expect(state.forms.every((api: FormApi) => api.isMounted)).toBe(true);
    expect((await state.forms[0].getValues()).password).toBeUndefined();
  });
});
