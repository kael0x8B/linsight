<script setup lang="ts">
import type { RecognitionLayer } from './recognition-layers';
import type { SourceClock } from './source-clock';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { PreviewRegion } from '#/views/ai-video/live/modules/overlay-coordinate';

import { computed, nextTick, onBeforeUnmount, ref, shallowRef, watch } from 'vue';

import { $t } from '#/locales';
import { describeObject } from '#/views/ai-video/live/modules/overlay-presentation';
import PreviewOverlay from '#/views/ai-video/live/modules/preview-overlay.vue';

import { OverlayDelay } from './overlay-delay';
import PreviewBufferControl from './preview-buffer-control.vue';
import { RecognitionLayerBuffer } from './recognition-layers';
import { alignedOverlay } from './synchronized-overlay';
import { usePreviewBuffer } from './use-preview-buffer';

const props = withDefaults(
  defineProps<{
    analysisFps?: number;
    clock?: SourceClock;
    frame?: AiVideoCameraApi.OverlayFrame;
    layers?: RecognitionLayer[];
    local?: boolean;
    regions?: PreviewRegion[];
    showAllObjects?: boolean;
    showOverlay?: boolean;
    showRegions?: boolean;
    title?: string;
    video?: HTMLVideoElement;
  }>(),
  {
    analysisFps: undefined,
    clock: undefined,
    frame: undefined,
    layers: undefined,
    local: false,
    regions: () => [],
    showAllObjects: false,
    showOverlay: true,
    showRegions: undefined,
    title: 'AI 识别',
    video: undefined,
  },
);
const emit = defineEmits<{
  displayed: [frame?: AiVideoCameraApi.OverlayFrame];
}>();
const root = ref<HTMLElement>();
const displayed = shallowRef<AiVideoCameraApi.OverlayFrame>();
const status = ref('正在建立视频同步');
const rendered = ref(false);
const displayedPts = ref<number>();
const displayedStream = ref<string>();
const anchorDistanceMs = ref<number>();
const renderFps = ref(0);
const bufferMs = ref(0);
const interpolated = ref(false);
const heldObjects = ref(0);
const maxHoldAgeMs = ref(0);
const matchedLayers = ref(0);
const eligibleFrames = ref(0);
const matchedFrames = ref(0);
const maxAnchorDistanceMs = ref(0);
const maxObservedDistanceMs = ref(0);
const maxTrackingSpanMs = ref(0);
const presentedFrames = ref(0);
const screenshotUrl = ref('');
const screenshotName = ref('');
const adaptiveDelay = new OverlayDelay();
const { delayMs, setDelay, storageError } = usePreviewBuffer(
  computed(() => props.local),
);
let anchors: AiVideoCameraApi.OverlayFrame[] = [];
let callbackId: number | undefined;
let activeVideo: HTMLVideoElement | undefined;
let activeClock: SourceClock | undefined;
let timer: ReturnType<typeof setInterval> | undefined;
let fpsStart = performance.now();
let fpsPresented = 0;
let lastPaint = 0;
let lastStream: string | undefined;
let measuredRun: string | undefined;
let screenshotRequested = false;
const layerBuffer = new RecognitionLayerBuffer();
watch(
  () => props.layers,
  (layers) => {
    layerBuffer.update(layers ?? []);
  },
  { immediate: true },
);

function clearVideo() {
  adaptiveDelay.reset();
  if (callbackId !== undefined)
    activeVideo?.cancelVideoFrameCallback(callbackId);
  if (timer) clearInterval(timer);
  activeClock?.setDelay(0);
  callbackId = undefined;
  timer = undefined;
  displayed.value = undefined;
  heldObjects.value = 0;
  maxHoldAgeMs.value = 0;
  rendered.value = false;
  screenshotRequested = false;
  lastStream = undefined;
  displayedPts.value = undefined;
  displayedStream.value = undefined;
  emit('displayed', undefined);
}

