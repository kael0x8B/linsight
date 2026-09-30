import type { App, Slot } from 'vue';

import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { createApp, h, nextTick, ref } from 'vue';

import { afterEach, describe, expect, it, vi } from 'vitest';

import translations from '#/locales/langs/zh-CN/rule-canvas.json';

import RuleRegionCanvas from './rule-region-canvas.vue';
import { regionGeometryError, translateRegion } from './rule-region-geometry';

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
}));
vi.mock('#/locales', () => ({
  $t: (key: string) =>
    translations[key.replace('rule-canvas.', '') as keyof typeof translations],
}));

type Point = AiVideoRuleApi.Point;
const fullFrame = [
  { x: 0, y: 0 },
  { x: 1, y: 0 },
  { x: 1, y: 1 },
  { x: 0, y: 1 },
];
const square = [
  { x: 0.2, y: 0.2 },
  { x: 0.8, y: 0.2 },
  { x: 0.8, y: 0.8 },
  { x: 0.2, y: 0.8 },
];
let app: App | undefined;
let host: HTMLDivElement;
afterEach(() => {
  app?.unmount();
  app = undefined;
  host?.remove();
  vi.restoreAllMocks();
});

async function mount(points = fullFrame, readOnly = false) {
  const region = ref<AiVideoRuleApi.Region>({
    id: 'main',
    name: '主区域',
    type: 'POLYGON',
    pointMode: 'FOOT',
    overlapThreshold: 0.2,
    sourceWidth: 1920,
    sourceHeight: 1080,
    points: points.map((p) => ({ ...p })),
  });
  const disabled = ref(readOnly);
  const undoStack = ref<Point[][]>([]);
  const redoStack = ref<Point[][]>([]);
  const busy = ref(false);
  const changed = vi.fn((next: Point[]) => {
    undoStack.value.push(region.value.points);
    redoStack.value = [];
    region.value.points = next;
  });
  host = document.createElement('div');
  document.body.append(host);
  app = createApp({
    render: () =>
      h(RuleRegionCanvas, {
        region: region.value,
        disabled: disabled.value,
        background: '',
        canUndo: undoStack.value.length > 0,
        canRedo: redoStack.value.length > 0,
        onChange: changed,
        onBusyChange: (value: boolean) => {
          busy.value = value;
        },
        onUndo: () => {
          const previous = undoStack.value.pop();
          if (previous) {
            redoStack.value.push(region.value.points);
            region.value.points = previous;
          }
        },
        onRedo: () => {
          const next = redoStack.value.pop();
          if (next) {
            undoStack.value.push(region.value.points);
            region.value.points = next;
          }
        },
      }),
  });
  app.mount(host);
  await nextTick();
  const element = host.querySelector('svg');
  if (!element) throw new Error('Canvas not mounted');
  const svg = element;
  vi.spyOn(svg, 'getBoundingClientRect').mockReturnValue(
    new DOMRect(100, 50, 800, 450),
  );
  const captured = new Set<number>();
  Object.assign(svg, {
    setPointerCapture: (id: number) => captured.add(id),
    hasPointerCapture: (id: number) => captured.has(id),
    releasePointerCapture: (id: number) => captured.delete(id),
  });
  async function button(text: string) {
    const target = [...host.querySelectorAll('button')].find(
      (b) => b.textContent?.trim() === text,
    );
    if (!target) throw new Error(`Button not found: ${text}`);
    target.click();
    await nextTick();
  }
  async function click(x: number, y: number, target: Element = svg) {
    target.dispatchEvent(
      new MouseEvent('click', {
        clientX: 100 + x * 800,
        clientY: 50 + y * 450,
        bubbles: true,
        button: 0,
      }),
    );
    await nextTick();
  }
  async function pointer(
    type: string,
    x: number,
    y: number,
    target: Element = svg,
    pointerId = 1,
  ) {
    target.dispatchEvent(
      new PointerEvent(type, {
        clientX: 100 + x * 800,
        clientY: 50 + y * 450,
        pointerId,
        button: 0,
        bubbles: true,
      }),
    );
    await nextTick();
  }
  function vertex(index: number) {
    const target = svg.querySelectorAll('circle[fill="transparent"]')[index];
    if (!target) throw new Error(`Vertex not found: ${index}`);
    return target;
  }
  function polygon() {
    const target = svg.querySelector('polygon');
    if (!target) throw new Error('Polygon not found');
    return target;
  }
  return {
    region,
    disabled,
    busy,
    changed,
    svg,
    captured,
    button,
    click,
    pointer,
    vertex,
    polygon,
  };
}

