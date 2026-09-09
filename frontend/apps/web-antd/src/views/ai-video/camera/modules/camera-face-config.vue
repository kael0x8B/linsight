<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { EntryAccess, FaceReference } from '#/api/ai-video/task/entry-access';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenModal } from '@vben/common-ui';

import { Alert, Button, Collapse, CollapsePanel, message, Space, Spin, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getCamera } from '#/api/ai-video/camera';
import { getModelPage, getModelVersionList, getNodeModelDeployments } from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { getRecognitionLibraryPage } from '#/api/ai-video/recognition-library';
import { listEntryAccess, listFaceReferences, saveEntryAccess } from '#/api/ai-video/task/entry-access';
import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';
import { $t } from '#/locales';

import EnrollmentForm from '../../recognition-library/modules/entry-access-modal.vue';
const props=defineProps<{cameraId:number;entryAccessId?:number;nodeId?:number;}>();
const emit=defineEmits(['success']);
const {hasAccessByCodes}=useAccess();
const t=(key:string)=>$t(`camera-face.${key}`);
const camera=ref<AiVideoCameraApi.Camera>();
const existing=ref<EntryAccess>();
const failed=ref(false); const loading=ref(true); const preview=ref(false); const saving=ref(false);
const libraryId=ref<number>(); const boundNodeId=ref<number>();
const models=ref<Array<{label:string;value:number}>>([]); const nodes=ref<Array<{label:string;value:number}>>([]);
const people=ref<FaceReference[]>([]);
const roi=ref({x:0,y:0,width:1,height:1});
const snapshot=ref('');
const player=ref<InstanceType<typeof CameraPreviewPlayer>>();
let disposed=false; let peopleGeneration=0;
let anchor:undefined|{x:number;y:number};
const validRoi=computed(()=>roi.value.width>=.01&&roi.value.height>=.01&&roi.value.width*roi.value.height<=.5&&roi.value.x+roi.value.width<=1&&roi.value.y+roi.value.height<=1);
const [Enrollment,enrollmentApi]=useVbenModal({connectedComponent:EnrollmentForm,destroyOnClose:true});
const [Form,form]=useVbenForm({commonConfig:{componentProps:{class:'w-full'}},showDefaultActions:false,layout:'vertical',schema:[
  {fieldName:'libraryId',label:t('library'),component:'Select',rules:'required',componentProps:{onChange:chooseLibrary}},
  {fieldName:'allowedEntryIds',label:t('allowed'),component:'Select',defaultValue:[],componentProps:{mode:'multiple',options:[]}},
]});
const [Advanced,advanced]=useVbenForm({commonConfig:{componentProps:{class:'w-full'}},showDefaultActions:false,layout:'vertical',wrapperClass:'grid-cols-2',schema:[
  
  {fieldName:'modelVersionId',label:t('model'),component:'Select',rules:'required',componentProps:{onChange:()=>loadPeople(true)}},
  {fieldName:'similarityThreshold',label:t('threshold'),component:'InputNumber',defaultValue:.6,componentProps:{min:.1,max:1,step:.01},rules:'required'},
  {fieldName:'ambiguityMargin',label:t('margin'),component:'InputNumber',defaultValue:.08,componentProps:{min:.01,max:.5,step:.01},rules:'required'},
  {fieldName:'temporalN',label:t('votes'),component:'InputNumber',defaultValue:3,componentProps:{min:2,max:10},rules:'required'},
  {fieldName:'temporalM',label:t('window'),component:'InputNumber',defaultValue:5,componentProps:{min:2,max:15},rules:'required'},
  ...(['x','y','width','height'] as const).map(key=>({fieldName:`roi-${key}`,label:t(`roi-${key}`),component:'InputNumber',componentProps:{min:0,max:100,step:1,onChange:(value:number)=>{roi.value={...roi.value,[key]:Number(value)/100};}}})),
]});
async function chooseLibrary(id:number){libraryId.value=id;await loadPeople(true);}
async function loadPeople(selectAll=false){
  const generation=++peopleGeneration;
  if(!libraryId.value)return;
  try{
    const list=await listFaceReferences(libraryId.value);if(disposed||generation!==peopleGeneration)return;
    const parameters=await advanced.getValues();
    people.value=list.filter(p=>p.status==='READY'&&p.modelVersionId===parameters.modelVersionId);
    form.updateSchema([{fieldName:'allowedEntryIds',componentProps:{options:people.value.map(p=>({label:`${p.name} · ${p.externalCode}`,value:p.entryId}))}}]);
    if(selectAll)await form.setFieldValue('allowedEntryIds',people.value.map(p=>p.entryId));
  }catch{failed.value=true;}
}
async function load(){
  loading.value=true;failed.value=false;
  try{
    const [cam,entries,ns,libs,modelPage]=await Promise.all([getCamera(props.cameraId),listEntryAccess(props.cameraId,props.nodeId),getNodeSimpleList(),getRecognitionLibraryPage({pageNo:1,pageSize:100,libraryType:'FACE',status:0}),getModelPage({pageNo:1,pageSize:100})]);
    const faceModel=modelPage.list.find(m=>m.code==='active-entry-face-yunet-sface');
    const versions=faceModel?await getModelVersionList(Number(faceModel.id)):[];
    if(disposed)return;
    camera.value=cam;
    const scoped=entries.filter(e=>e.cameraId===props.cameraId && (props.nodeId===undefined || e.nodeId===props.nodeId));
    existing.value=props.entryAccessId ? scoped.find(e=>e.id===props.entryAccessId) : props.nodeId ? scoped.find(e=>e.triggerMode==='FACE_ZONE') : undefined;
    if(props.entryAccessId && !existing.value) throw new Error('Configuration outside gateway scope');
    boundNodeId.value=props.nodeId??existing.value?.nodeId;
    if(!boundNodeId.value) throw new Error('Gateway context required');
    const deployments=await getNodeModelDeployments(boundNodeId.value);
    const installed=new Set(deployments.filter(d=>d.nodeId===boundNodeId.value&&d.actualStatus==='READY').map(d=>d.modelVersionId));
    nodes.value=ns.map(n=>({label:n.name,value:n.id}));
    models.value=versions.filter(v=>{try{return installed.has(v.id)&& JSON.parse(v.runtimeManifest??'{}').decoder?.type==='FACE_PAIR_SFACE_RKNN'&&v.executionStatus==='READY'&&v.publishStatus==='PUBLISHED';}catch{return false;}}).map(v=>({label:`${v.version} · NPU`,value:v.id}));
    form.updateSchema([{fieldName:'libraryId',componentProps:{options:libs.list.map(l=>({label:l.name,value:l.id}))}}]);
    advanced.updateSchema([{fieldName:'modelVersionId',componentProps:{options:models.value}}]);
    const e=existing.value;
    libraryId.value=e?.libraryId??libs.list.find(l=>l.engineModelVersionId===models.value[0]?.value)?.id;
    roi.value=e?{...e.roi}:{x:0,y:0,width:1,height:1};
    await advanced.setValues({nodeId:boundNodeId.value,modelVersionId:e?.modelVersionId??models.value[0]?.value,similarityThreshold:e?.similarityThreshold??.6,ambiguityMargin:e?.ambiguityMargin??.08,temporalN:e?.temporalN??3,temporalM:e?.temporalM??5});
    await syncRoi();
    await form.setValues({libraryId:libraryId.value,allowedEntryIds:e?.allowedEntryIds??[]});
    await loadPeople(!e);
  }catch{failed.value=true;}finally{loading.value=false;}
}
async function registerPeople(){
  const values=await advanced.getValues();enrollmentApi.setData({enrollmentOnly:true,libraryId:libraryId.value,nodeId:boundNodeId.value,modelVersionId:values.modelVersionId}).open();
}
function capture(){const frame=player.value?.captureFrame();if(!frame){message.warning(t('waitVideo'));return;}snapshot.value=frame.dataUrl;preview.value=false;}
function point(event:PointerEvent){const box=(event.currentTarget as SVGSVGElement).getBoundingClientRect();return {x:Math.max(0,Math.min(1,(event.clientX-box.left)/box.width)),y:Math.max(0,Math.min(1,(event.clientY-box.top)/box.height))};}
function begin(event:PointerEvent){if(event.button!==0)return;anchor=point(event);(event.currentTarget as SVGSVGElement).setPointerCapture(event.pointerId);}
function draw(event:PointerEvent){if(!anchor)return;const p=point(event);roi.value={x:Math.min(anchor.x,p.x),y:Math.min(anchor.y,p.y),width:Math.abs(p.x-anchor.x),height:Math.abs(p.y-anchor.y)};}
function end(event:PointerEvent){draw(event);anchor=undefined;void syncRoi();}
async function syncRoi(){await advanced.setValues(Object.fromEntries(Object.entries(roi.value).map(([key,value])=>[`roi-${key}`,Math.round(value*10000)/100])));}
function centerZone(){roi.value={x:.25,y:.1,width:.5,height:.8};void syncRoi();}
async function save(enabled:boolean){
  if(failed.value||!boundNodeId.value)return;
  if(!(await form.validate()).valid||!(await advanced.validate()).valid)return;
  if(enabled&&(!validRoi.value||!people.value.length)){message.warning(t('enableRequirements'));return;}
  saving.value=true;
  try{
    const base=await form.getValues(); const parameters=await advanced.getValues();
    for(const key of Object.keys(parameters))if(key.startsWith('roi-'))delete parameters[key];
    const id=await saveEntryAccess({...base,...parameters,nodeId:boundNodeId.value,id:existing.value?.id,version:existing.value?.version??0,name:existing.value?.name??`${camera.value?.name} · ${t('algorithm')}`,cameraId:props.cameraId,enabled,triggerMode:'FACE_ZONE',roiX:roi.value.x,roiY:roi.value.y,roiWidth:roi.value.width,roiHeight:roi.value.height});
    existing.value=(await listEntryAccess(props.cameraId,props.nodeId)).find(e=>e.id===id);message.success(t('saved'));emit('success');
  }catch{message.error(t('saveFailed'));}finally{saving.value=false;}
}
onMounted(load);
onBeforeUnmount(()=>{disposed=true;peopleGeneration++;preview.value=false;snapshot.value='';});
</script>
<template>
  <Enrollment @references-changed="loadPeople(false)" />
  <Spin :spinning="loading">
    <div class="space-y-4">
      <Alert v-if="failed" type="error" show-icon :message="t('loadFailed')"><template #action><Button @click="load">{{ t('retry') }}</Button></template></Alert>
      <p>{{ t('hint') }}</p>
      <p class="rounded-lg border bg-muted/30 p-3" data-testid="face-gateway-owner"><strong>{{ t('node') }}：</strong>{{ nodes.find(n=>n.value === boundNodeId)?.label ?? t('selectNode') }}</p>
      <Alert v-if="!loading && !failed && !models.length" type="warning" show-icon :message="t('noLocalModel')" />
      <Form />
      <p class="text-xs text-muted-foreground">{{ t('permissionHint') }}</p>
      <Space wrap><Button v-if="hasAccessByCodes(['ai-video:library:create','ai-video:model:test'])" @click="registerPeople">{{ t('register') }}</Button><Button @click="loadPeople(false)">{{ t('refreshPeople') }}</Button><Button :disabled="!people.length" @click="form.setFieldValue('allowedEntryIds',people.map(p=>p.entryId))">{{ t('selectAll') }}</Button><Tag>{{ people.length }} {{ t('readyPeople') }}</Tag></Space>
      <Alert v-if="!loading && !people.length" type="info" show-icon :message="t('emptyPeople')" />
      <div class="rounded-lg border p-3">
        <div class="mb-2 flex flex-wrap items-center justify-between gap-2"><strong>{{ t('zone') }}</strong><Button :disabled="!boundNodeId" @click="preview = !preview">{{ t('preview') }}</Button></div>
        <template v-if="preview"><div class="h-72"><CameraPreviewPlayer ref="player" :camera="camera" :node-id="boundNodeId" :overlay-enabled="false" compact /></div><Button class="mt-2" @click="capture">{{ t('capture') }}</Button></template>
        <div v-if="snapshot" class="relative mt-2 overflow-hidden rounded">
          <img :src="snapshot" :alt="t('zone')" class="block w-full" />
          <svg viewBox="0 0 1 1" preserveAspectRatio="none" class="absolute inset-0 h-full w-full touch-none cursor-crosshair" :aria-label="t('draw')" @pointerdown="begin" @pointermove="draw" @pointerup="end" @pointercancel="anchor = undefined">
            <rect :x="roi.x" :y="roi.y" :width="roi.width" :height="roi.height" fill="#1677ff33" stroke="#1677ff" stroke-width=".006" />
          </svg>
        </div>
        <p class="mt-2 text-sm text-muted-foreground">{{ snapshot ? t('draw') : t('zoneHint') }}</p>
        <p class="mt-2 text-sm" :class="validRoi ? 'text-green-600' : 'text-orange-600'">{{ t(validRoi ? 'zoneReady' : 'zoneRequired') }}</p>
        <Button size="small" class="mt-2" @click="centerZone">{{ t('centerZone') }}</Button>
      </div>
      <Collapse><CollapsePanel key="advanced" :header="t('advanced')" :force-render="true"><Advanced /></CollapsePanel></Collapse>
      <p class="text-xs text-muted-foreground">{{ nodes.find(n=>n.value === boundNodeId)?.label ?? t('selectNode') }} · NPU · {{ t('automatic') }}</p>
      <Space wrap>
        <Button :disabled="loading || failed" :loading="saving" @click="save(existing?.enabled ?? false)">{{ t('save') }}</Button>
        <span class="text-sm text-muted-foreground">启停请前往所属网关的“识别算法”。</span>
      </Space>
    </div>
  </Spin>
</template>