// Only screenshots copy the native image. Flush the overlay for this rVFC frame
// before compositing; normal playback does not copy video through a Canvas.
function captureScreenshot(video: HTMLVideoElement) {
  if (!root.value) return;
  const identity = displayed.value;
  const rect = root.value.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const copy = document.createElement('canvas');
  copy.width = Math.max(1, Math.round(rect.width * dpr));
  copy.height = Math.max(1, Math.round(rect.height * dpr));
  const context = copy.getContext('2d');
  if (!context) return;
  context.fillStyle = '#030711';
  context.fillRect(0, 0, copy.width, copy.height);
  const scale = Math.min(
    copy.width / video.videoWidth,
    copy.height / video.videoHeight,
  );
  const width = video.videoWidth * scale;
  const height = video.videoHeight * scale;
  context.drawImage(
    video,
    (copy.width - width) / 2,
    (copy.height - height) / 2,
    width,
    height,
  );
  void nextTick()
    .then(() => nextTick())
    .then(() => {
      if (!root.value || displayed.value !== identity) {
        screenshotRequested = true;
        return;
      }
      const overlay =
        root.value.querySelector<HTMLCanvasElement>('.preview-overlay');
      if (overlay && (props.showOverlay || props.showRegions))
        context.drawImage(overlay, 0, 0, copy.width, copy.height);
      copy.toBlob((blob) => {
        if (!blob) return;
        if (screenshotUrl.value) URL.revokeObjectURL(screenshotUrl.value);
        screenshotUrl.value = URL.createObjectURL(blob);
        screenshotName.value = `recognition-${Date.now()}.png`;
        const anchor = document.createElement('a');
        anchor.href = screenshotUrl.value;
        anchor.download = screenshotName.value;
        document.body.append(anchor);
        anchor.click();
        anchor.remove();
        // Embedded browser downloads may consume the Blob asynchronously. Keep
        // one image available until the next screenshot or component disposal.
      });
    });
}

function paint(
  now: number,
  metadata: VideoFrameCallbackMetadata & { rtpTimestamp?: number },
) {
  const video = activeVideo;
  if (!video) return;
  callbackId = video.requestVideoFrameCallback(paint);
  const stamp =
    metadata.rtpTimestamp === undefined
      ? undefined
      : activeClock?.read(metadata.rtpTimestamp);
  lastPaint = now;
  presentedFrames.value = metadata.presentedFrames;
  if (!fpsPresented) {
    fpsPresented = metadata.presentedFrames;
    fpsStart = now;
  }
  if (now - fpsStart >= 1000) {
    renderFps.value =
      ((metadata.presentedFrames - fpsPresented) * 1000) / (now - fpsStart);
    fpsStart = now;
    fpsPresented = metadata.presentedFrames;
  }
  if (!stamp) {
    rendered.value = false;
    displayed.value = undefined;
    heldObjects.value = 0;
    maxHoldAgeMs.value = 0;
    status.value = '视频播放中 · 等待同步信息';
    emit('displayed', undefined);
    return;
  }
  if (lastStream !== stamp.streamId) {
    lastStream = stamp.streamId;
    anchors = anchors.filter((frame) => frame.streamId === stamp.streamId);
  }
  const overlay = props.layers
    ? layerBuffer.align(stamp, (key) => activeClock?.locate(key))
    : alignedOverlay(anchors, stamp);
  if (
    props.frame?.streamId === stamp.streamId ||
    props.layers?.some((layer) => layer.visible && layer.frame)
  ) {
    eligibleFrames.value++;
    if (overlay) {
      matchedFrames.value++;
      maxAnchorDistanceMs.value = Math.max(
        maxAnchorDistanceMs.value,
        overlay.anchorDistanceMs,
      );
      if (overlay.interpolated) {
        maxTrackingSpanMs.value = Math.max(
          maxTrackingSpanMs.value,
          overlay.trackingSpanMs ?? 0,
        );
      } else if (!overlay.heldObjects)
        maxObservedDistanceMs.value = Math.max(
          maxObservedDistanceMs.value,
          overlay.anchorDistanceMs,
        );
    }
  }
  matchedLayers.value = 0;
  if (overlay)
    matchedLayers.value =
      'layerCount' in overlay ? Number(overlay.layerCount) : 1;
  displayed.value = overlay
    ? {
        ...overlay.frame,
        sourceWidth: video.videoWidth,
        sourceHeight: video.videoHeight,
      }
    : undefined;
  anchorDistanceMs.value = overlay?.anchorDistanceMs;
  interpolated.value = overlay?.interpolated ?? false;
  heldObjects.value = overlay?.heldObjects ?? 0;
  maxHoldAgeMs.value = overlay?.maxHoldAgeMs ?? 0;
  displayedPts.value = stamp.sourcePts;
  displayedStream.value = stamp.streamId;
  bufferMs.value = Math.round(stamp.bufferMs);
  rendered.value = true;
  if (overlay)
    status.value = props.layers
      ? `视频与 ${matchedLayers.value} 项算法已同步`
      : '视频与识别已同步';
  else
    status.value =
      props.frame || props.layers?.some((layer) => layer.visible && layer.frame)
        ? '视频播放中 · 等待对应帧的识别结果'
        : '视频播放中 · 等待识别任务';
  emit('displayed', displayed.value);
  if (screenshotRequested) {
    screenshotRequested = false;
    captureScreenshot(video);
  }
}

