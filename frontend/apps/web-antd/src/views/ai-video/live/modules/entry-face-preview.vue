<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { EntryStationStatus } from '#/api/ai-video/task/entry-access';
import type { SourceClock } from '#/components/ai-video/source-clock';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { getEntryStationStatus } from '#/api/ai-video/task/entry-access';
import SynchronizedRecognitionVideo from '#/components/ai-video/synchronized-recognition-video.vue';
import { $t } from '#/locales';
const props = withDefaults(
  defineProps<{
    cameraId: number;
    clock?: SourceClock;
    entryId: number;
    nodeId?: number;
    showOverlay?: boolean;
    video?: HTMLVideoElement;
  }>(),
  { clock: undefined, nodeId: undefined, showOverlay: true, video: undefined },
);
const emit = defineEmits<{ status: [value?: EntryStationStatus] }>();
const status = ref<EntryStationStatus>();
const failed = ref(false);
const sync = ref<{ takeScreenshot: () => void }>();
const height = ref(480);
const width = ref(640);
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let attached: HTMLVideoElement | undefined;
function dimensions() {
  width.value = attached?.videoWidth || 640;
  height.value = attached?.videoHeight || 480;
}
watch(
  () => props.video,
  (video) => {
    attached?.removeEventListener('loadedmetadata', dimensions);
    attached = video;
    attached?.addEventListener('loadedmetadata', dimensions);
    dimensions();
  },
  { immediate: true },
);
const frame = computed<AiVideoCameraApi.OverlayFrame | undefined>(() => {
  const value = status.value?.frame;
  if (
    failed.value ||
    !value ||
    value.cameraId !== props.cameraId ||
    Date.now() - Number(value.timestamp) > 3000 ||
    ['DISABLED', 'NO_FRESH_FRAME', 'OFFLINE', 'STATION_UNAVAILABLE'].includes(
      status.value?.state || '',
    )
  )
    return;
  return {
    ...value,
    sessionId: `entry-${props.entryId}`,
    objects: value.faces.map((face) => ({
      class: 'face',
      confidence: face.confidence,
      trackId: face.trackId,
      attributes: {},
      bbox: { x: face.x, y: face.y, width: face.width, height: face.height },
    })),
  };
});
async function poll(request: number) {
  try {
    const value = await getEntryStationStatus(props.entryId, props.nodeId);
    if (request !== generation) return;
    if (value.cameraId !== props.cameraId || (props.nodeId !== undefined && value.nodeId !== props.nodeId)) throw new Error('Entry scope mismatch');
    status.value = value;
    failed.value = false;
    emit('status', value);
  } catch {
    if (request === generation) {
      failed.value = true;
      status.value = undefined;
      emit('status', undefined);
    }
  } finally {
    if (request === generation)
      timer = setTimeout(() => void poll(request), 400);
  }
}
watch(
  () => [props.entryId, props.nodeId, props.cameraId],
  () => {
    generation++;
    if (timer) clearTimeout(timer);
    status.value = undefined;
    emit('status', undefined);
    void poll(generation);
  },
  { immediate: true },
);
onBeforeUnmount(() => {
  generation++;
  if (timer) clearTimeout(timer);
  attached?.removeEventListener('loadedmetadata', dimensions);
  emit('status', undefined);
});
defineExpose({ takeScreenshot: () => sync.value?.takeScreenshot() });
</script>
<template>
  <div
    class="entry-face-layer"
    :data-entry-id="entryId"
    :data-station-state="status?.state"
  >
    <SynchronizedRecognitionVideo
      ref="sync"
      :video="video"
      :clock="clock"
      :frame="frame"
      :show-overlay="showOverlay"
      :title="$t('entry-access.title')"
    />
    <svg
      v-if="showOverlay && status?.roi"
      class="entry-roi"
      :viewBox="`0 0 ${width} ${height}`"
      preserveAspectRatio="xMidYMid meet"
      aria-label="刷脸区域"
    >
      <rect
        :x="status.roi.x * width"
        :y="status.roi.y * height"
        :width="status.roi.width * width"
        :height="status.roi.height * height"
      />
    </svg>
    <div class="entry-prompt">
      {{
        failed
          ? $t('entry-access.queryFailed')
          : status
            ? $t(`entry-access.stationStates.${status.state}`)
            : $t('camera-face.loadingLayer')
      }}
    </div>
  </div>
</template>
<style scoped>
.entry-face-layer {
  position: absolute;
  inset: 0;
  pointer-events: none;
}
.entry-roi {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
.entry-roi rect {
  fill: rgb(59 130 246 / 8%);
  stroke: #60a5fa;
  stroke-width: 2;
  stroke-dasharray: 8 5;
  vector-effect: non-scaling-stroke;
}
.entry-prompt {
  position: absolute;
  top: 12px;
  left: 12px;
  right: 12px;
  width: fit-content;
  padding: 8px 12px;
  border-radius: 6px;
  background: rgb(2 6 23 / 80%);
  color: #fff;
  font-size: 14px;
}
</style>
