<script setup lang="ts">
import type { GatewayEvent, GatewayOverlay, GatewaySnapshot, GatewayTask, GatewayTransport } from '#/api/ai-video/node/gateway';

import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, Page, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Empty, Input, InputNumber, message, Select, TabPane, Tabs, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { $t } from '#/locales';

import GatewayRecognitionPreview from './modules/gateway-recognition-preview.vue';
import GatewayRuleEditor from './modules/gateway-rule-editor.vue';

const props = withDefaults(defineProps<{ canEdit?: boolean; local?: boolean; section?: 'events' | 'models' | 'preview'; transport: GatewayTransport; }>(), { canEdit: true, section: undefined });
const snapshot = ref<GatewaySnapshot>({ tasks: [], models: [], historyDays: 7 });
const error = ref('');
const loading = ref(false);
const hasSnapshot = ref(false);
const changingTask = ref<number>();
const previewPanel = ref<HTMLElement>();
let refreshGeneration = 0;
const activeTab = ref(props.section === 'preview' ? 'tasks' : props.section || 'tasks');
defineExpose({ edit, selectTask, refresh });
const selected = ref<number>();
const { hasAccessByCodes } = useAccess();
const canPreview = computed(() => props.local || hasAccessByCodes(['ai-video:camera:preview']));
const editing = ref<GatewayTask>();
const ruleText = ref('');
const bindingText = ref('');
const editError = ref('');
const editingImage = ref<string>();
const evidenceImage = ref('');
const evidenceId = ref('');
const evidenceVideo = ref(false);
const videoUrl = ref('');
const videoLoading = ref(false);
const videoProgress = ref(0);
let videoGeneration = 0;
const modelFile = ref<File>();
const modelManifest = ref('');
const modelVersion = ref(Date.now());
const password = ref('');
function taskName(task: GatewayTask) {
  const published = task.platformManaged === false ? undefined : snapshot.value.names?.tasks[task.config.taskId];
  return /^任务\s*\d+$/.test(task.name) ? published || task.name : task.name || published || $t('ai-video-gateway.taskFallback', { id: task.config.taskId });
}
function cameraName(task: GatewayTask) {
  return (task.platformManaged === false ? undefined : snapshot.value.names?.cameras[task.config.cameraId]) || $t('ai-video-gateway.cameraFallback', { id: task.config.cameraId });
}
function modelName(id: number) {
  return snapshot.value.names?.models[id]?.name || $t('ai-video-gateway.modelFallback', { id });
}
function modelVersionLabel(id: number) { return snapshot.value.names?.models[id]?.version || `#${id}`; }
function percent(value: unknown) { return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—'; }
function analysisFps(task: GatewayTask) {
  const fps = task.status.metrics.analysisFps;
  return task.status.status === 'RUNNING' && typeof fps === 'number' ? `${fps.toFixed(1)} FPS` : '—';
}
const previewTasks = computed(() => snapshot.value.tasks.map(task => ({ ...task, name: taskName(task) })));
const taskOptions = computed(() => [...new Map(snapshot.value.tasks.map(t => [t.config.cameraId,{label:cameraName(t),value:t.config.cameraId}])).values()]);
function selectPreviewCamera(value:unknown) { const tasks=snapshot.value.tasks.filter(t=>t.config.cameraId===Number(value));selected.value=(tasks.find(t=>t.enabled&&t.status.status==='RUNNING')??tasks[0])?.config.taskId; }
const selectedTask = computed(() => snapshot.value.tasks.find(t => t.config.taskId === selected.value));
const runningCount = computed(() => snapshot.value.tasks.filter(t => t.status.status === 'RUNNING').length);
const stoppedCount = computed(() => snapshot.value.tasks.filter(t => !t.enabled).length);
const tableHeight = computed(() => Math.min(420, Math.max(132, snapshot.value.tasks.length * 68 + 58)));
const previewState = computed(() => {
  if (error.value) return 'offline';
  if (!hasSnapshot.value) return 'loading';
  if (!selectedTask.value) return 'empty';
  if (snapshot.value.tasks.some(t=>t.config.cameraId===selectedTask.value?.config.cameraId && t.enabled && t.status.status==='RUNNING')) return 'live';
  if (!selectedTask.value.enabled) return 'stopped';
  if (selectedTask.value.status.status !== 'RUNNING') return 'recovering';
  return 'live';
});
const previewMessages = computed(() => ({
  offline: [$t('ai-video-gateway.previewOffline'), $t('ai-video-gateway.previewOfflineHint')],
  loading: [$t('ai-video-gateway.previewLoading'), $t('ai-video-gateway.previewLoadingHint')],
  empty: [$t('ai-video-gateway.previewEmpty'), $t('ai-video-gateway.previewEmptyHint')],
  stopped: [$t('ai-video-gateway.previewStopped'), $t('ai-video-gateway.previewStoppedHint')],
  recovering: [$t('ai-video-gateway.previewRecovering'), selectedTask.value?.status.errorMessage || $t('ai-video-gateway.previewRecoveringHint')],
  waiting: [$t('ai-video-gateway.previewWaiting'), $t('ai-video-gateway.previewWaitingHint')],
  live: ['', ''],
}));
function selectTask(task: GatewayTask) {
  selected.value = task.config.taskId;
  previewPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
const modelOptions = computed(() => snapshot.value.models.map(m => ({ label: `${modelName(m.modelVersionId)} · ${modelVersionLabel(m.modelVersionId)} · ${m.device}`, value: m.modelVersionId })));
const statusLabels: Record<string, string> = { RUNNING: $t('ai-video-gateway.m5942497005'), STOPPED: $t('ai-video-gateway.m75dddf524e'), FAILED: $t('ai-video-gateway.m0d6f3ca3f8'), OFFLINE: $t('ai-video-gateway.m211357d22f') };
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

const [TaskGrid, taskGrid] = useVbenVxeGrid<GatewayTask>({ gridOptions: {
  columns: [
    { field: 'name', title: $t('ai-video-gateway.taskAndCamera'), minWidth: 260, fixed: 'left', slots: { default: 'task' } },
    { field: 'config.modelVersionId', title: $t('ai-video-gateway.modelInUse'), minWidth: 220, slots: { default: 'model' } },
    { field: 'status.status', title: $t('ai-video-gateway.mdce7fbef3c'), width: 130, slots: { default: 'status' } },
    { field: 'config.parameters.confidence', title: $t('ai-video-gateway.recognitionParameters'), minWidth: 180, slots: { default: 'parameters' } },
    { field: 'operation', title: $t('ai-video-gateway.mf3ea6d345e'), width: 220, fixed: 'right', slots: { default: 'operation' } },
  ], data: [], height: 'auto', rowConfig: { height: 68 }, pagerConfig: { enabled: false }, toolbarConfig: { refresh: false },
} });
const [EventGrid] = useVbenVxeGrid<GatewayEvent>({ gridOptions: {
  columns: [
    { field: 'payload.occurredTime', title: $t('ai-video-gateway.m51f85a78ca'), minWidth: 190, formatter: ({ cellValue }: { cellValue: number }) => cellValue ? new Date(cellValue).toLocaleString() : '—' },
    { field: 'payload.eventType', title: $t('ai-video-gateway.m5b2d75aa54'), minWidth: 150 },
    { field: 'payload.taskId', title: $t('ai-video-gateway.m3172b317f9'), minWidth: 180, formatter: ({ cellValue }: { cellValue: number }) => { const task = snapshot.value.tasks.find(t => t.config.taskId === cellValue); return task ? taskName(task) : $t('ai-video-gateway.taskFallback', { id: cellValue }); } },
    { field: 'delivered', title: $t('ai-video-gateway.ma358e3aedd'), width: 120, formatter: ({ row }: { row: GatewayEvent }) => row.localOnly ? $t('ai-video-gateway.mb502dbc708') : row.delivered ? $t('ai-video-gateway.m76ce8e3d5e') : $t('ai-video-gateway.m3d9f3a0516') },
    { field: 'operation', title: $t('ai-video-gateway.m68d4cdfc09'), width: 120, fixed: 'right', slots: { default: 'operation' } },
  ], height: 390, proxyConfig: { ajax: { query: async ({ page }: { page: { currentPage: number; pageSize: number } }) => props.transport('events', { page: page.currentPage, size: page.pageSize }) } },
} });
const [Form, form] = useVbenForm({
  showDefaultActions: false, wrapperClass: 'grid-cols-2',
  schema: [
    { fieldName: 'name', label: $t('ai-video-gateway.m2e30469899'), component: 'Input', rules: 'required' },
    { fieldName: 'modelVersionId', label: $t('ai-video-gateway.mbdab15724e'), component: 'Select', rules: 'required', componentProps: () => ({ options: modelOptions.value }) },
    { fieldName: 'confidence', label: $t('ai-video-gateway.mb78c2dc2e2'), component: 'InputNumber', componentProps: { min: 0.01, max: 1, step: 0.05 }, rules: 'required' },
    { fieldName: 'sampleFps', label: $t('ai-video-gateway.m733e5b154f'), component: 'InputNumber', componentProps: { min: 0.1, max: 10, step: 0.1 }, rules: 'required' },
    { fieldName: 'personConfidence', label: $t('ai-video-gateway.mde483f1aa9'), component: 'InputNumber', componentProps: { min: 0.01, max: 1, step: 0.05 } },
    { fieldName: 'ppeConfidence', label: $t('ai-video-gateway.m40ff6dd496'), component: 'InputNumber', componentProps: { min: 0.01, max: 1, step: 0.05 } },
    { fieldName: 'temporalN', label: $t('ai-video-gateway.m9479ce56d4'), component: 'InputNumber', componentProps: { min: 1, max: 30 } },
    { fieldName: 'temporalM', label: $t('ai-video-gateway.m2d19d7d4a3'), component: 'InputNumber', componentProps: { min: 1, max: 60 } },
    { fieldName: 'durationSeconds', label: $t('ai-video-gateway.m04fea7916b'), component: 'InputNumber', componentProps: { min: 0, max: 300 } },
    { fieldName: 'sourceUrl', label: $t('ai-video-gateway.m94437713c2'), component: 'InputPassword', componentProps: { placeholder: $t('ai-video-gateway.ma568145dbc'), autocomplete: 'new-password' } },
  ],
});
const [EditModal, editModal] = useVbenModal({ title: $t('ai-video-gateway.m7e50dd849b'), class: 'w-[820px]', onConfirm: save });
const [EvidenceModal, evidenceModal] = useVbenModal({ title: $t('ai-video-gateway.m6e7be762da'), class: 'w-[900px]', footer: false, onClosed: () => { evidenceImage.value = ''; evidenceId.value = ''; releaseVideo(); } });
const [ModelModal, modelModal] = useVbenModal({ title: $t('ai-video-gateway.m32a9d23644'), class: 'w-[700px]', onConfirm: uploadModel });
const [PasswordModal, passwordModal] = useVbenModal({ title: $t('ai-video-gateway.me6d20b5e5b'), onConfirm: savePassword });

function newRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 15) | 64; bytes[8] = ((bytes[8] ?? 0) & 63) | 128;
  const hex = [...bytes].map(b => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

async function refresh(silent = false) {
  if (disposed) return;
  const generation = ++refreshGeneration;
  if (!silent) loading.value = true;
  try {
    const result = await props.transport<GatewaySnapshot>('snapshot');
    if (disposed || generation !== refreshGeneration) return;
    hasSnapshot.value = true;
    snapshot.value = result;
    await taskGrid.setGridOptions({ data: result.tasks });
    if (!result.tasks.some(t => t.config.taskId === selected.value)) selected.value = result.tasks.find(t => t.status.status === 'RUNNING')?.config.taskId ?? result.tasks[0]?.config.taskId;
    error.value = '';
  } catch (e) { if (!disposed && generation === refreshGeneration) error.value = e instanceof Error ? e.message : $t('ai-video-gateway.m04a090194d'); }
  finally { if (!silent) loading.value = false; }
}
async function poll() {
  await refresh(hasSnapshot.value);
  if (!disposed) timer = setTimeout(poll, 5000);
}
async function createTask() {
  const model = snapshot.value.models[0];
  if (!model) { message.warning($t('ai-video-gateway.m02d425939c')); return; }
  const id = Date.now();
  await edit({ name: $t('ai-video-gateway.ma6fac399e4'), revision: 0, appliedRevision: 0, enabled: false,
    config: { taskId: id, cameraId: id, algorithmId: id, pipelineVersionId: id, runId: newRequestId(),
      configVersion: 1, modelVersionId: model.modelVersionId, modelBindings: { primary: model.modelVersionId },
      pipeline: { schemaVersion: '1.0', nodes: [{ id: 'primary', type: 'DETECTOR', capabilityKey: 'detector.object' }], edges: [] },
      parameters: { schemaVersion: '1.0', confidence: 0.5, sampleFps: 1, temporalN: 2, temporalM: 3, durationSeconds: 1, personConfidence: 0.5, ppeConfidence: 0.5 }, rule: null },
    status: { status: 'STOPPED', metrics: {} } });
}

async function edit(row: GatewayTask) {
  editing.value = JSON.parse(JSON.stringify(row));
  editError.value = '';
  editingImage.value = undefined;
  if (row.revision > 0) {
    try { editingImage.value = (await props.transport<GatewayOverlay>('overlay', { taskId: row.config.taskId }))?.imageBase64; } catch { /* The form also works without a current frame. */ }
  }
  ruleText.value = row.config.rule ? JSON.stringify(row.config.rule, null, 2) : '';
  bindingText.value = JSON.stringify(row.config.modelBindings, null, 2);
  editModal.open();
  await nextTick();
  await form.setValues({ ...row.config.parameters, name: taskName(row), modelVersionId: row.config.modelVersionId, sourceUrl: '' });
}
async function save() {
  if (!(await form.validate()).valid || !editing.value) return;
  editModal.lock(); editError.value = '';
  try {
    const values = await form.getValues();
    const row = editing.value;
    if (row.revision === 0 && !values.sourceUrl) throw new Error($t('ai-video-gateway.m9de37d9a00'));
    const { name, sourceUrl, modelVersionId, ...parameters } = values;
    const bindings: Record<string, number> = JSON.parse(bindingText.value);
    // Preserve the Pipeline binding name when switching the primary model.
    for (const key of Object.keys(bindings)) if (bindings[key] === row.config.modelVersionId) bindings[key] = Number(modelVersionId);
    const result = await props.transport<GatewayTask>('task.save', {
      taskId: row.config.taskId, expectedRevision: row.revision, requestId: newRequestId(), name,
      configuration: { ...row.config, sourceUrl: sourceUrl || undefined, modelVersionId, modelBindings: bindings,
        parameters: { ...row.config.parameters, ...parameters },
        ruleId: ruleText.value.trim() ? row.config.ruleId || row.config.taskId : null,
        ruleVersionId: ruleText.value.trim() ? row.config.ruleVersionId || row.config.taskId : null, rule: ruleText.value.trim() ? JSON.parse(ruleText.value) : null },
    });
    if (result.appliedRevision !== result.revision) message.warning($t('ai-video-gateway.ma40f49775b'));
    else message.success($t('ai-video-gateway.md68db4afbf'));
    editModal.close(); await refresh();
  } catch (e) { editError.value = e instanceof Error ? e.message : $t('ai-video-gateway.m40525a7328'); }
  finally { editModal.unlock(); }
}
async function toggle(row: GatewayTask) {
  if (changingTask.value !== undefined) return;
  if (row.enabled) { try { await confirm($t('ai-video-gateway.mef8cd7a5a1', { p0: taskName(row) })); } catch { return; } }
  changingTask.value = row.config.taskId;
  try {
    await props.transport('task.save', { taskId: row.config.taskId, expectedRevision: row.revision, requestId: newRequestId(), enabled: !row.enabled });
    await refresh();
  } catch (e) { message.error(e instanceof Error ? e.message : $t('ai-video-gateway.m09e424b5e8')); }
  finally { changingTask.value = undefined; }
}
async function showEvidence(row: GatewayEvent) {
  releaseVideo();
  evidenceImage.value = ''; evidenceId.value = ''; evidenceVideo.value = row.hasVideo;
  try {
    if (row.hasSnapshot) {
      const result = await props.transport<{ imageBase64: string }>('event.snapshot', { sourceEventId: row.sourceEventId });
      evidenceImage.value = `data:image/jpeg;base64,${result.imageBase64}`;
    }
    evidenceId.value = row.sourceEventId; evidenceModal.open();
  } catch (e) { message.error(e instanceof Error ? e.message : $t('ai-video-gateway.m91a531b9f5')); }
}
function releaseVideo() {
  videoGeneration++;
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
  videoUrl.value = ''; videoLoading.value = false; videoProgress.value = 0;
}
async function loadVideo() {
  const generation = ++videoGeneration;
  videoLoading.value = true;
  try {
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let offset = 0;
    while (true) {
      const chunk = await props.transport<{ base64: string; length: number; size: number; }>('event.video', { sourceEventId: evidenceId.value, offset });
      if (disposed || generation !== videoGeneration) return;
      if (chunk.size > 128 * 1024 * 1024) throw new Error($t('ai-video-gateway.mce78e1adc1'));
      const data = Uint8Array.from(atob(chunk.base64), c => c.charCodeAt(0));
      chunks.push(data); offset += data.length;
      videoProgress.value = chunk.size ? Math.round(offset / chunk.size * 100) : 100;
      if (offset >= chunk.size) break;
      if (!data.length) throw new Error($t('ai-video-gateway.mb7c9204893'));
    }
    videoUrl.value = URL.createObjectURL(new Blob(chunks, { type: 'video/mp4' }));
  } catch (e) { message.error(e instanceof Error ? e.message : $t('ai-video-gateway.m3071a94119')); }
  finally { if (generation === videoGeneration) videoLoading.value = false; }
}

async function uploadModel() {
  if (!modelFile.value) { message.warning($t('ai-video-gateway.m3149101981')); return; }
  modelModal.lock();
  try {
    const file = modelFile.value;
    const metadata = JSON.parse(modelManifest.value);
    const raw = JSON.stringify({ ...metadata, modelVersionId: modelVersion.value });
    const encoded = btoa(String.fromCharCode(...new TextEncoder().encode(raw)));
    const response = await fetch('/gateway-api/models/upload', { method: 'POST', headers: { 'X-Model-Manifest': encoded, 'Content-Type': 'application/octet-stream' }, body: file });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || $t('ai-video-gateway.ma01a8d5393'));
    modelModal.close(); message.success($t('ai-video-gateway.m3a75859ea2')); await refresh();
  } catch (e) { message.error(e instanceof Error ? e.message : $t('ai-video-gateway.ma23cfbb6b6')); }
  finally { modelModal.unlock(); }
}
async function uninstallLocalModel(model: GatewaySnapshot['models'][number]) {
  try { await confirm(`卸载模型 #${model.modelVersionId}？当前网关的关联任务再次启动前需重新安装，历史事件保留。`); } catch { return; }
  try { await props.transport('model.uninstall', { modelVersionId: model.modelVersionId, sha256: model.sha256, requestId: newRequestId() }); message.success('模型已卸载'); await refresh(); }
  catch (e) { message.error(e instanceof Error ? e.message : '卸载失败'); }
}
async function savePassword() {
  passwordModal.lock();
  try {
    await props.transport('access.password', { password: password.value });
    password.value = ''; passwordModal.close(); message.success($t('ai-video-gateway.m04665692b2'));
  } catch (e) { message.error(e instanceof Error ? e.message : $t('ai-video-gateway.mc75bebd720')); }
  finally { passwordModal.unlock(); }
}
onMounted(poll);
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); releaseVideo(); });
</script>

