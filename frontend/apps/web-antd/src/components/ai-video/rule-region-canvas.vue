<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { Button } from 'ant-design-vue';

import { $t } from '#/locales';

import {
  regionGeometryError,
  roundCoordinate,
  translateRegion,
} from './rule-region-geometry';

type Point = AiVideoRuleApi.Point;
type DrawingMode = 'polygon' | 'quadrilateral';
const props = defineProps<{
  background: string;
  canRedo: boolean;
  canUndo: boolean;
  disabled: boolean;
  maxHeight?: string;
  region: AiVideoRuleApi.Region;
}>();
const emit = defineEmits<{
  busyChange: [busy: boolean];
  change: [points: Point[]];
  redo: [];
  undo: [];
}>();
const t = (key: string) => $t(`rule-canvas.${key}`);
const canvas = ref<SVGSVGElement>();
const drawing = ref<DrawingMode>();
const draft = ref<Point[]>([]);
const undone = ref<Point[]>([]);
const error = ref('');
const drag = ref<{
  clientX: number;
  clientY: number;
  index?: number;
  moved: boolean;
  origin: Point;
  pointerId: number;
  points: Point[];
}>();
const draggedPoints = ref<Point[]>([]);
const points = computed(() =>
  drag.value
    ? draggedPoints.value
    : drawing.value
      ? draft.value
      : props.region.points,
);
const polygon = computed(() =>
  points.value
    .map(
      (p) =>
        `${p.x * props.region.sourceWidth},${p.y * props.region.sourceHeight}`,
    )
    .join(' '),
);
const busy = computed(() => Boolean(drawing.value || drag.value));
watch(busy, (value) => emit('busyChange', value), { flush: 'sync' });
watch(
  () => [props.region, props.region.points, props.disabled, props.background],
  () => cancel(),
);
onBeforeUnmount(() => cancel());

function releasePointer() {
  const pointerId = drag.value?.pointerId;
  drag.value = undefined;
  if (pointerId !== undefined && canvas.value?.hasPointerCapture(pointerId))
    canvas.value.releasePointerCapture(pointerId);
}
function cancel() {
  releasePointer();
  drawing.value = undefined;
  draft.value = [];
  undone.value = [];
  error.value = '';
}
function startDrawing(mode: DrawingMode) {
  if (props.disabled) return;
  cancel();
  drawing.value = mode;
  canvas.value?.focus();
}
function pointAt(event: MouseEvent) {
  const bounds = canvas.value?.getBoundingClientRect();
  if (!bounds?.width || !bounds.height) return;
  return {
    x: roundCoordinate((event.clientX - bounds.left) / bounds.width),
    y: roundCoordinate((event.clientY - bounds.top) / bounds.height),
  };
}
function commit(next: Point[]) {
  const invalid = regionGeometryError(next);
  if (invalid) {
    error.value = t(invalid);
    return false;
  }
  error.value = '';
  if (JSON.stringify(next) !== JSON.stringify(props.region.points))
    emit(
      'change',
      next.map((point) => ({ ...point })),
    );
  return true;
}
function finishDrawing() {
  if (props.disabled || !drawing.value) return;
  if (drawing.value === 'quadrilateral' && draft.value.length !== 4) return;
  if (commit(draft.value)) cancel();
}
function addPoint(event: MouseEvent) {
  if (props.disabled || !drawing.value || event.button !== 0) return;
  const limit = drawing.value === 'quadrilateral' ? 4 : 20;
  if (draft.value.length >= limit) return;
  const point = pointAt(event);
  if (!point) return;
  draft.value.push(point);
  undone.value = [];
  error.value = '';
  if (drawing.value === 'quadrilateral' && draft.value.length === 4)
    finishDrawing();
}
function closePolygon(index: number) {
  if (drawing.value === 'polygon' && index === 0 && draft.value.length >= 3)
    finishDrawing();
}
function fullFrame() {
  if (props.disabled) return;
  cancel();
  commit([
    { x: 0, y: 0 },
    { x: 1, y: 0 },
    { x: 1, y: 1 },
    { x: 0, y: 1 },
  ]);
}
function undo() {
  if (props.disabled || drag.value) return;
  if (!drawing.value) {
    emit('undo');
    return;
  }
  const point = draft.value.pop();
  if (point) undone.value.push(point);
  else cancel();
  error.value = '';
}
function redo() {
  if (props.disabled || drag.value) return;
  if (!drawing.value) {
    emit('redo');
    return;
  }
  const point = undone.value.pop();
  if (point) draft.value.push(point);
  if (drawing.value === 'quadrilateral' && draft.value.length === 4)
    finishDrawing();
}
function startDrag(event: PointerEvent, index?: number) {
  if (props.disabled || drawing.value || drag.value || event.button !== 0)
    return;
  const origin = pointAt(event);
  if (!origin || !canvas.value) return;
  event.preventDefault();
  event.stopPropagation();
  canvas.value.focus();
  canvas.value.setPointerCapture(event.pointerId);
  drag.value = {
    index,
    origin,
    pointerId: event.pointerId,
    clientX: event.clientX,
    clientY: event.clientY,
    moved: false,
    points: props.region.points.map((point) => ({ ...point })),
  };
  draggedPoints.value = drag.value.points;
  error.value = '';
}
function moveDrag(event: PointerEvent) {
  const current = drag.value;
  if (!current || current.pointerId !== event.pointerId || props.disabled)
    return;
  const point = pointAt(event);
  if (!point) return;
  if (
    !current.moved &&
    Math.hypot(
      event.clientX - current.clientX,
      event.clientY - current.clientY,
    ) < 3
  )
    return;
  current.moved = true;
  draggedPoints.value =
    current.index === undefined
      ? translateRegion(current.points, {
          x: point.x - current.origin.x,
          y: point.y - current.origin.y,
        })
      : current.points.map((original, i) =>
          i === current.index ? point : { ...original },
        );
}
function endDrag(event: PointerEvent) {
  if (drag.value?.pointerId !== event.pointerId) return;
  moveDrag(event);
  const next = draggedPoints.value;
  const moved = drag.value.moved;
  releasePointer();
  if (moved && !props.disabled) commit(next);
}
function cancelPointer(event: PointerEvent) {
  if (drag.value?.pointerId === event.pointerId) releasePointer();
}
function keydown(event: KeyboardEvent) {
  if (event.key === 'Escape' && busy.value) {
    event.preventDefault();
    event.stopPropagation();
    cancel();
  } else if (event.key === 'Enter' && drawing.value) {
    event.preventDefault();
    finishDrawing();
  }
}
defineExpose({ cancel });
</script>

