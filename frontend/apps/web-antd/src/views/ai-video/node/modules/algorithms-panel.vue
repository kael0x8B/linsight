<script setup lang="ts">
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoNode } from '#/api/ai-video/node';
import type { GatewaySnapshot, GatewayTask } from '#/api/ai-video/node/gateway';

import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { confirm, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Empty, Input, message, Select, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getCameraPage } from '#/api/ai-video/camera';
import { platformGateway } from '#/api/ai-video/node/gateway';
import { deleteTask, getTask, startTask, stopTask } from '#/api/ai-video/task';
import { deleteEntryAccess, enableEntryAccess, stopEntryAccess } from '#/api/ai-video/task/entry-access';
import { capabilityActions } from '#/views/ai-video/camera/modules/camera-algorithm-state';
import FaceModal from '#/views/ai-video/camera/modules/camera-face-modal.vue';
import TaskRuleModal from '#/views/ai-video/task/modules/task-rule-modal.vue';

import GatewayWorkbench from '../gateway-workbench.vue';
import GatewayEntryPreview from './gateway-entry-preview.vue';

type Row = AiVideoCameraApi.CameraCapability & { cameraId: number; cameraName: string; key: string; localTask?: GatewayTask };
const props = defineProps<{ node: AiVideoNode }>();
const route = useRoute(); const router = useRouter();
const { hasAccessByCodes: can } = useAccess();
const busy = ref(''); const error = ref(''); const loading = ref(false); const localError = ref(''); const rows = ref<Row[]>([]); const search = ref('');
const cameraId = ref(Number(route.query.cameraId) || undefined); const state = ref<string>();
const preview = ref<InstanceType<typeof GatewayWorkbench>>();
const snapshot = ref<GatewaySnapshot>();
const entryPreviewKey = ref<string>();
const selectedEntry = computed(() => rows.value.find(row => row.key === entryPreviewKey.value && row.entryAccessId));
const entryPanel = ref<HTMLElement>();
const allCameras = ref<Array<{label: string; value: number}>>([]);
const [CreateForm, createForm] = useVbenForm({ showDefaultActions: false, schema: [
  { fieldName: 'kind', label: '识别算法', component: 'Select', rules: 'required', defaultValue: 'video', componentProps: { options: [{ label: '视频识别算法', value: 'video' }, { label: '入口主动刷脸', value: 'entry' }] } },
  { fieldName: 'cameraId', label: '摄像头', component: 'Select', rules: 'required', dependencies: { triggerFields: ['kind'], show: values => values.kind === 'entry' }, componentProps: () => ({ options: allCameras.value, showSearch: true, optionFilterProp: 'label' }) },
] });
const [CreateModal, createApi] = useVbenModal({ title: '添加本机识别算法', async onConfirm() {
  if (!(await createForm.validate()).valid) return;
  const values = await createForm.getValues();
  createApi.close();
  if (values.kind === 'entry') faceApi.setData({ cameraId: Number(values.cameraId), nodeId: props.node.id }).open();
  else await router.push({ path: '/ai-video/task', query: { create: '1', nodeId: props.node.id } });
} });
const [FaceConfiguration, faceApi] = useVbenModal({ connectedComponent: FaceModal, destroyOnClose: true });
const [RuleModal, ruleApi] = useVbenModal({ connectedComponent: TaskRuleModal, destroyOnClose: true });
const transport = <T,>(action: string, payload?: Record<string, unknown>) => platformGateway<T>(props.node.id, action, payload);
const labels: Record<string, string> = { RUNNING: '正在识别', STARTING: '正在启动', STOPPING: '正在停止', STOPPED: '已停止', DRAFT: '待启动', FAILED: '运行异常', OFFLINE: '网关离线', STALE: '状态待确认' };
const filtered = computed(() => rows.value.filter(r => (!cameraId.value || r.cameraId === cameraId.value) && (!state.value || r.actualStatus === state.value) && `${r.algorithmName} ${r.taskName} ${r.cameraName}`.toLowerCase().includes(search.value.trim().toLowerCase())));
const cameras = computed(() => [...new Map(rows.value.map(r => [r.cameraId, { value: r.cameraId, label: r.cameraName }])).values()]);
const running = computed(() => rows.value.filter(r => r.effectiveStatus === 'RUNNING').length);
const [Grid, grid] = useVbenVxeGrid<Row>({ gridOptions: {
  columns: [
    { field: 'algorithmName', title: '识别算法 / 任务', minWidth: 240, fixed: 'left', slots: { default: 'algorithm' } },
    { field: 'cameraName', title: '摄像头', minWidth: 230 },
    { field: 'actualStatus', title: '运行状态', width: 165, slots: { default: 'status' } },
    { field: 'analysisFps', title: '分析性能', width: 140, slots: { default: 'metrics' } },
    { field: 'actions', title: '操作', width: 235, fixed: 'right', slots: { default: 'actions' } },
  ], data: [], height: 'auto', rowConfig: { keyField: 'key', height: 78 }, pagerConfig: { enabled: false }, toolbarConfig: { refresh: false },
} });
watch(filtered, value => { void grid.setGridOptions({ data: value }); });
let disposed = false; let generation = 0; let timer: ReturnType<typeof setTimeout> | undefined;
async function refresh(quiet = false) {
  clearTimeout(timer);
  const expected = ++generation;
  if (!quiet) loading.value = true;
  // Camera capabilities already compose inference tasks and entrance recognition through their owning services.
  const platform = async () => {
    const all: Row[] = []; const choices: Array<{label:string;value:number}> = [];
    for (let pageNo = 1; ; pageNo++) {
      const page = await getCameraPage({ pageNo, pageSize: 100 });
      if (disposed || expected !== generation) return all;
      choices.push(...page.list.map(camera => ({label:camera.name,value:camera.id!})));
      for (const camera of page.list) for (const c of camera.recognitionCapabilities || []) if (c.nodeId === props.node.id) {
        all.push({ ...c, key: c.entryAccessId ? `entry-${c.entryAccessId}` : `task-${c.taskId}`, cameraId: camera.id!, cameraName: camera.name });
      }
      if (pageNo * 100 >= page.total || !page.list.length) { allCameras.value = choices; return all; }
    }
  };
  const results = await Promise.allSettled([platform(), transport<GatewaySnapshot>('snapshot')]);
  if (disposed || expected !== generation) return;
  const central = results[0]; const local = results[1];
  error.value = central.status === 'rejected' ? '算法列表加载失败，请刷新重试。当前内容可能已过期。' : '';
  localError.value = local.status === 'rejected' ? '网关连接暂不可用，本地任务及实时画面无法更新。平台任务显示最近上报状态。' : '';
  if (local.status === 'fulfilled') snapshot.value = local.value;
  if (central.status === 'fulfilled') {
    const localTasks = (local.status === 'fulfilled' ? local.value.tasks : []).filter(t => t.platformManaged === false).map(t => ({
      key: `local-${t.config.taskId}`, taskId: t.config.taskId, taskName: t.name, algorithmName: '本地识别任务',
      cameraId: t.config.cameraId, cameraName: `本地摄像头 #${t.config.cameraId}`, nodeId: props.node.id,
      actualStatus: t.status.status, effectiveStatus: t.status.status, desiredStatus: t.enabled ? 'RUNNING' : 'STOPPED',
      validationOnly: false, localTask: t,
    }));
    rows.value = [...central.value, ...localTasks];
    if (!rows.value.some(row => row.key === entryPreviewKey.value)) entryPreviewKey.value = undefined;
    if (!entryPreviewKey.value && !snapshot.value?.tasks.length) entryPreviewKey.value = rows.value.find(row => row.entryAccessId && (!cameraId.value || row.cameraId === cameraId.value))?.key;
  }
  loading.value = false;
  timer = setTimeout(() => void refresh(true), 5000);
}
function lifecycle(row: Row) {
  if (row.localTask) return { start: !row.localTask.enabled, stop: row.localTask.enabled, remove: false, stopping: false };
  return capabilityActions(row);
}
async function act(row: Row, action: 'remove' | 'start' | 'stop') {
  if (busy.value || !lifecycle(row)[action]) return;
  if (action !== 'start') {
    try { await confirm(action === 'stop' ? `停止“${row.taskName}”？仅停止“${props.node.name}”上该摄像头的识别，保留配置和历史记录。` : `移除“${row.taskName}”的配置？历史事件将保留。`); } catch { return; }
  }
  busy.value = row.key;
  try {
    if (row.localTask) {
      await transport('task.save', { taskId: row.taskId, expectedRevision: row.localTask.revision, requestId: crypto.randomUUID(), enabled: action === 'start' });
    } else if (row.entryAccessId) {
      await ({ start: enableEntryAccess, stop: stopEntryAccess, remove: deleteEntryAccess })[action](row.entryAccessId, props.node.id);
    } else if (row.taskId) await ({ start: startTask, stop: stopTask, remove: deleteTask })[action](row.taskId);
    message.success(action === 'remove' ? '配置已移除' : '操作已提交，等待网关确认执行状态');
    await refresh(true);
  } catch (e) { message.error(e instanceof Error ? e.message : '操作失败，请刷新后重试'); }
  finally { busy.value = ''; }
}
async function configure(row: Row) {
  if (row.entryAccessId) { faceApi.setData({ cameraId: row.cameraId, nodeId: props.node.id, entryAccessId: row.entryAccessId }).open(); return; }
  const local = row.localTask || snapshot.value?.tasks.find(t => t.platformManaged !== false && t.config.taskId === row.taskId);
  if (local) { entryPreviewKey.value = undefined; await nextTick(); await preview.value?.edit(local); }
  else if (row.taskId) ruleApi.setData(await getTask(row.taskId)).open();
}
async function showPreview(row: Row) {
  if (row.entryAccessId) { entryPreviewKey.value = row.key; await nextTick(); entryPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); return; }
  entryPreviewKey.value = undefined;
  await nextTick();
  const task = row.localTask || snapshot.value?.tasks.find(t => t.config.taskId === row.taskId && t.platformManaged !== false);
  if (task) preview.value?.selectTask(task);
  else message.info(row.entryAccessId ? '入口识别画面可在配置中预览，识别记录在本地事件中查看。' : '任务尚未下发到网关，启动后可查看实时画面。');
}
onMounted(() => void refresh());
onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer); });
</script>
<template>
  <CreateModal><p class="mb-4 text-sm text-muted-foreground">所属网关：{{ node.name }}。配置只在这台网关上运行。</p><CreateForm /></CreateModal>
  <FaceConfiguration @success="refresh()" /><RuleModal @success="refresh()" />
  <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
    <div><h3 class="text-base font-semibold">识别算法 <span class="ml-2 text-sm font-normal text-muted-foreground">{{ rows.length }} 项 · {{ running }} 项正在识别</span></h3><p class="mt-1 text-sm text-muted-foreground">启停仅作用于当前网关。停止保留配置；移除需要先停止。</p></div>
    <div class="flex gap-2"><Button :loading="loading" @click="refresh()">刷新</Button><Button v-if="can(['ai-video:task:create'])" type="primary" :disabled="loading || !!error" @click="createApi.open()">添加识别算法</Button></div>
  </div>
  <Alert v-if="error" class="mb-3" type="error" show-icon :message="error" />
  <Alert v-if="localError" class="mb-3" type="warning" show-icon :message="localError" />
  <div class="mb-4 flex flex-wrap gap-3"><Input v-model:value="search" allow-clear class="!w-64" placeholder="搜索算法或任务" aria-label="搜索识别算法" /><Select v-model:value="cameraId" allow-clear class="min-w-64" :options="cameras" placeholder="全部摄像头" aria-label="按摄像头筛选" /><Select v-model:value="state" allow-clear class="w-40" :options="Object.entries(labels).filter(([key]) => key !== 'STALE').map(([value,label]) => ({ value,label }))" placeholder="全部状态" aria-label="按运行状态筛选" /></div>
  <div :style="{ height: `${Math.min(620, Math.max(180, filtered.length * 78 + 65))}px` }">
    <Grid>
      <template #algorithm="{ row }"><div class="text-left"><strong>{{ row.algorithmName || row.taskName }}</strong><div class="mt-1 truncate text-xs text-muted-foreground" :title="row.taskName">{{ row.taskName }}</div><Tag v-if="row.localTask" class="mt-1">本地创建</Tag><Tag v-else-if="row.validationOnly" class="mt-1" color="orange">现场验证</Tag></div></template>
      <template #status="{ row }"><Tag :color="node.onlineStatus !== 1 ? 'default' : row.effectiveStatus === 'RUNNING' ? 'green' : ['FAILED', 'STALE'].includes(row.effectiveStatus) ? 'orange' : 'default'">{{ node.onlineStatus !== 1 ? '网关离线' : labels[row.effectiveStatus] || row.effectiveStatus }}</Tag><p v-if="row.actualStatus !== row.desiredStatus" class="mt-1 text-xs text-muted-foreground">期望：{{ labels[row.desiredStatus] || row.desiredStatus }}</p><p v-if="row.errorMessage" class="mt-1 text-xs text-red-500" :title="row.errorMessage">{{ row.errorMessage }}</p></template>
      <template #metrics="{ row }"><span v-if="node.onlineStatus === 1 && row.effectiveStatus === 'RUNNING' && row.analysisFps != null">{{ row.analysisFps.toFixed(1) }} FPS</span><span v-else class="text-muted-foreground">—</span><p class="mt-1 text-xs text-muted-foreground">{{ row.executionBackend || '' }}</p></template>
      <template #actions="{ row }">
