<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { GatewayTask, GatewayTransport } from '#/api/ai-video/node/gateway';
import type { PreviewTransport } from '#/components/ai-video/preview-transport';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Switch, Tooltip } from 'ant-design-vue';

import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';
import { layerColor } from '#/components/ai-video/recognition-layers';
import SynchronizedRecognitionVideo from '#/components/ai-video/synchronized-recognition-video.vue';
import { useDisplayPreferences } from '#/components/ai-video/use-display-preferences';

import { acceptsTaskFrame } from '../../live/modules/overlay-presentation';
const props = withDefaults(defineProps<{cameraName:string;local?:boolean;task:GatewayTask;tasks:GatewayTask[];title:string;transport:GatewayTransport}>(),{local:false});
const taskId=props.task.config.taskId;
const cameraId=computed(()=>props.task.config.cameraId);
const camera=computed(()=>({id:cameraId.value,name:props.cameraName,code:`camera-${cameraId.value}`,status:0}));
const prefs=useDisplayPreferences(cameraId,props.local);
const session=ref<AiVideoCameraApi.PreviewSession>();
const frames=ref<Record<string,AiVideoCameraApi.OverlayFrame>>({});
const showAllObjects=ref(false);const showOverlay=ref(true);const frameError=ref(false);
const player=ref<InstanceType<typeof CameraPreviewPlayer>>();
const cameraTasks=computed(()=>props.tasks.filter(t=>t.config.cameraId===cameraId.value));
const layers=computed(()=>cameraTasks.value.map(t=>{const key=`task-${t.config.taskId}`;const frame=frames.value[key];return {key,title:t.name,color:layerColor(key),visible:!prefs.hidden.value.includes(key),frame:t.enabled && t.status.status==='RUNNING' && frame?.runId===(t.status.runId??t.config.runId) ? frame : undefined};}));
const signaling:PreviewTransport={create:offer=>props.transport('preview.open',{taskId,offerSdp:offer.offerSdp,offerType:offer.offerType}),get:sessionId=>props.transport('preview.status',{taskId,sessionId}),release:sessionId=>props.transport('preview.close',{taskId,sessionId})};
let generation=0;let timer:ReturnType<typeof setTimeout>|undefined;let disposed=false;
watch(()=>session.value?.sessionId,sessionId=>{const request=++generation;clearTimeout(timer);frames.value={};if(sessionId)void readFrames(sessionId,request);});
async function readFrames(sessionId:string,request:number){
 try {
  const results=await props.transport<AiVideoCameraApi.OverlayFrame[]>('preview.frames',{taskId,sessionId});
  if(disposed||request!==generation)return;
  const updated={...frames.value};
  for(const result of results){const task=cameraTasks.value.find(t=>t.config.taskId===result.taskId);const key=`task-${result.taskId}`;
   if(task && result.cameraId===cameraId.value && result.sessionId===sessionId && acceptsTaskFrame(result,{taskId:task.config.taskId,activeRunId:task.status.runId??task.config.runId,effectiveStatus:task.enabled?task.status.status:'STOPPED'},updated[key]))updated[key]=result;
  }
  frames.value=updated;frameError.value=false;
 } catch {if(disposed||request!==generation)return;frames.value={};frameError.value=true;}
 if(!disposed&&request===generation)timer=setTimeout(()=>void readFrames(sessionId,request),frameError.value?1500:150);
}
onBeforeUnmount(()=>{disposed=true;generation++;clearTimeout(timer);});
</script>
<template>
 <div class="gateway-recognition">
  <div class="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-3">
   <span class="text-xs text-muted-foreground">{{ local ? '本地显示偏好独立保存，不修改平台设置' : '沿用实时预览中的账号图层偏好' }} · 全算法叠加</span>
   <div class="flex items-center gap-2">
    <Button size="small" :type="showOverlay ? 'primary' : 'default'" :aria-pressed="showOverlay" @click="showOverlay = !showOverlay">识别 ROI</Button>
    <Tooltip title="截图"><Button type="text" aria-label="截图" @click="player?.takeScreenshot()"><IconifyIcon icon="lucide:camera" /></Button></Tooltip>
    <Tooltip title="全屏"><Button type="text" aria-label="全屏" @click="player?.toggleFullscreen()"><IconifyIcon icon="lucide:maximize" /></Button></Tooltip>
   </div>
  </div>
  <div class="flex flex-wrap gap-4 border-b px-5 py-3">
   <label v-for="layer in layers" :key="layer.key" class="flex items-center gap-2 text-xs"><i class="h-2 w-2 rounded-full" :style="{background:layer.color}"></i>{{ layer.title }}<Switch size="small" :aria-label="`${layer.title}图层`" :checked="layer.visible" :disabled="!prefs.ready.value || prefs.saving.value" @change="value=>prefs.setVisible(layer.key,Boolean(value))" /></label>
   <label class="flex items-center gap-2 text-xs"><Switch v-model:checked="showAllObjects" size="small" />显示合规与待确认目标</label>
  </div>
  <Alert v-if="prefs.error.value" :message="prefs.error.value" type="warning" />
  <Alert v-if="frameError" type="warning" message="多算法结果暂不可用，正在重试；旧版网关需升级以支持全算法预览。视频继续播放。" show-icon />
  <CameraPreviewPlayer ref="player" class="gateway-recognition__player" :camera="camera" :transport="signaling" :overlay-enabled="false" @session="value=>session = value">
   <template #overlay="{video,clock}"><SynchronizedRecognitionVideo class="gateway-recognition__overlay" :video="video" :clock="clock" :layers="layers" :title="cameraName" :show-all-objects="showAllObjects" :show-overlay="showOverlay" /></template>
  </CameraPreviewPlayer>
 </div>
</template>
<style scoped>
.gateway-recognition__player { height:min(65vh,620px);min-height:320px; }
.gateway-recognition__overlay {position:absolute;inset:0;}
.gateway-recognition :deep(.camera-preview-player__statusbar) {display:none;}
</style>