<template>
  <Page :title="local ? $t('ai-video-gateway.m452a957e11') : undefined" :description="$t('ai-video-gateway.m6cdf0c112d')">
    <div v-if="!section" class="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-4">
      <div class="flex flex-wrap items-center gap-3">
        <Tag :color="error ? 'warning' : hasSnapshot ? 'green' : 'default'">{{ error ? $t('ai-video-gateway.mcf539eb8da') : hasSnapshot ? $t('ai-video-gateway.ma5a0e0ac92') : $t('ai-video-gateway.previewLoading') }}</Tag>
        <span class="text-sm text-muted-foreground">{{ local ? $t('ai-video-gateway.mc187353cb6') : $t('ai-video-gateway.ma52e9475a4') }}</span>
        <span v-if="hasSnapshot" class="border-l pl-3 text-sm text-muted-foreground">{{ $t('ai-video-gateway.taskSummary', { total: snapshot.tasks.length, running: runningCount, stopped: stoppedCount }) }}</span>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button :loading="loading" @click="refresh()">{{ $t('ai-video-gateway.m38108eaa1d') }}</Button>
        <Button v-if="canEdit" :disabled="!!error || !hasSnapshot" @click="passwordModal.open()">{{ $t('ai-video-gateway.mdc132af861') }}</Button>
        <Button v-if="canEdit" type="primary" :disabled="!!error || !hasSnapshot" @click="createTask">{{ $t('ai-video-gateway.m4a238f3444') }}</Button>
      </div>
    </div>
    <Alert v-if="error" class="mb-4" type="error" show-icon :message="error" />
    <Tabs v-model:active-key="activeTab" :class="{ 'gateway-section': section }">
      <TabPane v-if="!section || section === 'preview'" key="tasks" :tab="$t('ai-video-gateway.tasksTab', { count: snapshot.tasks.length })">
        <div v-if="!section" :style="{ height: `${tableHeight}px` }">
          <TaskGrid>
            <template #task="{ row }">
              <div class="min-w-0 py-2 text-left">
                <div class="truncate font-medium" :title="taskName(row)">{{ taskName(row) }}</div>
                <div class="mt-1 truncate text-xs text-muted-foreground" :title="cameraName(row)">{{ cameraName(row) }}</div>
              </div>
            </template>
            <template #model="{ row }">
              <div class="min-w-0 py-2 text-left">
                <div class="truncate" :title="modelName(row.config.modelVersionId)">{{ modelName(row.config.modelVersionId) }}</div>
                <div class="mt-1 truncate text-xs text-muted-foreground" :title="modelVersionLabel(row.config.modelVersionId)">{{ modelVersionLabel(row.config.modelVersionId) }}</div>
              </div>
            </template>
            <template #status="{ row }">
              <Tag :color="row.status.status === 'RUNNING' ? 'green' : row.enabled ? 'orange' : 'default'">{{ statusLabels[row.status.status] || row.status.status }}</Tag>
              <div class="mt-1 text-xs text-muted-foreground">{{ $t('ai-video-gateway.configVersion', { version: row.revision }) }} <span v-if="row.appliedRevision !== row.revision" class="text-amber-600">· {{ $t('ai-video-gateway.m8fddb7fe05') }}</span></div>
            </template>
            <template #parameters="{ row }">
              <div class="text-sm">{{ $t('ai-video-gateway.confidenceValue', { value: percent(row.config.parameters.confidence) }) }}</div>
              <div class="mt-1 text-xs text-muted-foreground">{{ $t('ai-video-gateway.fpsValue', { value: analysisFps(row) }) }}</div>
            </template>
            <template #operation="{ row }">
              <TableAction
