<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Checkbox, message, Select, TabPane, Tabs, Tag, Upload } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getCameraPage } from '#/api/ai-video/camera';
import { getModelPage, getModelVersionList } from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { getRecognitionLibraryPage } from '#/api/ai-video/recognition-library';
import * as api from '#/api/ai-video/task/entry-access';
import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';
import { $t } from '#/locales';
const emit=defineEmits(['referencesChanged']);
const enrollmentOnly=ref(false);
const existingEntry=ref<{externalCode:string;id:number;mediaRef?:string;name:string;}>();
const t = (key: string) => $t(`entry-access.${key}`);
const {hasAccessByCodes} = useAccess();
const canEdit = computed(()=>hasAccessByCodes(['ai-video:task:update']));
const canEnroll = computed(()=>hasAccessByCodes([existingEntry.value?'ai-video:library:update':'ai-video:library:create'])&&hasAccessByCodes(['ai-video:model:test']));
const canStart = computed(()=>hasAccessByCodes(['ai-video:task:start'])&&hasAccessByCodes(['ai-video:library:query']));
const tab = ref('scan'); const entries=ref<api.EntryAccess[]>([]); const selected=ref<number>();
const current=computed(()=>entries.value.find(v=>v.id===selected.value));
const automatic=computed(()=>current.value?.triggerMode==='FACE_ZONE');
const stationState=ref('OFFLINE');
let stationTimer:ReturnType<typeof setTimeout>|undefined;
let stationGeneration=0;
const cameras=ref<AiVideoCameraApi.Camera[]>([]);
const camera=computed(()=>cameras.value.find(v=>v.id===current.value?.cameraId));
const libraries=ref<{label:string;value:number}[]>([]); const nodes=ref<{label:string;value:number}[]>([]); const versions=ref<{label:string;value:number}[]>([]);
const people=ref<api.FaceReference[]>([]); const rosterLibrary=ref<number>();
const busy=ref(false); const consent=ref(false); const error=ref(''); const opened=ref(false); const preview=ref(false);
const editing=ref<{id?:number;version:number}>({version:0});
const scan=ref<api.EntryScan>(); const file=ref<File>();
let generation=0; let timer: ReturnType<typeof setTimeout>|undefined;
const stateText=(s?:string)=>s ? t(`states.${s}`) : t('waiting');
const photoReason=(reason:string)=>({NO_FACE:'未检测到人脸，请更换清晰的单人正面照片。',MULTIPLE_FACES:'照片中有多张脸，请使用单人照片。',FACE_TOO_SMALL:'照片中的人脸太小，请使用近距离正面照片。',INSUFFICIENT_IMAGE_QUALITY:'照片清晰度或光照不足，请重新拍摄。',FACE_CLIPPED:'照片中的人脸不完整，请更换照片。',EXECUTION_FAILED:'网关执行失败，请检查节点和模型状态后重试。'}[reason]??stateText(reason));
const outcome=computed(()=>scan.value?stateText(scan.value.result.decision??scan.value.result.status??scan.value.status):automatic.value?t(`stationStates.${stationState.value}`):t('waiting'));
function field(fieldName:string,label:string,component:string,extra:Record<string,unknown>={}) {
  return {fieldName,label:t(label),component,rules:'required',...extra};
}
const [ConfigForm,configForm]=useVbenForm({showDefaultActions:false,wrapperClass:'grid-cols-1 md:grid-cols-2',schema:[
  field('name','entryName','Input'),
  field('triggerMode','triggerMode','Select',{defaultValue:'FACE_ZONE',componentProps:{options:[{label:t('automaticMode'),value:'FACE_ZONE'},{label:t('manualMode'),value:'MANUAL'}]}}),
  field('cameraId','camera','Select',{componentProps:()=>({options:cameras.value.map(v=>({label:v.name,value:v.id}))})}),
  field('nodeId','node','Select',{componentProps:()=>({options:nodes.value})}),
  field('libraryId','library','Select',{componentProps:()=>({options:libraries.value,onChange:loadPeople})}),
  field('modelVersionId','engine','Select',{componentProps:()=>({options:versions.value})}),
  field('allowedEntryIds','allowed','Select',{defaultValue:[],rules:undefined,componentProps:()=>({mode:'multiple',options:people.value.filter(v=>v.status==='READY').map(v=>({label:`${v.name} · ${v.externalCode}`,value:v.entryId}))})}),
  field('similarityThreshold','threshold','InputNumber',{defaultValue:.6,componentProps:{min:.1,max:1,step:.01}}),
  field('ambiguityMargin','margin','InputNumber',{defaultValue:.08,componentProps:{min:.01,max:.5,step:.01}}),
  field('temporalN','votes','InputNumber',{defaultValue:3,componentProps:{min:2,max:10}}),
  field('temporalM','window','InputNumber',{defaultValue:5,componentProps:{min:2,max:15}}),
  ...['X','Y','Width','Height'].map((v)=>field(`roi${v}`,`roi${v}`,'InputNumber',{defaultValue:['X','Y'].includes(v)?0:100,componentProps:{min:['X','Y'].includes(v)?0:1,max:100,step:5}})),

]});
const [EnrollForm,enrollForm]=useVbenForm({showDefaultActions:false,wrapperClass:'grid-cols-1 md:grid-cols-2',schema:[
  field('libraryId','library','Select',{componentProps:()=>({options:libraries.value,disabled:!!existingEntry.value||busy.value})}),
  field('nodeId','node','Select',{componentProps:()=>({options:nodes.value})}),
  field('modelVersionId','engine','Select',{componentProps:()=>({options:versions.value})}),
  field('name','personName','Input',{dependencies:{triggerFields:['libraryId'],show:()=>!existingEntry.value},componentProps:()=>({disabled:!!existingEntry.value||busy.value})}),field('externalCode','code','Input',{dependencies:{triggerFields:['libraryId'],show:()=>!existingEntry.value},componentProps:()=>({disabled:!!existingEntry.value||busy.value})}),
  field('validUntil','validUntil','DatePicker',{componentProps:{showTime:true,valueFormat:'YYYY-MM-DDTHH:mm:ss'}}),
  field('consentConfirmed','enrollConsent','Checkbox',{defaultValue:false,rules:undefined,componentProps:{content:t('enrollConsentText')}}),
]});
const [PeopleGrid,peopleGrid]=useVbenVxeGrid<api.FaceReference>({gridOptions:{border:true,height:260,pagerConfig:{enabled:false},columns:[
  {field:'name',title:t('personName')},{field:'externalCode',title:t('code')},
  {field:'status',title:t('status'),formatter:({cellValue}:{cellValue:string})=>stateText(cellValue)},
  {field:'validUntil',title:t('validUntil'),minWidth:170,formatter:'formatDateTime'},{title:t('actions'),slots:{default:'actions'},width:110},
],data:[]}});
const [HistoryGrid,historyGrid]=useVbenVxeGrid<api.EntryScan>({gridOptions:{border:true,height:390,pagerConfig:{enabled:false},columns:[
  {field:'id',title:t('session'),width:80},{field:'createTime',title:t('time'),minWidth:165,formatter:'formatDateTime'},
  {field:'result.personName',title:t('personName')},{field:'status',title:t('status'),formatter:({cellValue}:{cellValue:string})=>stateText(cellValue)},
  {title:t('outcome'),minWidth:160,formatter:({row}:{row:api.EntryScan})=>stateText(row.result.decision??row.result.status)},
  {field:'result.device',title:t('device')},{field:'eventId',title:t('event'),slots:{default:'event'},width:90},
],data:[]}});
async function refresh() {
  if(!hasAccessByCodes(['ai-video:task:query']))return;
  entries.value=await api.listEntryAccess(); if(selected.value&&!entries.value.some(v=>v.id===selected.value))selected.value=undefined;
  if(!selected.value)selected.value=entries.value[0]?.id;
  await historyGrid.setGridOptions({data:await api.entryScanHistory()});
}
async function pollStation(version:number){
  if(version!==stationGeneration||!opened.value||!current.value||!automatic.value||tab.value!=='scan')return;
  try{
    const status=await api.getEntryStationStatus(current.value.id);
    if(version!==stationGeneration)return;
    stationState.value=status.state;
    scan.value=['SCANNING','TRIGGERED','WAIT_CLEAR'].includes(status.state)&&status.latestScan&&Date.now()-new Date(status.latestScan.createTime).getTime()<120000?status.latestScan:undefined;
  }catch{stationState.value='OFFLINE';scan.value=undefined;}
  if(version===stationGeneration)stationTimer=setTimeout(()=>pollStation(version),1000);
}
watch([opened,selected,automatic,tab],()=>{
  stationGeneration++;if(stationTimer)clearTimeout(stationTimer);
  if(automatic.value&&tab.value==='scan'){scan.value=undefined;void pollStation(stationGeneration);}
});
async function loadPeople(id?:number) {
  rosterLibrary.value=id;people.value=id?await api.listFaceReferences(id):[];
  await peopleGrid.setGridOptions({data:people.value});
}
async function poll(id:number,version:number,deadline:number) {
  if(version!==generation)return;
  try {
    scan.value=await (existingEntry.value ? api.getExtractionStatus(id) : api.getEntryScan(id));
    if(!['QUEUED','RUNNING','SENT'].includes(scan.value.status)) {
      busy.value=false;if(scan.value.mode==='ENROLL')emit('referencesChanged');await refresh();if(rosterLibrary.value)await loadPeople(rosterLibrary.value);return;
    }
    if(Date.now()>deadline){busy.value=false;error.value=t('timeout');emit('referencesChanged');return;}
    timer=setTimeout(()=>poll(id,version,deadline),1000);
  }catch{busy.value=false;error.value=t('queryFailed');}
}
async function runScan() {
  if(!current.value?.enabled||!consent.value||busy.value)return;
  busy.value=true;error.value='';const v=++generation;
  try { const id=await api.startEntryScan(current.value.id);scan.value={id,mode:'IDENTIFY',status:'QUEUED',result:{},createTime:''};consent.value=false;await poll(id,v,Date.now()+130000); }
  catch{busy.value=false;error.value=t('startFailed');}
}
async function cancelScan(){if(scan.value&&busy.value)await api.cancelEntryScan(scan.value.id);busy.value=false;generation++;if(timer)clearTimeout(timer);await refresh();}
async function submitEnrollment(){
  if(!(await enrollForm.validate()).valid||(!file.value&&!existingEntry.value)||busy.value)return;
  const values=await enrollForm.getValues();if(values.consentConfirmed!==true){message.warning(t('consentRequired'));return;}
  busy.value=true;error.value='';const v=++generation;
  try{const id=existingEntry.value ? await api.extractEntryFace({...values,entryId:existingEntry.value.id}) : await api.enrollEntryFace({...values,file:file.value!});emit('referencesChanged');scan.value={id,mode:'ENROLL',status:'QUEUED',result:{},createTime:''};
    await enrollForm.setValues({consentConfirmed:false});await loadPeople(Number(values.libraryId));await poll(id,v,Date.now()+130000);}
  catch(e){busy.value=false;const detail=e as {response?:{data?:{msg?:string}}};error.value=detail?.response?.data?.msg || (e instanceof Error&&e.message ? e.message : t('enrollFailed'));}
}
function chooseFile(value:File){if(!['image/jpeg','image/png'].includes(value.type)||value.size>5*1024*1024){message.warning(t('fileLimit'));return false;}file.value=value;return false;}
async function editEntry(){if(!current.value)return;const e=current.value;editing.value={id:e.id,version:e.version};tab.value='config';await nextTick();await loadPeople(e.libraryId);
  await configForm.setValues({...e,roiX:e.roi.x*100,roiY:e.roi.y*100,roiWidth:e.roi.width*100,roiHeight:e.roi.height*100});tab.value='config';}
