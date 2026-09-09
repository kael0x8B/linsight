<script lang="ts" setup>
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { $t } from '#/locales';

import { mapNormalizedBox } from './overlay-coordinate';
import { describeObject, isFreshFrame } from './overlay-presentation';

const props = withDefaults(
  defineProps<{
    frame?: AiVideoCameraApi.OverlayFrame;
    historical?: boolean;
    maxAgeMs?: number;
    regions?: {bbox:AiVideoCameraApi.OverlayBoundingBox;color:string;title:string;}[];
    showAllObjects?: boolean;
    videoHeight?:number;
    videoWidth?:number;
    visible?: boolean;
  }>(),
  { regions:()=>[],videoWidth:0,videoHeight:0,frame: undefined, historical: false, visible: true, showAllObjects: true, maxAgeMs: 750 },
);

const canvasRef = ref<HTMLCanvasElement>();
let resizeObserver: ResizeObserver | undefined;
let ageTimer: ReturnType<typeof setInterval> | undefined;

function classColor(className: string) {
  if (className.endsWith('_absent')) return '#fb7185';
  if (className.endsWith('_present')) return '#34d399';
  if (className.endsWith('_unknown')) return '#fbbf24';
  let hash = 0;
  for (const character of className) {
    hash = Math.trunc(
      (hash * 31 + (character.codePointAt(0) ?? 0)) % 2_147_483_647,
    );
  }
  const fallback = '#22d3ee';
  const palette = [
    fallback,
    '#a78bfa',
    '#f59e0b',
    '#34d399',
    '#fb7185',
    '#60a5fa',
  ];
  return palette[hash % palette.length] ?? fallback;
}

function drawOverlay() {
  const canvas = canvasRef.value;
  const frame = props.frame;
  if (!canvas) return;

  const rect = canvas.getBoundingClientRect();
  const devicePixelRatio = window.devicePixelRatio || 1;
  const width = Math.max(1, Math.round(rect.width * devicePixelRatio));
  const height = Math.max(1, Math.round(rect.height * devicePixelRatio));
  if (canvas.width !== width || canvas.height !== height) {
    canvas.width = width;
    canvas.height = height;
  }

  const context = canvas.getContext('2d');
  if (!context) return;
  context.setTransform(devicePixelRatio, 0, 0, devicePixelRatio, 0, 0);
  context.clearRect(0, 0, rect.width, rect.height);
  if (props.visible && props.videoWidth && props.videoHeight) {
    for (const region of props.regions) {
      const box=mapNormalizedBox(region.bbox,props.videoWidth,props.videoHeight,rect.width,rect.height);
      context.strokeStyle=region.color;context.lineWidth=2;context.setLineDash([8,5]);context.strokeRect(box.x,box.y,box.width,box.height);context.setLineDash([]);
    }
  }
  if (
    !props.visible ||
    !frame ||
    (!props.historical && !isFreshFrame(frame, Date.now(), props.maxAgeMs)) ||
    frame.sourceWidth <= 0 ||
    frame.sourceHeight <= 0
  )
    return;

  const labels: {height:number;width:number;x:number;y:number;}[]=[];
  for (const object of frame.objects) {
    const presentation = describeObject(object);
    if (!props.showAllObjects && !presentation.visibleByDefault) continue;
    const color = typeof object.attributes.overlayColor === 'string' ? object.attributes.overlayColor : classColor(presentation.classKey);
    const {
      height: boxHeight,
      width: boxWidth,
      x,
      y,
    } = mapNormalizedBox(
      presentation.bbox,
      frame.sourceWidth,
      frame.sourceHeight,
      rect.width,
      rect.height,
    );
    const name = presentation.labelKey ? $t(`page.aiVideo.recognition.${presentation.labelKey}`) : object.class;
    const score = presentation.confidence === undefined ? '' : ` ${(presentation.confidence * 100).toFixed(0)}%`;
    const prefix = object.attributes.overlayLayer ? `${object.attributes.overlayLayer} · ` : '';
    let label = `${prefix}${name}${score}`;

    context.strokeStyle = color;
    context.lineWidth = 2;
    context.strokeRect(x, y, boxWidth, boxHeight);
    context.font = '12px ui-monospace, SFMono-Regular, Menlo, monospace';
    const maxLabelWidth=Math.max(40,Math.min(rect.width-8,320));
    if(context.measureText(label).width+12>maxLabelWidth){while(label.length>1 && context.measureText(`${label}…`).width+12>maxLabelWidth)label=label.slice(0,-1);label+='…';}
    const labelWidth = context.measureText(label).width + 12;
    const labelHeight = 22;
    const labelX = Math.max(0, Math.min(x, rect.width - labelWidth));
    let labelY =
      y >= labelHeight
        ? y - labelHeight
        : Math.min(y + boxHeight, rect.height - labelHeight);
    for(let attempt=0;attempt<6;attempt++) {
      if(!labels.some(box=>labelX<box.x+box.width && labelX+labelWidth>box.x && labelY<box.y+box.height && labelY+labelHeight>box.y))break;
      labelY=labelY>=labelHeight+2 ? labelY-labelHeight-2 : Math.min(rect.height-labelHeight,labelY+boxHeight+labelHeight+2);
    }
    labels.push({x:labelX,y:labelY,width:labelWidth,height:labelHeight});
    context.fillStyle = color;
    context.fillRect(
      labelX,
      labelY,
      Math.min(labelWidth, rect.width),
      labelHeight,
    );
    context.fillStyle = '#08111f';
    context.fillText(label, labelX + 6, labelY + 15);
  }
}

watch(
  () => [props.frame, props.regions, props.videoWidth, props.videoHeight, props.visible, props.showAllObjects, props.maxAgeMs, props.historical],
  () => void nextTick(drawOverlay),
  { deep: true },
);

onMounted(() => {
  const canvas = canvasRef.value;
  if (!canvas) return;
  resizeObserver = new ResizeObserver(drawOverlay);
  if (canvas.parentElement) resizeObserver.observe(canvas.parentElement);
  drawOverlay();
  ageTimer = setInterval(drawOverlay, 250);
});

onBeforeUnmount(() => {
  resizeObserver?.disconnect();
  if (ageTimer) clearInterval(ageTimer);
});
</script>

<template>
  <canvas ref="canvasRef" aria-hidden="true" class="preview-overlay"></canvas>
</template>

<style scoped>
.preview-overlay {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}
</style>
