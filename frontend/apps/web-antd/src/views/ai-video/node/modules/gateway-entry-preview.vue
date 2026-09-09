<script setup lang="ts">
import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';

import { Alert, Button } from 'ant-design-vue';

import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';
import EntryFacePreview from '#/views/ai-video/live/modules/entry-face-preview.vue';

const props = defineProps<{ cameraId: number; cameraName: string; entryId: number; nodeId: number; online: boolean }>();
const { hasAccessByCodes: can } = useAccess();
const player = ref<InstanceType<typeof CameraPreviewPlayer>>();
const showOverlay = ref(true);
const camera = computed(() => ({ id: props.cameraId, name: props.cameraName, code: `camera-${props.cameraId}`, status: 0 }));
</script>
<template>
  <section class="mt-6 overflow-hidden rounded-xl border" data-testid="gateway-entry-preview">
    <div class="flex items-center justify-between gap-3 border-b p-4">
      <div><h3 class="font-semibold">入口刷脸画面</h3><p class="mt-1 text-xs text-muted-foreground">{{ cameraName }} · 仅显示当前网关的刷脸配置和结果</p></div>
      <div class="flex gap-2"><Button size="small" :type="showOverlay ? 'primary' : 'default'" @click="showOverlay = !showOverlay">识别 ROI</Button><Button size="small" @click="player?.takeScreenshot()">截图</Button><Button size="small" @click="player?.toggleFullscreen()">全屏</Button></div>
    </div>
    <Alert v-if="!can(['ai-video:camera:preview'])" class="m-4" type="info" message="暂无摄像头预览权限" show-icon />
    <Alert v-else-if="!online" class="m-4" type="warning" message="当前网关离线，恢复连接后可查看刷脸画面" show-icon />
    <CameraPreviewPlayer v-else ref="player" :key="`${nodeId}:${entryId}`" class="h-[min(65vh,620px)] min-h-80" :camera="camera" :node-id="nodeId" :overlay-enabled="false">
      <template #overlay="{ video, clock }"><EntryFacePreview :entry-id="entryId" :node-id="nodeId" :camera-id="cameraId" :video="video" :clock="clock" :show-overlay="showOverlay" /></template>
    </CameraPreviewPlayer>
  </section>
</template>