watch(
  () =>
    props.frame ??
    props.layers?.find(
      (layer) =>
        layer.visible && layer.frame?.streamId === activeClock?.streamId,
    )?.frame,
  (frame) => {
    if (!frame) {
      anchors = [];
      displayed.value = undefined;
      emit('displayed', undefined);
      return;
    }
    const previous = anchors.at(-1);
    if (measuredRun !== frame.runId) {
      measuredRun = frame.runId;
      eligibleFrames.value = 0;
      matchedFrames.value = 0;
      maxAnchorDistanceMs.value = 0;
      maxObservedDistanceMs.value = 0;
      maxTrackingSpanMs.value = 0;
    }
    if (
      previous &&
      (previous.runId !== frame.runId ||
        previous.taskId !== frame.taskId ||
        previous.streamId !== frame.streamId)
    )
      anchors = [];
    if (
      frame.streamId &&
      frame.sourcePts !== undefined &&
      previous?.frameId !== frame.frameId
    ) {
      anchors.push(frame);
      if (anchors.length > 40) anchors.shift();
      if (
        displayedPts.value !== undefined &&
        displayedStream.value === frame.streamId
      ) {
        // Retain delivery diagnostics without overriding the viewer's fixed buffer.
        adaptiveDelay.observe(
          `${frame.streamId}:${frame.runId}:${frame.taskId}`,
          frame.sourcePts,
          displayedPts.value,
          bufferMs.value,
          performance.now(),
        );
      }
    }
  },
  { immediate: true },
);

watch(
  [() => props.video, () => props.clock],
  ([video, clock]) => {
    clearVideo();
    activeVideo = video;
    activeClock = clock;
    if (!video || !clock) return;
    if (!clock.supported || !video.requestVideoFrameCallback) {
      status.value = '当前浏览器不支持同步识别，请使用新版 Chrome';
      return;
    }
    clock.setDelay(delayMs.value);
    fpsStart = performance.now();
    fpsPresented = 0;
    lastPaint = 0;
    callbackId = video.requestVideoFrameCallback(paint);
    timer = setInterval(() => {
      if (lastPaint && performance.now() - lastPaint > 250) {
        displayed.value = undefined;
        heldObjects.value = 0;
        maxHoldAgeMs.value = 0;
        emit('displayed', undefined);
        if (performance.now() - lastPaint > 1200) {
          rendered.value = false;
          status.value = '视频正在重连';
        }
      }
    }, 100);
  },
  { immediate: true },
);