:actions="[
                { label: $t('ai-video-gateway.mf4c3988e2b'), onClick: () => selectTask(row), type: 'link' },
                { label: $t('ai-video-gateway.ma7f814c0a4'), ifShow: canEdit, disabled: !!error, onClick: () => edit(row), type: 'link' },
                { label: row.enabled ? $t('ai-video-gateway.ma17f70a8d3') : $t('ai-video-gateway.mebd26da421'), ifShow: canEdit, disabled: !!error || changingTask !== undefined, loading: changingTask === row.config.taskId, onClick: () => toggle(row), type: 'link' },
              ]"
/>
            </template>
            <template #empty><Empty :description="$t('ai-video-gateway.m860304c141')" /></template>
          </TaskGrid>
        </div>
        <section ref="previewPanel" class="mt-5 overflow-hidden rounded-xl border bg-card">
          <div class="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4">
            <div>
              <h3 class="font-medium">{{ $t('ai-video-gateway.m105a680e17') }}</h3>
              <p class="mt-1 text-xs text-muted-foreground">{{ selectedTask ? cameraName(selectedTask) : $t('ai-video-gateway.previewSelectHint') }}</p>
            </div>
            <Select v-if="taskOptions.length" :value="selectedTask?.config.cameraId" :options="taskOptions" @change="selectPreviewCamera" class="w-full sm:w-72" aria-label="选择预览摄像头" />
          </div>
          <template v-if="previewState === 'live' && selectedTask">
            <Alert v-if="!canPreview" class="m-4" type="warning" message="当前账号没有视频预览权限" show-icon />
            <GatewayRecognitionPreview