async function newEntry(){editing.value={version:0};tab.value='config';await nextTick();await configForm.resetForm();await configForm.setValues({id:undefined,version:0});tab.value='config';}
async function saveConfig(){if(!(await configForm.validate()).valid)return;error.value='';
  try{const values=await configForm.getValues();selected.value=await api.saveEntryAccess({...values,enabled:entries.value.find(e=>e.id===editing.value.id)?.enabled ?? false,roiX:Number(values.roiX)/100,roiY:Number(values.roiY)/100,roiWidth:Number(values.roiWidth)/100,roiHeight:Number(values.roiHeight)/100,id:editing.value.id,version:editing.value.version,allowedEntryIds:values.allowedEntryIds??[]});await refresh();tab.value='scan';}
  catch{error.value=t('saveFailed');}}
async function removeEntry(){if(!current.value)return;await confirm(t('deleteConfirm'));await api.deleteEntryAccess(current.value.id);await refresh();}
async function revoke(row:api.FaceReference){await confirm(t('revokeConfirm'));await api.revokeFaceReference(row.id);await loadPeople(rosterLibrary.value);}
const [Modal,modalApi]=useVbenModal({showConfirmButton:false,title:t('title'),onOpenChange:async(value)=>{
  opened.value=value;const context=modalApi.getData<{enrollmentOnly?:boolean;entry?:{externalCode:string;id:number;mediaRef?:string;name:string;};libraryId?:number;modelVersionId?:number;nodeId?:number;}> ();existingEntry.value=context?.entry;enrollmentOnly.value=context?.enrollmentOnly===true;if(value&&enrollmentOnly.value)tab.value='enroll';if(!value){preview.value=false;if(scan.value?.mode==='ENROLL'){generation++;if(timer)clearTimeout(timer);emit('referencesChanged');}else await cancelScan();return;}error.value='';consent.value=false;
  try {const [cs,ns,ls,ms]=await Promise.all([getCameraPage({pageNo:1,pageSize:100}),getNodeSimpleList(),getRecognitionLibraryPage({pageNo:1,pageSize:100,libraryType:'FACE'}),getModelPage({pageNo:1,pageSize:100})]);
    cameras.value=cs.list;nodes.value=ns.map(v=>({label:`${v.name}${v.onlineStatus===1?'':' · 离线'}`,value:v.id}));libraries.value=ls.list.filter(v=>v.status===0).map(v=>({label:v.name,value:v.id}));
    const models=ms.list.filter(v=>v.code==='active-entry-face-yunet-sface');
    const vs=(await Promise.all(models.map(v=>getModelVersionList(Number(v.id))))).flat();
    versions.value=vs.filter(v=>{try{return ['FACE_PAIR_SFACE','FACE_PAIR_SFACE_RKNN'].includes(JSON.parse(v.runtimeManifest??'{}').decoder?.type)&&v.executionStatus==='READY'&&v.publishStatus==='PUBLISHED';}catch{return false;}})
      .map(v=>({label:`${v.version} · ${JSON.parse(v.runtimeManifest??'{}').decoder?.type?.endsWith('RKNN')?'NPU':'CPU'}`,value:v.id}));
    await refresh();
    const defaults=enrollmentOnly.value ? {...current.value,...context} : current.value;
    if(defaults){
      await enrollForm.setValues({libraryId:defaults.libraryId,nodeId:defaults.nodeId??nodes.value[0]?.value,modelVersionId:defaults.modelVersionId??versions.value.find(v=>v.label.includes('NPU'))?.value,name:existingEntry.value?.name,externalCode:existingEntry.value?.externalCode});
      await loadPeople(defaults.libraryId);
    }
  }catch{error.value=t('loadFailed');}
}});
onBeforeUnmount(()=>{generation++;stationGeneration++;if(stationTimer)clearTimeout(stationTimer);if(timer)clearTimeout(timer);if(scan.value&&busy.value&&scan.value.mode!=='ENROLL')void api.cancelEntryScan(scan.value.id);});
</script>
<template>
  <Modal class="w-[1160px]" :title="existingEntry ? '提取人脸特征' : t(enrollmentOnly ? 'enrollTab' : 'title')">
    <Alert :message="existingEntry ? '使用该人员已保存的照片，在边缘网关提取特征。通过后可在摄像头配置中选择该人员，无需重复录入。' : t(enrollmentOnly ? 'enrollIntro' : 'intro')" type="info" show-icon class="mb-3" />
    <Alert v-if="error" :message="error" type="error" show-icon class="mb-3" />
    <Tabs v-model:active-key="tab">
      <TabPane v-if="!enrollmentOnly" key="scan" :tab="t('scanTab')">
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <Select v-model:value="selected" class="w-72" :placeholder="t('selectEntry')" :options="entries.map(v=>({label:`${v.name} · ${v.enabled ? t('enabled') : t('disabled')}`,value:v.id}))" :disabled="busy" />
          <Button @click="refresh">{{ t('refresh') }}</Button><Button v-if="canEdit" @click="newEntry">{{ t('newEntry') }}</Button>
          <Button v-if="current && canEdit" @click="editEntry">{{ t('configure') }}</Button>
          <span class="text-xs text-muted-foreground">算法启停请前往所属边缘网关管理。</span>
          <Button v-if="current && !current.enabled && hasAccessByCodes(['ai-video:task:delete'])" danger @click="removeEntry">{{ t('delete') }}</Button>
        </div>
        <Alert v-if="!current" :message="t('emptyEntries')" type="info" show-icon />
        <Alert v-if="automatic" :message="t('automaticHint')" :description="t(`stationStates.${stationState}`)" type="info" show-icon class="mb-3" />
        <div v-if="current" class="grid grid-cols-1 gap-4 md:grid-cols-2">
          <div>