<div class="flex flex-wrap items-center gap-2">
        <Button v-if="lifecycle(row).start && can([row.localTask ? 'ai-video:node:operate' : 'ai-video:task:start'])" type="primary" size="small" :loading="busy === row.key" :disabled="!!busy || !!error || node.onlineStatus !== 1 || (row.localTask && !!localError)" @click="act(row, 'start')">启动识别</Button>
        <Button v-if="lifecycle(row).stop && can([row.localTask ? 'ai-video:node:operate' : row.entryAccessId ? 'ai-video:task:update' : 'ai-video:task:stop'])" size="small" :loading="busy === row.key" :disabled="!!busy || !!error || (row.localTask && !!localError)" @click="act(row, 'stop')">{{ lifecycle(row).stopping ? '重试停止' : '停止识别' }}</Button>
        <TableAction
:actions="[{ label: '画面', type: 'link', disabled: !!localError, onClick: () => showPreview(row) }]" :drop-down-actions="[
          { label: row.entryAccessId || row.localTask || snapshot?.tasks.some(t => t.config.taskId === row.taskId) ? '配置参数' : '配置规则', ifShow: can(['ai-video:task:update']), disabled: !!busy || !!error, onClick: () => configure(row) },
          { label: '移除配置', danger: true, ifShow: !row.localTask && can(['ai-video:task:delete']), disabled: !!busy || !!error || !lifecycle(row).remove, onClick: () => act(row, 'remove') },
        ]"
/>
      </div>
</template>
      <template #empty><Empty :description="loading ? '正在读取识别任务' : '没有符合条件的识别任务'" /></template>
    </Grid>
  </div>
  <div v-if="selectedEntry" ref="entryPanel"><GatewayEntryPreview :entry-id="selectedEntry.entryAccessId!" :camera-id="selectedEntry.cameraId" :camera-name="selectedEntry.cameraName" :node-id="node.id" :online="node.onlineStatus === 1 && node.previewTunnelConnected" /></div>
  <GatewayWorkbench v-else ref="preview" :transport="transport" section="preview" :can-edit="can(['ai-video:node:operate']) && can(['ai-video:task:update'])" />
</template>