v-else-if="snapshot.capabilities?.includes('preview.webrtc.v1') && activeTab === 'tasks'"
              :key="selectedTask.config.cameraId" :task="selectedTask" :tasks="previewTasks" :local="local" :title="taskName(selectedTask)" :camera-name="cameraName(selectedTask)" :transport="transport"
/>
            <Alert v-else-if="!snapshot.capabilities?.includes('preview.webrtc.v1')" class="m-4" type="info" message="此网关需在线升级后使用统一实时播放器" show-icon />
          </template>
          <div v-else class="flex min-h-[210px] flex-col items-center justify-center bg-muted/30 px-6 py-8 text-center" aria-live="polite">
            <div class="mb-3 flex h-11 w-11 items-center justify-center rounded-full border bg-card text-muted-foreground" aria-hidden="true">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><rect x="3" y="5" width="14" height="14" rx="3" /><path d="m17 10 4-3v10l-4-3" /></svg>
            </div>
            <h4 class="text-base font-medium">{{ previewMessages[previewState][0] }}</h4>
            <p class="mt-2 max-w-lg text-sm text-muted-foreground">{{ previewMessages[previewState][1] }}</p>
            <div class="mt-4 flex flex-wrap justify-center gap-2">
              <Button v-if="previewState === 'stopped' && canEdit && !section && selectedTask" type="primary" :loading="changingTask === selectedTask.config.taskId" :disabled="changingTask !== undefined" @click="toggle(selectedTask)">{{ $t('ai-video-gateway.startRecognition') }}</Button>
              <Button v-if="selectedTask && canEdit && !error && !section" @click="edit(selectedTask)">{{ $t('ai-video-gateway.editConfiguration') }}</Button>
              <Button v-if="previewState === 'empty' && canEdit" type="primary" @click="createTask">{{ $t('ai-video-gateway.m4a238f3444') }}</Button>
              <Button v-if="previewState === 'offline'" :loading="loading" @click="refresh()">{{ $t('ai-video-gateway.retryConnection') }}</Button>
            </div>
          </div>
        </section>
      </TabPane>
      <TabPane v-if="!section || section === 'models'" key="models" :tab="$t('ai-video-gateway.modelsTab', { count: snapshot.models.length })">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-muted-foreground">{{ $t(local ? 'ai-video-gateway.localModelsHint' : 'ai-video-gateway.platformModelsHint') }}</p>
          <Button v-if="local && canEdit" type="primary" @click="modelModal.open()">{{ $t('ai-video-gateway.mab7e444b8b') }}</Button>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article v-for="model in snapshot.models" :key="model.modelVersionId" class="min-w-0 rounded-xl border bg-card p-5">
            <h3 class="truncate font-medium" :title="modelName(model.modelVersionId)">{{ modelName(model.modelVersionId) }}</h3>
            <p class="mt-1 truncate text-xs text-muted-foreground" :title="modelVersionLabel(model.modelVersionId)">{{ modelVersionLabel(model.modelVersionId) }}</p>
            <div class="my-4 flex gap-2"><Tag>{{ model.artifactFormat }}</Tag><Tag color="blue">{{ model.device }}</Tag></div>
            <details class="border-t pt-3 text-xs text-muted-foreground"><summary class="cursor-pointer">{{ $t('ai-video-gateway.modelDetails') }}</summary><p class="mt-2">{{ $t('ai-video-gateway.modelVersionId') }} #{{ model.modelVersionId }}</p><p class="mt-2 break-all font-mono">SHA256 {{ model.sha256 }}</p></details>
            <Button v-if="local && canEdit && snapshot.capabilities?.includes('model.uninstall.v1')" danger size="small" class="mt-4" :disabled="!!error || snapshot.tasks.some(t => t.enabled && (t.config.modelVersionId === model.modelVersionId || Object.values(t.config.modelBindings).includes(model.modelVersionId)))" @click="uninstallLocalModel(model)">卸载模型</Button>
          </article>
        </div>
        <Empty v-if="!snapshot.models.length" :description="$t('ai-video-gateway.m93b8b014f3')" />
      </TabPane>
      <TabPane v-if="!section || section === 'events'" key="events" :tab="$t('ai-video-gateway.m2a05ddf222')">
        <p class="mb-3 text-muted-foreground">{{ $t('ai-video-gateway.m81b89296a4') }} {{ snapshot.historyDays }} {{ $t('ai-video-gateway.mb0c65d67bd') }}</p>
        <div class="h-[390px]"><EventGrid><template #operation="{ row }"><Button type="link" @click="showEvidence(row)">{{ $t('ai-video-gateway.m4160eecfa4') }}</Button></template></EventGrid></div>
      </TabPane>
    </Tabs>
    <EditModal>
      <Alert v-if="editError" class="mb-4" type="error" show-icon :message="editError" />
      <p class="mb-4 text-muted-foreground">{{ $t('ai-video-gateway.m2a15c9846c') }}</p>
      <Form />
      <GatewayRuleEditor v-model="ruleText" :image="editingImage" />
      <details class="mt-4">