<Checkbox v-model:checked="preview">{{ t('preview') }}</Checkbox>
            <div v-if="preview && opened && tab === 'scan'" class="mt-2 h-80"><CameraPreviewPlayer :camera="camera" :node-id="current.nodeId" :overlay-enabled="false" compact /></div>
            <p class="mt-3 text-sm text-gray-500">{{ automatic ? t('automaticPreviewHint') : t('previewHint') }}</p>
          </div>
          <div class="rounded border p-4">
            <div class="mb-3 text-xl font-semibold">{{ outcome }}</div>
            <p v-if="scan?.result.personName">{{ scan.result.personName }} · {{ scan.result.externalCode }}</p>
            <p v-if="scan?.result.reason">{{ stateText(scan.result.reason) }}</p>
            <p v-if="scan?.result.device" class="my-2"><Tag>{{ scan.result.device }}</Tag>{{ scan.result.matchedFrames ?? 0 }} / {{ scan.result.sampledFrames ?? 0 }} {{ t('frames') }}</p>
            <p v-if="scan?.result.similarity !== undefined">{{ t('similarity') }} {{ Math.round(scan.result.similarity * 100) }}%</p>
            <a v-if="scan?.eventId" :href="`/ai-video/event?eventId=${scan.eventId}`" target="_blank">{{ t('viewEvent') }} #{{ scan.eventId }}</a>
            <div v-if="!automatic" class="my-4"><Checkbox v-model:checked="consent" :disabled="busy">{{ t('scanConsent') }}</Checkbox></div>
            <Button v-if="canStart && !automatic" type="primary" :disabled="!consent || !current.enabled || busy" @click="runScan">{{ t('start') }}</Button>
            <Button v-if="busy" class="ml-2" @click="cancelScan">{{ t('cancel') }}</Button>
            <p class="mt-3 text-sm text-gray-500">{{ automatic ? t('automaticScanHint') : t('scanHint') }}</p>
          </div>
        </div>
      </TabPane>
      <TabPane key="enroll" :force-render="true" :tab="t('enrollTab')">
        <div v-if="existingEntry" class="mb-4 flex items-center gap-3 rounded border p-3">
          <img v-if="existingEntry.mediaRef" :src="existingEntry.mediaRef" alt="已保存的人员照片" class="h-20 w-20 rounded object-cover" />
          <div><strong>{{ existingEntry.name }}</strong><p>{{ existingEntry.externalCode }}</p><p class="text-sm text-gray-500">照片如需更换，请返回人员卡片点击“编辑”。</p></div>
        </div>
        <EnrollForm v-if="canEnroll" />
        <p v-if="canEnroll" class="my-2 text-sm text-gray-600">{{ t('enrollConsentText') }}</p>
        <div v-if="canEnroll" class="my-3 flex gap-3"><Upload v-if="!existingEntry" :before-upload="chooseFile" :show-upload-list="false" accept="image/jpeg,image/png"><Button>{{ file?.name ?? t('choosePhoto') }}</Button></Upload><Button type="primary" :loading="busy" :disabled="(!file && !existingEntry) || busy" @click="submitEnrollment">{{ existingEntry ? '开始提取' : t('enroll') }}</Button></div>
        <Alert v-if="scan?.mode === 'ENROLL'" :message="outcome" :description="scan.result.reason ? photoReason(scan.result.reason) : busy ? '网关正在校验照片，关闭窗口后仍会继续处理。' : scan.result.status === 'REFERENCE_READY' ? '特征已就绪，可返回摄像头选择该人员；通行权限需在摄像头配置中保存。' : '请查看结果，必要时更换清晰的单人正面照片后重试。'" :type="busy ? 'info' : scan.result.status === 'REFERENCE_READY' ? 'success' : 'warning'" show-icon class="mb-3" />
        <Tag v-if="scan?.mode === 'ENROLL' && scan.result.device">{{ scan.result.device === 'RKNPU' ? 'NPU 已执行' : scan.result.device }}</Tag>
        <div v-if="!existingEntry" class="mb-3 flex gap-2"><Select :value="rosterLibrary" :options="libraries" class="w-72" :placeholder="t('library')" @change="value=>loadPeople(Number(value))" /><Button @click="loadPeople(rosterLibrary)">{{ t('refresh') }}</Button></div>
        <PeopleGrid v-if="!existingEntry"><template #actions="{row}"><Button v-if="hasAccessByCodes(['ai-video:library:update']) && row.status !== 'REVOKED'" type="link" danger @click="revoke(row)">{{ t('revoke') }}</Button></template></PeopleGrid>
      </TabPane>
      <TabPane v-if="canEdit && !enrollmentOnly" key="config" :force-render="true" :tab="t('configTab')"><Alert :message="t('configHint')" type="info" show-icon class="mb-3" /><ConfigForm /><Button type="primary" @click="saveConfig">{{ t('save') }}</Button></TabPane>
      <TabPane v-if="!enrollmentOnly" key="history" :force-render="true" :tab="t('historyTab')"><HistoryGrid><template #event="{row}"><a v-if="row.eventId" :href="`/ai-video/event?eventId=${row.eventId}`" target="_blank">#{{ row.eventId }}</a><span v-else>—</span></template></HistoryGrid></TabPane>
    </Tabs>
  </Modal>
</template>
