<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { message } from 'ant-design-vue';

import { describeObject, frameTimestampMillis, isFreshFrame } from '#/views/ai-video/live/modules/overlay-presentation';
import PreviewOverlay from '#/views/ai-video/live/modules/preview-overlay.vue';

const props = withDefaults(defineProps<{
  contextLabel?: string;
  emptyResultText?: string;
  emptyText?: string;
  frame?: AiVideoCameraApi.OverlayFrame;
  historical?: boolean;
  maxAgeMs?: number;
  showAllObjects?: boolean;
  showBoxes?: boolean;
  source?: string;
  title?: string;
}>(), {
  frame: undefined, source: undefined, historical: false, maxAgeMs: 15_000,
  showAllObjects: false, showBoxes: true, title: 'AI 识别画面',
  emptyText: '正在等待识别结果，请稍候。', emptyResultText: '本帧暂无已确认的告警目标', contextLabel: undefined,
});

const root = ref<HTMLElement>();
const image = ref<HTMLImageElement>();
const loadedKey = ref('');
const failed = ref(false);
const now = ref(Date.now());
const dimensions = ref({ width: 0, height: 0 });
let timer: ReturnType<typeof setInterval> | undefined;
const imageSource = computed(() => props.source || (props.frame?.imageBase64
  ? `data:image/jpeg;base64,${props.frame.imageBase64}` : ''));
const imageKey = computed(() => `${props.frame?.frameId ?? ''}:${imageSource.value}`);
const fresh = computed(() => props.historical || isFreshFrame(props.frame, now.value, props.maxAgeMs));
const visible = computed(() => fresh.value && imageSource.value && !failed.value);
const drawnFrame = computed(() => props.frame && loadedKey.value === imageKey.value ? {
  ...props.frame, sourceWidth: dimensions.value.width, sourceHeight: dimensions.value.height,
} : undefined);
const count = computed(() => props.frame?.objects.filter(object => props.showAllObjects || describeObject(object).visibleByDefault).length ?? 0);
const age = computed(() => props.frame ? Math.max(0, (now.value - frameTimestampMillis(props.frame.timestamp)) / 1000).toFixed(1) : '—');
const empty = computed(() => {
  if (failed.value) return '识别图片加载失败，请刷新后重试。';
  if (props.frame && !fresh.value) return '识别结果暂未更新，请检查任务状态或刷新连接。';
  if (props.frame && !imageSource.value) return '本次结果缺少配套图片，暂时无法展示目标位置。';
  return props.emptyText;
});
function onLoad(event: Event) {
  const target = event.target as HTMLImageElement;
  if (target.getAttribute('src') !== imageSource.value) return;
  dimensions.value = { width: target.naturalWidth, height: target.naturalHeight };
  loadedKey.value = imageKey.value;
}
watch(imageKey, () => { loadedKey.value = ''; failed.value = false; });

function takeScreenshot() {
  if (!visible.value || !image.value || !drawnFrame.value || !root.value) {
    message.warning('识别图片尚未就绪'); return;
  }
  const rect = root.value.getBoundingClientRect();
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(rect.width); canvas.height = Math.round(rect.height);
  const context = canvas.getContext('2d');
  if (!context) return;
  context.fillStyle = '#030711'; context.fillRect(0, 0, canvas.width, canvas.height);
  const scale = Math.min(rect.width / dimensions.value.width, rect.height / dimensions.value.height);
  const w = dimensions.value.width * scale; const h = dimensions.value.height * scale;
  context.drawImage(image.value, (rect.width - w) / 2, (rect.height - h) / 2, w, h);
  const overlay = root.value.querySelector('canvas');
  if (overlay && props.showBoxes) context.drawImage(overlay, 0, 0, canvas.width, canvas.height);
  canvas.toBlob(blob => {
    if (!blob) return;
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a'); anchor.href = url;
    anchor.download = `recognition-${Date.now()}.png`; anchor.click(); URL.revokeObjectURL(url);
  });
}
defineExpose({ takeScreenshot });
onMounted(() => { timer = setInterval(() => { now.value = Date.now(); }, 250); });
onBeforeUnmount(() => { if (timer) clearInterval(timer); });
</script>

<template>
  <div ref="root" class="recognition-frame" :data-frame-id="drawnFrame?.frameId" :data-object-count="visible ? count : undefined">
    <template v-if="visible">
      <img ref="image" :src="imageSource" :alt="title" @load="onLoad" @error="failed = true" />
      <PreviewOverlay :frame="drawnFrame" :historical="historical" :visible="showBoxes" :show-all-objects="showAllObjects" :max-age-ms="maxAgeMs" />
    </template>
    <div v-else class="recognition-frame__empty" role="status">
      <strong>{{ title }}</strong><span>{{ empty }}</span>
    </div>
    <div class="recognition-frame__caption">
      <strong>{{ title }}</strong>
      <span v-if="visible && drawnFrame">{{ count ? `本帧标出 ${count} 个目标` : emptyResultText }}</span>
      <span v-if="visible && !historical">采样距今 {{ age }} 秒</span>
      <span v-else-if="historical">{{ contextLabel || '告警时刻' }}</span>
    </div>
  </div>
</template>

<style scoped>
.recognition-frame { position: relative; width: 100%; height: 100%; min-height: 180px; overflow: hidden; color: #e2e8f0; background: #030711; }
.recognition-frame img { display: block; width: 100%; height: 100%; object-fit: contain; }
.recognition-frame__empty { position: absolute; inset: 0; display: flex; flex-direction: column; gap: 12px; align-items: center; justify-content: center; padding: 32px; text-align: center; }
.recognition-frame__empty span { max-width: 400px; font-size: 13px; color: #94a3b8; }
.recognition-frame__caption { position: absolute; right: 0; bottom: 0; left: 0; display: flex; flex-wrap: wrap; gap: 6px 16px; align-items: center; padding: 12px; font-size: 12px; background: linear-gradient(transparent, rgb(0 0 0 / 85%)); pointer-events: none; }
.recognition-frame__caption strong { margin-right: auto; }
</style>