<summary class="cursor-pointer">{{ $t('ai-video-gateway.mfc08955b6b') }}</summary>
        <label class="my-2 block">{{ $t('ai-video-gateway.m9750134406') }}</label><Input.TextArea v-model:value="bindingText" :rows="4" />
        <label class="my-2 block">{{ $t('ai-video-gateway.m8df9abf997') }}</label><Input.TextArea v-model:value="ruleText" :rows="12" />
      </details>
    </EditModal>
    <EvidenceModal>
      <img v-if="evidenceImage" :src="evidenceImage" :alt="$t('ai-video-gateway.mabcefed669')" class="w-full rounded" />
      <video v-if="local && evidenceVideo && evidenceId" :key="evidenceId" :src="`/gateway-api/events/${evidenceId}/video`" controls preload="metadata" class="mt-4 w-full"></video>
      <Button v-if="!local && evidenceVideo && !videoUrl" class="mt-4" :loading="videoLoading" @click="loadVideo">{{ $t('ai-video-gateway.mb91dcca025') }} {{ videoLoading ? `${videoProgress}%` : '' }}</Button>
      <video v-if="videoUrl" :src="videoUrl" controls class="mt-4 w-full"></video>
      <Empty v-if="!evidenceImage && !evidenceVideo" :description="$t('ai-video-gateway.maa0c31c283')" />
    </EvidenceModal>
    <ModelModal>
      <p class="mb-4">{{ $t('ai-video-gateway.mb8dacbb1e5') }}</p>
      <label class="mb-2 block">{{ $t('ai-video-gateway.m9119ea7fb0') }}</label><InputNumber v-model:value="modelVersion" :min="1" class="!w-full" />
      <label class="mb-2 mt-4 block">{{ $t('ai-video-gateway.md711ab45e4') }}</label><input type="file" accept=".onnx,.rknn" @change="modelFile = ($event.target as HTMLInputElement).files?.[0]" />
      <label class="mb-2 mt-4 block">{{ $t('ai-video-gateway.me69bdf6be6') }}</label><Input.TextArea v-model:value="modelManifest" :rows="12" />
    </ModelModal>
    <PasswordModal><p class="mb-3">{{ $t('ai-video-gateway.mf3438e176f') }}</p><Input.Password v-model:value="password" autocomplete="new-password" /></PasswordModal>
  </Page>
</template>

<style scoped>.gateway-section :deep(> .ant-tabs-nav) { display: none; }</style>
