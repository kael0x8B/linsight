<script setup lang="ts">
import type { SourceClock } from './source-clock';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { EntryStationStatus } from '#/api/ai-video/task/entry-access';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { getEntryStationStatus } from '#/api/ai-video/task/entry-access';

import { capabilityKey, layerColor } from './recognition-layers';
import SynchronizedRecognitionVideo from './synchronized-recognition-video.vue';
import { useDisplayPreferences } from './use-display-preferences';
const props = withDefaults(defineProps<{camera?:AiVideoCameraApi.Camera; clock?:SourceClock; frames:Record<string,AiVideoCameraApi.OverlayFrame>; showAllObjects?:boolean; showOverlay?:boolean; video?:HTMLVideoElement}>(),{camera:undefined,clock:undefined,video:undefined,showOverlay:true,showAllObjects:false});
const emit = defineEmits<{displayed:[frame?:AiVideoCameraApi.OverlayFrame]; entries:[value:Record<string,EntryStationStatus>];}>();
const prefs = useDisplayPreferences(computed(() => props.camera?.id));
const entries = ref<Record<string,EntryStationStatus>>({});
let generation=0; let timer:ReturnType<typeof setTimeout>|undefined;
const entryIds=computed(()=>(props.camera?.recognitionCapabilities??[]).filter(v=>v.entryAccessId && v.effectiveStatus==='RUNNING' && !prefs.hidden.value.includes(capabilityKey(v))).map(v=>v.entryAccessId!).slice(0,16));
async function poll(request:number) {
  const results=await Promise.allSettled(entryIds.value.map(async id=>({id,value:await getEntryStationStatus(id)})));
  if(request!==generation)return;
  entries.value=Object.fromEntries(results.flatMap(result=>result.status==='fulfilled' && result.value.value.cameraId===props.camera?.id ? [[`entry-${result.value.id}`,result.value.value]] : []));
  emit('entries',entries.value);
  if(entryIds.value.length)timer=setTimeout(()=>void poll(request),600);
}
watch(()=>`${props.camera?.id}:${entryIds.value.join(',')}`,()=>{generation++;clearTimeout(timer);entries.value={};emit('entries',{});if(entryIds.value.length)void poll(generation);},{immediate:true});
onBeforeUnmount(()=>{generation++;clearTimeout(timer);});
const layers=computed(()=>(props.camera?.recognitionCapabilities??[]).map(cap=>{
  const key=capabilityKey(cap);const entry=entries.value[key];
  const raw=entry?.frame;
  const frame = cap.entryAccessId ? raw && Date.now()-Number(raw.timestamp)<3000 ? {...raw,sessionId:key,objects:raw.faces.map(face=>({class:'face',confidence:face.confidence,trackId:face.trackId,attributes:{},bbox:{x:face.x,y:face.y,width:face.width,height:face.height}}))} : undefined : props.frames[key];
  return {key,title:cap.algorithmName||cap.taskName,color:layerColor(key),visible:!prefs.hidden.value.includes(key),frame:cap.effectiveStatus==='RUNNING' && (cap.entryAccessId || frame?.runId===cap.activeRunId) ? frame : undefined};
}));
const regions=computed(()=>Object.entries(entries.value).flatMap(([key,value])=> value.roi && !prefs.hidden.value.includes(key) ? [{bbox:value.roi,title:'刷脸区域',color:layerColor(key)}] : []));
</script>
<template>
  <SynchronizedRecognitionVideo :video="video" :clock="clock" :layers="layers" :regions="regions" :show-all-objects="showAllObjects" :show-overlay="showOverlay" :title="camera?.name || '全部算法'" @displayed="frame => emit('displayed',frame)" />
</template>