describe('rule region canvas interactions', () => {
  it('replaces the default full frame with exactly four drawn corners and supports undo/redo', async () => {
    const ui = await mount();
    await ui.button('绘制四边形');
    expect(ui.busy.value).toBe(true);
    for (const point of square) await ui.click(point.x, point.y);
    expect(ui.region.value.points).toEqual(square);
    expect(ui.changed).toHaveBeenCalledTimes(1);
    expect(ui.busy.value).toBe(false);
    await ui.click(0.5, 0.5);
    expect(ui.region.value.points).toHaveLength(4);
    await ui.button('撤销');
    expect(ui.region.value.points).toEqual(fullFrame);
    await ui.button('重做');
    expect(ui.region.value.points).toEqual(square);
  });

  it('drags a vertex without appending a point and commits once per gesture', async () => {
    const ui = await mount(square);
    await ui.pointer('pointerdown', 0.2, 0.2, ui.vertex(0));
    await ui.pointer('pointermove', 0.25, 0.3);
    await ui.pointer('pointermove', 0.3, 0.35);
    expect(ui.changed).not.toHaveBeenCalled();
    await ui.pointer('pointerup', 0.3, 0.35);
    await ui.click(0.3, 0.35);
    expect(ui.region.value.points).toEqual([
      { x: 0.3, y: 0.35 },
      ...square.slice(1),
    ]);
    expect(ui.changed).toHaveBeenCalledTimes(1);
    expect(ui.captured.size).toBe(0);
    await ui.button('撤销');
    expect(ui.region.value.points).toEqual(square);
  });

  it('moves the whole region without distorting it or leaving the image', async () => {
    const ui = await mount(square);
    await ui.pointer('pointerdown', 0.5, 0.5, ui.polygon());
    await ui.pointer('pointermove', 1.5, -0.5);
    await ui.pointer('pointerup', 1.5, -0.5);
    expect(ui.region.value.points).toEqual([
      { x: 0.4, y: 0 },
      { x: 1, y: 0 },
      { x: 1, y: 0.6 },
      { x: 0.4, y: 0.6 },
    ]);
  });

  it('keeps clicks and tiny movements out of history and ignores another pointer', async () => {
    const ui = await mount(square);
    await ui.pointer('pointerdown', 0.2, 0.2, ui.vertex(0));
    await ui.pointer('pointermove', 0.5, 0.5, ui.svg, 2);
    await ui.pointer('pointerup', 0.201, 0.201);
    await ui.click(0.201, 0.201);
    expect(ui.changed).not.toHaveBeenCalled();
    expect(ui.region.value.points).toEqual(square);
  });

  it('cancels drawing and interrupted drags without modifying the saved region', async () => {
    const ui = await mount(square);
    await ui.button('绘制四边形');
    await ui.click(0.1, 0.1);
    await ui.click(0.9, 0.1);
    ui.svg.dispatchEvent(
      new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }),
    );
    await nextTick();
    expect(ui.busy.value).toBe(false);
    await ui.pointer('pointerdown', 0.2, 0.2, ui.vertex(0));
    await ui.pointer('pointermove', 0.3, 0.3);
    await ui.pointer('pointercancel', 0.3, 0.3);
    await ui.pointer('pointerup', 0.3, 0.3);
    expect(ui.region.value.points).toEqual(square);
    expect(ui.changed).not.toHaveBeenCalled();
    expect(ui.captured.size).toBe(0);
  });

  it('closes a polygon by clicking its first vertex and can undo draft points', async () => {
    const ui = await mount();
    await ui.button('绘制多边形');
    await ui.click(0.1, 0.1);
    await ui.click(0.9, 0.1);
    await ui.click(0.5, 0.9);
    await ui.button('撤销');
    expect(ui.svg.querySelectorAll('circle[fill="transparent"]')).toHaveLength(
      2,
    );
    await ui.button('重做');
    await ui.click(0.1, 0.1, ui.vertex(0));
    expect(ui.region.value.points).toEqual([
      { x: 0.1, y: 0.1 },
      { x: 0.9, y: 0.1 },
      { x: 0.5, y: 0.9 },
    ]);
    expect(ui.busy.value).toBe(false);
  });

  it('rejects crossed quadrilaterals without replacing the old region', async () => {
    const ui = await mount();
    await ui.button('绘制四边形');
    for (const [x, y] of [
      [0.1, 0.1],
      [0.9, 0.9],
      [0.9, 0.1],
      [0.1, 0.9],
    ] as [number, number][])
      await ui.click(x, y);
    expect(host.querySelector('[role="alert"]')?.textContent).toContain(
      '边线不能交叉',
    );
    expect(ui.region.value.points).toEqual(fullFrame);
    expect(ui.busy.value).toBe(true);
    await ui.button('取消绘制');
    expect(ui.busy.value).toBe(false);
  });

  it('rejects invalid vertex drags and resets a draft when its region changes', async () => {
    const ui = await mount(square);
    await ui.pointer('pointerdown', 0.2, 0.2, ui.vertex(0));
    await ui.pointer('pointerup', 0.9, 0.5);
    expect(ui.region.value.points).toEqual(square);
    expect(host.querySelector('[role="alert"]')).not.toBeNull();
    await ui.button('绘制四边形');
    await ui.click(0.1, 0.1);
    ui.region.value.points = fullFrame;
    await nextTick();
    expect(ui.busy.value).toBe(false);
    expect(ui.svg.querySelectorAll('circle[fill="transparent"]')).toHaveLength(
      4,
    );
  });

  it('prevents drawing, dragging and history changes without update permission', async () => {
    const ui = await mount(square, true);
    for (const button of host.querySelectorAll('button'))
      expect(button.disabled).toBe(true);
    await ui.pointer('pointerdown', 0.2, 0.2, ui.vertex(0));
    await ui.pointer('pointerup', 0.4, 0.4);
    await ui.click(0.5, 0.5);
    expect(ui.changed).not.toHaveBeenCalled();
    expect(ui.region.value.points).toEqual(square);
  });
});