watch(delayMs, () => {
  if (activeVideo && activeClock?.supported) activeClock.setDelay(delayMs.value);
});

function takeScreenshot() {
  screenshotRequested = true;
}
defineExpose({ takeScreenshot });
onBeforeUnmount(() => {
  clearVideo();
  if (screenshotUrl.value) URL.revokeObjectURL(screenshotUrl.value);
});
</script>

<template>
  <div
    ref="root"
    class="synchronized-video"
    :data-sync-status="status"
    :data-source-pts="displayedPts"
    :data-stream-id="displayedStream"
    :data-anchor-distance-ms="anchorDistanceMs"
    :data-display-fps="renderFps"
    :data-buffer-ms="bufferMs"
    :data-target-buffer-ms="delayMs"
    :data-interpolated="interpolated"
    :data-held-objects="heldObjects"
    :data-max-hold-age-ms="maxHoldAgeMs"
    :data-result-cadence-ms="adaptiveDelay.cadenceMs"
    :data-result-delivery-lag-ms="adaptiveDelay.deliveryLagMs"
    :data-frame-id="displayed?.frameId"
    :data-object-count="displayed?.objects.length"
    :data-visible-object-count="
      displayed?.objects.filter(
        (object) => showAllObjects || describeObject(object).visibleByDefault,
      ).length ?? 0
    "
    :data-matched-layers="matchedLayers"
    :data-visible-layers="
      layers
        ?.filter((layer) => layer.visible)
        .map((layer) => layer.key)
        .join(',')
    "
    :data-result-source-pts="frame?.sourcePts"
    :data-result-stream-id="frame?.streamId"
    :data-eligible-frames="eligibleFrames"
    :data-matched-frames="matchedFrames"
    :data-max-anchor-distance-ms="maxAnchorDistanceMs"
    :data-max-observed-distance-ms="maxObservedDistanceMs"
    :data-max-tracking-span-ms="maxTrackingSpanMs"
    :data-presented-frames="presentedFrames"
    data-playback-mode="native-video"
    @capture-recognition="takeScreenshot"
  >
    <PreviewOverlay
      :regions="regions"
      :show-regions="showRegions"
      :video-width="video?.videoWidth"
      :video-height="video?.videoHeight"
      :frame="displayed"
      historical
      :visible="rendered && showOverlay"
      :show-all-objects="showAllObjects"
    />
    <a
      v-if="screenshotUrl"
      class="screenshot-download"
      :href="screenshotUrl"
      :download="screenshotName"
      >截图已生成 · 保存图片</a
    >
    <div class="synchronized-video__caption">
      <strong>{{ title }}</strong
      ><span>{{ status }}</span>
      <span v-if="rendered && heldObjects">{{
        $t('page.aiVideo.recognition.shortHold')
      }}</span>
      <span v-if="rendered">播放 {{ renderFps.toFixed(1) }} FPS</span>
      <span v-if="analysisFps !== undefined"
        >分析 {{ analysisFps.toFixed(2) }} FPS</span
      >
      <PreviewBufferControl
        :model-value="delayMs"
        :actual-ms="rendered ? bufferMs : undefined"
        :storage-error="storageError"
        :disabled="!clock?.supported"
        @update:model-value="setDelay"
      />
    </div>
  </div>
</template>

<style scoped>
.synchronized-video {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 0;
  color: #e2e8f0;
  pointer-events: none;
}

.synchronized-video__caption {
  position: absolute;
  inset: auto 0 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px 14px;
  padding: 12px;
  font-size: 12px;
  background: linear-gradient(transparent, rgb(0 0 0 / 85%));
}

.synchronized-video__caption strong {
  margin-right: auto;
}

.screenshot-download {
  position: absolute;
  top: 12px;
  left: 12px;
  padding: 6px 10px;
  color: #e2e8f0;
  pointer-events: auto;
  background: #15243c;
  border-radius: 6px;
}
</style>