<template>
  <div @keydown="keydown">
    <div class="mb-3 flex flex-wrap gap-2">
      <Button
        :disabled="disabled || !!drag"
        :type="drawing === 'quadrilateral' ? 'primary' : 'default'"
        @click="startDrawing('quadrilateral')"
      >
        {{ t('quadrilateral') }}
      </Button>
      <Button
        :disabled="disabled || !!drag"
        :type="drawing === 'polygon' ? 'primary' : 'default'"
        @click="startDrawing('polygon')"
      >
        {{ t('polygon') }}
      </Button>
      <Button
        v-if="drawing === 'polygon'"
        :disabled="disabled || draft.length < 3"
        @click="finishDrawing"
        >{{ t('finish') }}</Button
      >
      <Button v-if="drawing" @click="cancel">{{ t('cancel') }}</Button>
      <Button :disabled="disabled || !!drag" @click="fullFrame">{{
        t('fullFrame')
      }}</Button>
      <Button
        :disabled="disabled || !!drag || (!drawing && !canUndo)"
        @click="undo"
        >{{ t('undo') }}</Button
      >
      <Button
        :disabled="disabled || !!drag || (drawing ? !undone.length : !canRedo)"
        @click="redo"
        >{{ t('redo') }}</Button
      >
    </div>
    <svg
      ref="canvas"
      class="mx-auto block w-full touch-none select-none rounded bg-slate-900 outline-none focus-visible:ring-2 focus-visible:ring-sky-400"
      :class="{ 'cursor-crosshair': drawing, 'cursor-grabbing': drag }"
      :style="{
        aspectRatio: `${region.sourceWidth}/${region.sourceHeight}`,
        maxWidth: maxHeight
          ? `calc(${maxHeight} * ${region.sourceWidth / region.sourceHeight})`
          : undefined,
      }"
      :viewBox="`0 0 ${region.sourceWidth} ${region.sourceHeight}`"
      :aria-label="t('canvas')"
      :aria-disabled="disabled"
      tabindex="0"
      @click="addPoint"
      @pointermove="moveDrag"
      @pointerup="endDrag"
      @pointercancel="cancelPointer"
      @lostpointercapture="cancelPointer"
    >
      <image
        v-if="background"
        :href="background"
        width="100%"
        height="100%"
        preserveAspectRatio="none"
        pointer-events="none"
      />
      <polygon
        v-if="points.length >= 3"
        :points="polygon"
        :class="{ 'cursor-grab': !disabled && !drawing && !drag }"
        fill="#38bdf833"
        stroke="#38bdf8"
        stroke-width="3"
        vector-effect="non-scaling-stroke"
        @pointerdown="startDrag($event)"
      />
      <polyline
        v-else
        :points="polygon"
        fill="none"
        stroke="#38bdf8"
        stroke-width="3"
        vector-effect="non-scaling-stroke"
      />
      <g
        v-for="(p, i) in points"
        :key="i"
        :class="{ 'cursor-move': !disabled && !drawing && !drag }"
      >
        <circle
          :cx="p.x * region.sourceWidth"
          :cy="p.y * region.sourceHeight"
          :r="region.sourceWidth / 65"
          fill="transparent"
          @pointerdown="startDrag($event, i)"
          @click.stop="closePolygon(i)"
        />
        <circle
          :cx="p.x * region.sourceWidth"
          :cy="p.y * region.sourceHeight"
          :r="region.sourceWidth / 140"
          fill="white"
          stroke="#0284c7"
          stroke-width="1.5"
          vector-effect="non-scaling-stroke"
          pointer-events="none"
        />
      </g>
    </svg>
    <p v-if="error" class="mt-2 text-sm text-destructive" role="alert">
      {{ error }}
    </p>
    <p class="mt-2 text-xs text-muted-foreground" aria-live="polite">
      {{
        disabled
          ? t('readOnly')
          : drawing === 'quadrilateral'
            ? t('drawFour')
            : drawing
              ? t('drawPolygon')
              : t('editHint')
      }}
      <span v-if="drawing"
        >{{ draft.length }} / {{ drawing === 'quadrilateral' ? 4 : 20 }}</span
      >
    </p>
    <p class="mt-1 text-xs text-muted-foreground">
      {{ background ? t('imageLoaded') : t('noImage') }} ·
      {{ region.sourceWidth }} × {{ region.sourceHeight }}
    </p>
  </div>
</template>