describe('normalized region geometry', () => {
  it('accepts concave polygons and both vertex orientations', () => {
    expect(regionGeometryError(square)).toBeUndefined();
    expect(regionGeometryError([...square].reverse())).toBeUndefined();
    expect(
      regionGeometryError([
        { x: 0.1, y: 0.1 },
        { x: 0.9, y: 0.1 },
        { x: 0.5, y: 0.4 },
        { x: 0.1, y: 0.9 },
      ]),
    ).toBeUndefined();
  });
  it('rejects degenerate polygons, overlapping edges and invalid coordinates', () => {
    expect(
      regionGeometryError([
        { x: 0, y: 0 },
        { x: 0.001, y: 0 },
        { x: 0, y: 0.001 },
      ]),
    ).toBe('tooSmall');
    expect(regionGeometryError([...square, square[0] as Point])).toBe(
      'duplicatePoints',
    );
    expect(
      regionGeometryError([
        { x: 0, y: 0 },
        { x: 1, y: 0 },
        { x: 0.5, y: 0 },
        { x: 0.5, y: 1 },
      ]),
    ).toBe('selfIntersection');
    expect(regionGeometryError([{ x: Number.NaN, y: 0 }, ...square])).toBe(
      'outOfBounds',
    );
    expect(regionGeometryError([{ x: 1.1, y: 0 }, ...square])).toBe(
      'outOfBounds',
    );
  });
  it('keeps a full-frame polygon unchanged when dragged', () => {
    expect(translateRegion(fullFrame, { x: 0.2, y: -0.2 })).toEqual(fullFrame);
  });
});
