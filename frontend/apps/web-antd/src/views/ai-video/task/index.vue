<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoModelApi } from '#/api/ai-video/model';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Select,
  Space,
  Statistic,
  Steps,
  Switch,
  Table,
  Tag,
} from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getPipelineVersions, getRunnableAlgorithms } from '#/api/ai-video/algorithm';
import { getCamera, getCameraPage } from '#/api/ai-video/camera';
import { getModelVersionList } from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { getPublishedRules, getRuleVersions } from '#/api/ai-video/rule';
import {
  batchCreateTasks,
  createTask,
  deleteTask,
  getTaskPage,
  getTaskRuns,
} from '#/api/ai-video/task';
import { AiPageHeader, AiStatusIndicator } from '#/components/ai-video';
import { hasCustomRegions } from '#/components/ai-video/rule-regions';
import { $t } from '#/locales';
import { router } from '#/router';
import { gatewayLocation } from '#/views/ai-video/node/presentation';

import TaskRuleModal from './modules/task-rule-modal.vue';

const [RuleModal, ruleModalApi] = useVbenModal({connectedComponent:TaskRuleModal,destroyOnClose:true});

const { hasAccessByCodes } = useAccess();
const canCreate = computed(() => hasAccessByCodes(['ai-video:task:create']));
const canStart = computed(() => hasAccessByCodes(['ai-video:task:start']));
const canStop = computed(() => hasAccessByCodes(['ai-video:task:stop']));
const canDelete = computed(() => hasAccessByCodes(['ai-video:task:delete']));

const loading = ref(false);
const error = ref('');
const tasks = ref<AiVideoTaskApi.Task[]>([]);
const algorithms = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const executableAlgorithmIds = ref(new Set<number>());
const selectableAlgorithms = computed(() => algorithms.value.filter((item) =>
  item.status === 0 && executableAlgorithmIds.value.has(item.id) &&
  ['PASS', 'PENDING'].includes(item.pipelineAcceptanceStatus),
));
const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const modelConfigError = ref(false);
let modelConfigGeneration = 0;
const pipelineModelNodes = ref<Array<{ label: string; modelId: number; nodeId: string }>>([]);
const versionsByNode = ref<Record<string, AiVideoModelApi.ModelVersion[]>>({});
const rules = ref<AiVideoRuleApi.Rule[]>([]);

const wizardOpen = ref(false);
const batchCameraIds = ref<number[]>([]);
const batchResults = ref<AiVideoTaskApi.BatchResult[]>([]);
const batchRegionsConfirmed = ref(false);
const batchRuleVersion = ref<AiVideoRuleApi.RuleVersion>();
const batchRuleLoading = ref(false);
const batchHasRegions = computed(() => hasCustomRegions(batchRuleVersion.value?.ast.regions));
let batchRuleGeneration = 0;
let batchRequestId = '';
let batchPayload: AiVideoTaskApi.BatchCreate | undefined;
const [TaskWizard, taskWizardApi] = useVbenDrawer({
  showConfirmButton: false,
  showCancelButton: false,
  onOpenChange(open) { wizardOpen.value = open; },
});
watch(wizardOpen, (open) => { if (open) taskWizardApi.open(); else taskWizardApi.close(); });
const wizardStep = ref(0);
const saving = ref(false);
const validationOnly = ref(false);
const wizard = reactive<Partial<AiVideoTaskApi.TaskSave> & { modelBindings: Record<string, number> }>({
  modelBindings: {},
  parameters: {
    confidence: 0.5,
    inputHeight: 640,
    inputWidth: 640,
    nmsThreshold: 0.5,
    sampleFps: 1,
    schemaVersion: '1.0',
  },
});
const monitorOpen = ref(false);
const monitoredTask = ref<AiVideoTaskApi.Task>();
const runs = ref<AiVideoTaskApi.TaskRun[]>([]);
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let viewActive = true;

const selectedAlgorithm = computed(() =>
  algorithms.value.find((item) => item.id === wizard.algorithmId),
);
const pipelineAccepted = computed(
  () => pipelineUsable(selectedAlgorithm.value?.pipelineAcceptanceStatus),
);
function pipelineUsable(status?: string) {
  return status === 'PASS' || (validationOnly.value &&
    status === 'PENDING');
}
const parameters = computed(
  () => wizard.parameters as Record<string, boolean | number | string | undefined>,
);
const booleanParameters = computed(
  () => parameters.value as Record<string, boolean | undefined>,
);
const numberParameters = computed(
  () => parameters.value as Record<string, number | undefined>,
);
const selectParameters = computed(
  () => parameters.value as Record<string, number | string | undefined>,
);
const stringParameters = computed(
  () => parameters.value as Record<string, string | undefined>,
);
const commonParameterKeys = new Set([
  'confidence', 'inputHeight', 'inputWidth', 'nmsThreshold', 'sampleFps', 'schemaVersion',
]);
const parameterFields = computed(() => {
  const schema = selectedAlgorithm.value?.parameterSchema as undefined | {
    properties?: Record<string, {
      description?: string;
      enum?: Array<number | string>;
      maximum?: number;
      minimum?: number;
      title?: string;
      type?: string;
    }>;
  };
  return Object.entries(schema?.properties ?? {})
    .filter(([key]) => !commonParameterKeys.has(key))
    .map(([key, definition]) => ({ key, ...definition }));
});
function runnableNodeVersions(nodeId: string) {
  return (versionsByNode.value[nodeId] ?? []).filter(
    (item) => item.publishStatus === 'PUBLISHED' && item.executionStatus === 'READY',
  );
}
const selectedRule = computed(() =>
  rules.value.find((item) => item.id === wizard.ruleId),
);

const columns: VxeTableGridOptions<AiVideoTaskApi.Task>['columns'] = [
  { field: 'name', title: '任务', minWidth: 220, fixed: 'left', showOverflow: false, slots: { default: 'name' } },
  { field: 'code', title: '编码', minWidth: 190 },
  { field: 'actualStatus', title: '当前 / 期望', width: 150, showOverflow: false, slots: { default: 'status' } },
  { field: 'cameraId', title: '摄像头', minWidth: 220, formatter: ({ cellValue }) => cameraName(cellValue) },
  { field: 'algorithmId', title: '算法', minWidth: 180, formatter: ({ cellValue }) => algorithmName(cellValue) },
  { field: 'nodeId', title: '节点', minWidth: 180, formatter: ({ cellValue }) => nodeName(cellValue) },
  { field: 'configVersion', title: '配置', width: 80, formatter: ({ cellValue }) => `v${cellValue}` },
  { field: 'metricsSnapshot', title: '实时指标', width: 180, slots: { default: 'metrics' } },
  { field: 'actions', title: '操作', width: 250, fixed: 'right', slots: { default: 'actions' } },
];

const runColumns: TableColumnsType = [
  { dataIndex: 'runId', ellipsis: true, key: 'runId', title: 'Run ID' },
  {
    dataIndex: 'configVersion',
    key: 'configVersion',
    title: '配置',
    width: 70,
  },
  { dataIndex: 'status', key: 'status', title: '状态', width: 100 },
  { dataIndex: 'startTime', key: 'startTime', title: '启动时间', width: 170 },
  { dataIndex: 'finishTime', key: 'finishTime', title: '结束时间', width: 170 },
];

const statusText: Record<string, string> = {
  DRAFT: '草稿',
  FAILED: '异常',
  OFFLINE: '节点离线',
  RUNNING: '运行中',
  STARTING: '启动中',
  STOPPED: '已停止',
  STOPPING: '停止中',
};

const [Grid, gridApi] = useVbenVxeGrid<AiVideoTaskApi.Task>({
  formOptions: {
    schema: [
      { fieldName: 'name', label: '任务名称', component: 'Input', componentProps: { allowClear: true, placeholder: '搜索任务' } },
      { fieldName: 'actualStatus', label: '运行状态', component: 'Select', componentProps: { allowClear: true, placeholder: '全部状态', options: Object.entries(statusText).map(([value, label]) => ({ label, value })) } },
    ],
  },
  gridOptions: {
    align: 'left',
    columns,
    height: 'auto',
    rowConfig: { keyField: 'id', isHover: true },
    scrollY: { enabled: false },
    pagerConfig: { pageSize: 20 },
    toolbarConfig: { refresh: true, search: true },
    proxyConfig: {
      autoLoad: false,
      ajax: {
        query: async (
          { page }: { page: { currentPage: number; pageSize: number } },
          values: Pick<AiVideoTaskApi.TaskPageParams, 'actualStatus' | 'name'>,
        ) => {
          try {
            const result = await getTaskPage({
              name: values.name || undefined,
              actualStatus: values.actualStatus || undefined,
              pageNo: page.currentPage,
              pageSize: page.pageSize,
            });
            error.value = '';
            tasks.value = result.list;
            if (monitoredTask.value) {
              monitoredTask.value = result.list.find((item) => item.id === monitoredTask.value?.id);
            }
            return result;
          } catch (cause) {
            error.value = '任务列表加载失败，请重试。';
            throw cause;
          } finally {
            schedulePoll();
          }
        },
      },
    },
  },
});

async function loadInitial() {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  try {
    const [algorithmList, cameraPage, nodeList, ruleList] = await Promise.all([
      getRunnableAlgorithms(),
      getCameraPage({ pageNo: 1, pageSize: 100, status: 0 }),
      getNodeSimpleList(),
      getPublishedRules(),
    ]);
    algorithms.value = algorithmList;
    // Publication only describes a DAG. Every bound model must have an executable
    // published version before this algorithm is offered for task creation.
    const versionCache = new Map<number, Promise<AiVideoModelApi.ModelVersion[]>>();
    const ready = await Promise.all(algorithmList.map(async (algorithm) => {
      if (!algorithm.currentPipelineVersionId || algorithm.status !== 0 ||
          !['PASS', 'PENDING'].includes(algorithm.pipelineAcceptanceStatus)) return undefined;
      const pipelines = await getPipelineVersions(algorithm.id);
      const pipeline = pipelines.find((item) => item.id === algorithm.currentPipelineVersionId && item.validationStatus === 'PUBLISHED');
      const modelTypes = new Set(['CLASSIFIER', 'DETECTOR', 'OCR', 'POSE', 'RECOGNIZER', 'SEGMENTER']);
      const boundNodes = (pipeline?.dag.nodes as Array<Record<string, unknown>> | undefined)?.filter((node) => modelTypes.has(String(node.type))) ?? [];
      if (!boundNodes.length) return undefined;
      const available = await Promise.all(boundNodes.map(async (node) => {
        const modelId = Number(node.modelId ?? algorithm.defaultModelId);
        if (!Number.isSafeInteger(modelId) || modelId <= 0) return false;
        if (!versionCache.has(modelId)) versionCache.set(modelId, getModelVersionList(modelId));
        return (await versionCache.get(modelId)!).some((version) => version.publishStatus === 'PUBLISHED' && version.executionStatus === 'READY');
      }));
      return available.every(Boolean) ? algorithm.id : undefined;
    }));
    executableAlgorithmIds.value = new Set(ready.filter((id): id is number => id !== undefined));
    cameras.value = cameraPage.list;
    nodes.value = nodeList;
    rules.value = ruleList;
    await loadTasks();
    const route = router.currentRoute.value;
    if (route.query.create === '1' && canCreate.value) {
      if (!route.query.cameraIds) { openWizard(); if (Number(route.query.nodeId)) wizard.nodeId = Number(route.query.nodeId); return; }
      const ids = [...new Set(String(route.query.cameraIds ?? '').split(',').map(Number))];
      if (!ids.length || ids.length > 100 || ids.some((id) => !Number.isSafeInteger(id) || id <= 0)) {
        message.warning($t('page.aiVideo.cameraAlgorithms.invalidSelection'));
        return;
      }
      const missing = ids.filter((id) => !cameras.value.some((camera) => camera.id === id));
      cameras.value.push(...await Promise.all(missing.map(getCamera)));
      openWizard();
      batchCameraIds.value = ids;
      wizard.cameraId = ids[0];
      const selectedId = Number(route.query.algorithmId);
      if (algorithms.value.some((item) => item.id === selectedId)) wizard.algorithmId = selectedId;
    }
  } catch {
    error.value = '任务中心初始化失败，请检查控制面、模型和节点状态。';
  } finally {
    loading.value = false;
  }
}

async function loadTasks() {
  await gridApi.query();
}

function schedulePoll() {
  if (pollTimer) clearTimeout(pollTimer);
  if (!viewActive) return;
  if (
    !monitorOpen.value &&
    !tasks.value.some((item) =>
      ['RUNNING', 'STARTING', 'STOPPING'].includes(item.actualStatus),
    )
  )
    return;
  pollTimer = setTimeout(loadTasks, 3000);
}

function openWizard() {
  batchCameraIds.value = [];
  batchResults.value = [];
  batchPayload = undefined;
  batchRequestId = crypto.randomUUID();
  batchRegionsConfirmed.value = false;
  validationOnly.value = false;
  Object.assign(wizard, {
    algorithmId: undefined,
    cameraId: undefined,
    code: '',
    modelVersionId: undefined,
    modelBindings: {},
    name: '',
    nodeId: nodes.value.find((item) => item.onlineStatus === 1)?.id,
    parameters: {
      confidence: 0.5,
      inputHeight: 640,
      inputWidth: 640,
      nmsThreshold: 0.5,
      sampleFps: 1,
      schemaVersion: '1.0',
    },
    pipelineVersionId: undefined,
    ruleId: undefined,
    ruleVersionId: undefined,
  });
  wizardStep.value = 0;
  wizardOpen.value = true;
}

async function loadVersions() {
  const currentRequest = ++modelConfigGeneration;
  const algorithm = selectedAlgorithm.value;
  modelConfigError.value = false;
  versionsByNode.value = {};
  pipelineModelNodes.value = [];
  wizard.modelVersionId = undefined;
  wizard.modelBindings = {};
  if (!algorithm?.defaultModelId) return;
  try {
  const pipelines = await getPipelineVersions(algorithm.id);
  if (currentRequest !== modelConfigGeneration) return;
  const current = pipelines.find((item) => item.id === algorithm?.currentPipelineVersionId);
  const modelNodeTypes = new Set(['CLASSIFIER', 'DETECTOR', 'OCR', 'POSE', 'RECOGNIZER', 'SEGMENTER']);
  const dagNodes = Array.isArray(current?.dag?.nodes) ? current.dag.nodes as Array<Record<string, unknown>> : [];
  pipelineModelNodes.value = dagNodes
    .filter((node) => modelNodeTypes.has(String(node.type)))
    .map((node, index) => ({
      label: `${String(node.type)} · ${String(node.capabilityKey ?? node.id)}`,
      modelId: Number(node.modelId ?? algorithm?.defaultModelId),
      nodeId: String(node.id ?? `model-${index + 1}`),
    }));
  if (!pipelineModelNodes.value.length) {
    pipelineModelNodes.value = [{ label: '主模型', modelId: algorithm.defaultModelId, nodeId: 'primary' }];
  }
  const modelIds = [...new Set(pipelineModelNodes.value.map((item) => item.modelId))];
  const versionLists = await Promise.all(modelIds.map((id) => getModelVersionList(id)));
  if (currentRequest !== modelConfigGeneration) return;
  const byModelId = new Map(modelIds.map((id, index) => [id, versionLists[index] ?? []]));
  for (const node of pipelineModelNodes.value) {
    versionsByNode.value[node.nodeId] = byModelId.get(node.modelId) ?? [];
    const first = runnableNodeVersions(node.nodeId)[0];
    if (first) wizard.modelBindings[node.nodeId] = first.id;
  }
  wizard.pipelineVersionId = algorithm.currentPipelineVersionId;
  wizard.parameters = JSON.parse(JSON.stringify(algorithm.defaultParameters));
  wizard.modelVersionId = Object.values(wizard.modelBindings)[0];
  } catch { if (currentRequest === modelConfigGeneration) modelConfigError.value = true; }
}

async function submitWizard(startImmediately: boolean) {
  if (
    (!batchCameraIds.value.length && (!wizard.name || !wizard.code)) ||
    !wizard.cameraId ||
    !wizard.algorithmId ||
    !wizard.modelVersionId ||
    pipelineModelNodes.value.some((node) => !wizard.modelBindings[node.nodeId]) ||
    !wizard.nodeId ||
    !pipelineAccepted.value ||
    (selectedAlgorithm.value?.eventType && !wizard.ruleVersionId) ||
    !wizard.parameters ||
    (batchCameraIds.value.length > 0 && (batchRuleLoading.value || (wizard.ruleId && !batchRuleVersion.value) || (batchHasRegions.value && !batchRegionsConfirmed.value)))
  ) {
    message.warning('任务配置未完成，请检查七个步骤');
    return;
  }
  saving.value = true;
  try {
    wizard.parameters.validationOnly = validationOnly.value;
    if (batchCameraIds.value.length) {
      batchPayload ??= JSON.parse(JSON.stringify({ ...wizard, cameraIds: batchCameraIds.value, requestId: batchRequestId, confirmSharedRegions: batchRegionsConfirmed.value })) as AiVideoTaskApi.BatchCreate;
      batchResults.value = await batchCreateTasks(batchPayload);
      await loadTasks();
      return;
    }
    await createTask(wizard as AiVideoTaskApi.TaskSave);

    message.success(
      '任务配置已保存，请在所属网关启动识别',
    );
    wizardOpen.value = false;
    if (startImmediately && wizard.nodeId) await router.push(gatewayLocation(wizard.nodeId));
    await loadTasks();
  } finally {
    saving.value = false;
  }
}

async function remove(task: AiVideoTaskApi.Task) {
  await deleteTask(task.id);
  message.success('任务已删除，历史事件快照不受影响');
  await loadTasks();
}

async function openMonitor(task: AiVideoTaskApi.Task) {
  monitoredTask.value = task;
  runs.value = await getTaskRuns(task.id);
  monitorOpen.value = true;
  schedulePoll();
}

function cameraName(id: number) {
  return cameras.value.find((item) => item.id === id)?.name ?? `#${id}`;
}

function algorithmName(id: number) {
  return algorithms.value.find((item) => item.id === id)?.name ?? `#${id}`;
}

function nodeName(id: number) {
  return nodes.value.find((item) => item.id === id)?.name ?? `#${id}`;
}

watch(() => wizard.algorithmId, loadVersions);
watch(
  () => wizard.ruleId,
  async (id) => {
    wizard.ruleVersionId = rules.value.find(
      (item) => item.id === id,
    )?.currentVersionId;
    batchRuleVersion.value = undefined;
    batchRegionsConfirmed.value = false;
    const current = ++batchRuleGeneration;
    if (!batchCameraIds.value.length || !id) { batchRuleLoading.value = false; return; }
    batchRuleLoading.value = true;
    try {
      const versions = await getRuleVersions(id);
      if (current === batchRuleGeneration) batchRuleVersion.value = versions.find((item) => item.id === wizard.ruleVersionId);
    } catch { message.error($t('page.aiVideo.cameraAlgorithms.ruleLoadFailed')); }
    finally { if (current === batchRuleGeneration) batchRuleLoading.value = false; }
  },
);
watch(monitorOpen, (open) => {
  if (open) schedulePoll();
});
watch(() => router.currentRoute.value.fullPath, () => {
  if (viewActive && router.currentRoute.value.path === '/ai-video/task' && router.currentRoute.value.query.create === '1') void loadInitial();
});
onMounted(loadInitial);
onActivated(() => {
  viewActive = true;
  if (router.currentRoute.value.query.create === '1') void loadInitial();
  else schedulePoll();
});
onDeactivated(() => {
  viewActive = false;
  wizardOpen.value = false;
  if (pollTimer) clearTimeout(pollTimer);
});
onBeforeUnmount(() => {
  viewActive = false;
  modelConfigGeneration += 1;
  batchRuleGeneration += 1;
  if (pollTimer) clearTimeout(pollTimer);
});
</script>

<template>
  <Page auto-content-height>
    <RuleModal @success="loadTasks" />
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader title="AI 任务" description="编排摄像头、算法、模型、规则与边缘节点，持续观察实际状态和运行指标。" icon="lucide:scan-line" status="Runtime Orchestration">
        <template #extra><Button v-if="canCreate" type="primary" @click="openWizard"><IconifyIcon icon="lucide:plus" />创建任务</Button></template>
      </AiPageHeader>
      <Alert
        message="在这里创建和查看任务；启停集中在“边缘网关 → 识别算法”，点击“管理算法”可直达所属网关。"
        show-icon
        type="info"
      />
      <Alert v-if="error" :message="error" show-icon type="error">
        <template #action><Button @click="loadInitial">重试</Button></template>
      </Alert>
      <Grid class="task-grid min-h-0 flex-1" table-title="AI 任务中心">
        <template #name="{ row }">
          <div class="task-name" :title="row.name">{{ row.name }}</div>
          <Tag v-if="row.parameters?.validationOnly === true" class="mt-1" color="orange">{{ $t('ai-video-task.validationMode') }}</Tag>
          <div v-if="row.errorMessage" class="task-error mt-1 text-xs text-red-500" :title="`${row.errorMessage} · ${row.diagnosticId || ''}`">
            {{ row.errorMessage }} · {{ row.diagnosticId }}
          </div>
        </template>
        <template #status="{ row }">
          <AiStatusIndicator :label="statusText[row.actualStatus] || row.actualStatus" :status="row.actualStatus" :pulse="row.actualStatus === 'RUNNING'" />
          <div v-if="row.actualStatus !== row.desiredStatus" class="mt-1 text-xs text-amber-500">期望：{{ statusText[row.desiredStatus] || row.desiredStatus }}</div>
        </template>
        <template #metrics="{ row }">
          <span v-if="row.metricsSnapshot" class="whitespace-nowrap tabular-nums">{{ row.metricsSnapshot.analysisFps ?? 0 }} FPS · {{ row.metricsSnapshot.inferenceMillis ?? 0 }} ms</span>
          <span v-else class="text-muted-foreground">暂无指标</span>
        </template>
        <template #actions="{ row }">
          <TableAction
:actions="[
            { label: '监控', type: 'link', onClick: () => openMonitor(row) },
            { label: '更换规则', type: 'link', ifShow: hasAccessByCodes(['ai-video:task:update']) && (['DRAFT', 'STOPPED'].includes(row.actualStatus) || (row.actualStatus === 'RUNNING' && canStart && canStop)), onClick: () => ruleModalApi.setData(row).open() },
            { label: '管理算法', type: 'link', ifShow: hasAccessByCodes(['ai-video:node:query']), onClick: () => router.push(gatewayLocation(row.nodeId, 'algorithms', row.cameraId)) },
            { label: '删除', type: 'link', danger: true, ifShow: canDelete && ['DRAFT', 'STOPPED'].includes(row.actualStatus), popConfirm: { title: `确认删除任务“${row.name}”吗？`, confirm: () => remove(row) } },
          ]"
/>
        </template>
      </Grid>
    </div>

    <TaskWizard class="w-[1100px]">
      <template #title>{{ batchCameraIds.length ? $t('page.aiVideo.cameraAlgorithms.batchWizardTitle') : '任务创建向导' }}</template>
      <template v-if="batchResults.length">
        <Alert v-for="result in batchResults" :key="result.cameraId" class="mb-3" show-icon :type="result.status === 'FAILED' ? 'error' : 'success'" :message="`${cameraName(result.cameraId)} · ${result.message}`" />
        <Space>
          <Button v-if="batchResults.some((item) => item.status === 'FAILED')" :loading="saving" @click="submitWizard(false)">{{ $t('page.aiVideo.cameraAlgorithms.retrySave') }}</Button>
          <Button type="primary" @click="wizardOpen = false; router.push('/ai-video/camera')">{{ $t('page.aiVideo.cameraAlgorithms.backToCameras') }}</Button>
        </Space>
      </template>
      <template v-else>
      <Alert v-if="modelConfigError" type="error" class="mb-3" :message="$t('page.aiVideo.cameraAlgorithms.modelLoadFailed')">
        <template #action><Button @click="loadVersions">{{ $t('page.aiVideo.cameraAlgorithms.reload') }}</Button></template>
      </Alert>
      <Steps v-model:current="wizardStep" class="mb-6" size="small">
        <Steps.Step title="摄像头" />
        <Steps.Step title="算法" />
        <Steps.Step title="模型版本" />
        <Steps.Step title="节点" />
        <Steps.Step title="推理参数" />
        <Steps.Step title="规则" />
        <Steps.Step title="确认" />
      </Steps>
      <div class="grid min-h-96 grid-cols-12 gap-6">
        <Card class="col-span-8" size="small">
          <Form layout="vertical" :disabled="saving || !!batchPayload">
            <template v-if="wizardStep === 0">
              <div v-if="batchCameraIds.length" class="space-y-3">
                <p>{{ $t('page.aiVideo.cameraAlgorithms.targets', { count: batchCameraIds.length }) }}</p>
                <Tag v-for="id in batchCameraIds" :key="id">{{ cameraName(id) }}</Tag>
                <Alert type="info" :message="$t('page.aiVideo.cameraAlgorithms.batchWizardHint')" />
              </div>
              <FormItem v-else label="摄像头" required>
                <Select
                  v-model:value="wizard.cameraId"
                  :options="
                    cameras.map((item) => ({
                      label: `${item.name} · ${item.onlineStatus === 1 ? '在线' : '离线'}`,
                      value: item.id,
                      disabled: item.status !== 0,
                    }))
                  "
                />
              </FormItem>
            </template>
            <template v-else-if="wizardStep === 1">
              <FormItem :label="$t('ai-video-task.validationMode')" :help="$t('ai-video-task.validationHelp')">
                <Switch v-model:checked="validationOnly" />
              </FormItem>
              <FormItem label="可运行算法" required extra="仅列出已启用且模型可执行的算法；待验收算法需开启现场验证。节点部署与单图测试将在后续步骤检查。">
                <Select
                  v-model:value="wizard.algorithmId"
                  :options="
                    selectableAlgorithms.map((item) => ({
                      label: `${item.name}${item.pipelineAcceptanceStatus === 'PASS' ? '' : ' · 现场验证'}${!pipelineUsable(item.pipelineAcceptanceStatus) ? '（请先开启现场验证）' : ''}`,
                      value: item.id,
                      disabled: !pipelineUsable(item.pipelineAcceptanceStatus),
                    }))
                  "
                />
              </FormItem>
              <Alert
                v-if="selectedAlgorithm"
                :message="selectedAlgorithm.description"
                show-icon
                type="info"
              />
              <Alert
                v-if="validationOnly"
                class="mt-3"
                :message="$t('ai-video-task.validationHelp')"
                show-icon
                type="warning"
              />
              <Alert
                v-if="selectedAlgorithm && !pipelineAccepted"
                class="mt-3"
                :message="`该 Pipeline 尚未通过生产验收（${selectedAlgorithm.pipelineAcceptanceStatus}），不能创建或启动任务。`"
                show-icon
                type="warning"
              />
            </template>
            <template v-else-if="wizardStep === 2">
              <FormItem v-for="node in pipelineModelNodes" :key="node.nodeId" :label="node.label" required>
                <Select
                  v-model:value="wizard.modelBindings[node.nodeId]"
                  :options="
                    runnableNodeVersions(node.nodeId).map((item) => ({
                      label: `${item.version} · ${item.artifactFormat}`,
                      value: item.id,
                    }))
                  "
                  @change="wizard.modelVersionId = Object.values(wizard.modelBindings)[0]"
                />
              </FormItem>
              <Alert
                v-if="pipelineModelNodes.some((node) => !runnableNodeVersions(node.nodeId).length)"
                message="Pipeline 中至少一个模型节点没有 Ready 版本，请先完成模型发布、单图测试和节点部署。"
                show-icon
                type="warning"
              />
              <Alert v-else :message="`该 Pipeline 需要 ${pipelineModelNodes.length} 个模型节点，任务会按节点分别绑定版本。`" show-icon type="info" />
            </template>
            <template v-else-if="wizardStep === 3">
              <FormItem label="执行节点" required>
                <Select
                  v-model:value="wizard.nodeId"
                  :options="
                    nodes.map((item) => ({
                      label: `${item.name} · ${item.onlineStatus === 1 ? '在线' : '离线'}`,
                      value: item.id,
                      disabled: item.status !== 0,
                    }))
                  "
                />
              </FormItem>
            </template>
            <template v-else-if="wizardStep === 4">
              <div class="grid grid-cols-2 gap-4">
                <FormItem label="置信度">
<InputNumber
                    v-model:value="numberParameters.confidence"
                    :max="1"
                    :min="0.01"
                    :step="0.05"
                />
</FormItem>
                <FormItem label="NMS">
<InputNumber
                    v-model:value="numberParameters.nmsThreshold"
                    :max="1"
                    :min="0.01"
                    :step="0.05"
                />
</FormItem>
                <FormItem label="采样 FPS">
<InputNumber
                    v-model:value="numberParameters.sampleFps"
                    :max="10"
                    :min="0.1"
                    :step="0.5"
                />
</FormItem>
                <FormItem label="输入宽">
<InputNumber
                    v-model:value="numberParameters.inputWidth"
                    :max="2048"
                    :min="32"
                />
</FormItem>
                <FormItem label="输入高">
<InputNumber
                    v-model:value="numberParameters.inputHeight"
                    :max="2048"
                    :min="32"
                />
</FormItem>
                <FormItem v-for="field in parameterFields" :key="field.key" :label="field.title || field.key" :help="field.description">
                  <Select v-if="field.enum?.length" v-model:value="selectParameters[field.key]" :options="field.enum.map((value) => ({ label: String(value), value }))" />
                  <Switch v-else-if="field.type === 'boolean'" v-model:checked="booleanParameters[field.key]" />
                  <InputNumber v-else-if="field.type === 'number' || field.type === 'integer'" v-model:value="numberParameters[field.key]" :max="field.maximum" :min="field.minimum" :precision="field.type === 'integer' ? 0 : undefined" class="w-full" />
                  <Input v-else v-model:value="stringParameters[field.key]" />
                </FormItem>
              </div>
              <Alert
                :message="parameterFields.length ? '以下业务参数来自算法的 JSON Schema，新增能力无需修改任务页面。' : '当前算法没有额外业务参数，仅使用通用推理参数。'"
                show-icon
                type="info"
              />
            </template>
            <template v-else-if="wizardStep === 5">
              <FormItem
                label="已发布规则"
                :required="Boolean(selectedAlgorithm?.eventType)"
              >
                <Select
                  v-model:value="wizard.ruleId"
                  allow-clear
                  :options="
                    rules
                      .filter(
                        (item) =>
                          !selectedAlgorithm?.eventType ||
                          item.eventType === selectedAlgorithm.eventType,
                      )
                      .map((item) => ({
                        label: `${item.name} · ${item.eventType}`,
                        value: item.id,
                      }))
                  "
                  placeholder="选择已发布规则版本"
                />
              </FormItem>
              <Alert
                v-if="selectedRule"
                :message="`${selectedRule.description || selectedRule.name} · 版本 #${selectedRule.currentVersionId}`"
                show-icon
                type="success"
              />
              <Alert
                v-else-if="selectedAlgorithm?.eventType"
                message="该算法会生成事件，启动前必须绑定一个事件类型一致的已发布规则。"
                show-icon
                type="warning"
              />
            </template>
            <template v-else>
              <FormItem v-if="!batchCameraIds.length" label="任务名称" required>
<Input v-model:value="wizard.name" :maxlength="100" />
</FormItem>
              <FormItem v-if="!batchCameraIds.length" label="稳定编码" required>
<Input
                  v-model:value="wizard.code"
                  :maxlength="64"
                  placeholder="person-line-01"
              />
</FormItem>
              <FormItem v-if="batchCameraIds.length && batchHasRegions" :label="$t('page.aiVideo.cameraAlgorithms.confirmRegions')">
                <Switch v-model:checked="batchRegionsConfirmed" />
                <p class="mt-2 text-xs text-muted-foreground">{{ $t('page.aiVideo.cameraAlgorithms.regionsHint') }}</p>
              </FormItem>
              <Alert
                message="保存草稿不会启动；立即启动将创建独立 Run ID 并下发带 configVersion 的节点命令。"
                show-icon
                type="warning"
              />
            </template>
          </Form>
        </Card>
        <Card class="col-span-4" size="small" title="配置摘要">
          <Descriptions :column="1" size="small">
            <DescriptionsItem :label="$t('ai-video-task.mode')">{{ $t(validationOnly ? 'ai-video-task.validationMode' : 'ai-video-task.productionMode') }}</DescriptionsItem>
            <DescriptionsItem label="摄像头">
{{
              batchCameraIds.length ? $t('page.aiVideo.cameraAlgorithms.targets', { count: batchCameraIds.length }) : wizard.cameraId ? cameraName(wizard.cameraId) : '未选择'
            }}
</DescriptionsItem>
            <DescriptionsItem label="算法">
{{
              wizard.algorithmId ? algorithmName(wizard.algorithmId) : '未选择'
            }}
</DescriptionsItem>
            <DescriptionsItem label="Pipeline">
{{
              wizard.pipelineVersionId
                ? `#${wizard.pipelineVersionId}`
                : '未发布'
            }}
</DescriptionsItem>
            <DescriptionsItem label="模型版本">
{{
              wizard.modelVersionId ? `#${wizard.modelVersionId}` : '未 Ready'
            }}
</DescriptionsItem>
            <DescriptionsItem label="节点">
{{
              wizard.nodeId ? nodeName(wizard.nodeId) : '未选择'
            }}
</DescriptionsItem>
            <DescriptionsItem label="采样">
{{ parameters.sampleFps ?? 1 }} FPS
</DescriptionsItem>
            <DescriptionsItem label="规则">
{{
              selectedRule
                ? `${selectedRule.name} · #${wizard.ruleVersionId}`
                : '未绑定'
            }}
</DescriptionsItem>
          </Descriptions>
        </Card>
      </div>
      <div class="mt-4 flex justify-between">
        <Button :disabled="wizardStep === 0" @click="wizardStep--">
上一步
</Button>
        <Space>
          <Button
            v-if="wizardStep < 6"
            :disabled="wizardStep === 1 && !pipelineAccepted"
            type="primary"
            @click="wizardStep++"
            >
下一步
</Button>
          <template v-else>
            <Button :loading="saving" @click="submitWizard(false)">
保存草稿
</Button>
            <Button v-if="!batchCameraIds.length && canStart" :loading="saving" type="primary" @click="submitWizard(true)">
保存并前往网关
</Button>
          </template>
        </Space>
      </div>
      </template>
    </TaskWizard>

    <Drawer v-model:open="monitorOpen" placement="right" width="72%">
      <template #title>{{ monitoredTask?.name }} · 运行监控</template>
      <template v-if="monitoredTask">
        <Alert v-if="monitoredTask.gatewayRevision" class="mb-4" type="info" show-icon :message="$t('ai-video-gateway.executionRevision', { revision: monitoredTask.gatewayRevision })">
          <template #action><Button type="link" @click="monitorOpen = false; router.push(gatewayLocation(monitoredTask.nodeId, 'algorithms', monitoredTask.cameraId))">{{ $t('ai-video-gateway.openWorkbench') }}</Button></template>
        </Alert>
        <Alert v-if="monitoredTask.parameters.validationOnly === true" :message="$t('ai-video-task.validationHelp')" show-icon type="warning" class="mb-4" />
        <Alert
          v-if="monitoredTask.actualStatus === 'FAILED'"
          :message="`发生了什么：${monitoredTask.errorMessage || monitoredTask.errorCode || '节点执行失败'}`"
          :description="`影响：当前任务未运行。建议：检查模型部署、摄像头连通性和节点资源。诊断 ID：${monitoredTask.diagnosticId || '无'}`"
          show-icon
          type="error"
        />
        <div class="my-4 grid grid-cols-5 gap-4">
          <Card size="small">
<Statistic
              title="输入 FPS"
              :value="monitoredTask.metricsSnapshot?.inputFps ?? 0"
          />
</Card>
          <Card size="small">
<Statistic
              title="分析 FPS"
              :value="monitoredTask.metricsSnapshot?.analysisFps ?? 0"
          />
</Card>
          <Card size="small">
<Statistic
              title="推理 ms"
              :value="monitoredTask.metricsSnapshot?.inferenceMillis ?? 0"
          />
</Card>
          <Card size="small">
<Statistic
              title="队列深度"
              :value="monitoredTask.metricsSnapshot?.queueDepth ?? 0"
          />
</Card>
          <Card size="small">
<Statistic
              title="丢帧"
              :value="monitoredTask.metricsSnapshot?.droppedFrames ?? 0"
          />
</Card>
        </div>
        <Card class="mb-4" size="small" title="当前配置快照">
          <Descriptions :column="3" size="small">
            <DescriptionsItem label="当前 / 期望">
{{ monitoredTask.actualStatus }} /
              {{ monitoredTask.desiredStatus }}
</DescriptionsItem>
            <DescriptionsItem label="Run ID">
{{
              monitoredTask.activeRunId || '未运行'
            }}
</DescriptionsItem>
            <DescriptionsItem label="配置版本">
v{{ monitoredTask.configVersion }}
</DescriptionsItem>
            <DescriptionsItem label="摄像头">
{{
              cameraName(monitoredTask.cameraId)
            }}
</DescriptionsItem>
            <DescriptionsItem label="算法">
{{
              algorithmName(monitoredTask.algorithmId)
            }}
</DescriptionsItem>
            <DescriptionsItem label="节点">
{{
              nodeName(monitoredTask.nodeId)
            }}
</DescriptionsItem>
            <DescriptionsItem label="最近心跳">
{{
              monitoredTask.lastHeartbeatTime || '尚未上报'
            }}
</DescriptionsItem>
          </Descriptions>
        </Card>
        <Card size="small" title="运行历史（最近 50 次）">
          <Table
            :columns="runColumns"
            :data-source="runs"
            :pagination="false"
            row-key="id"
            size="small"
          />
        </Card>
      </template>
    </Drawer>
  </Page>
</template>

<style scoped>
.task-name,
.task-error {
  display: -webkit-box;
  overflow: hidden;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 2;
}

.task-name {
  font-weight: 500;
  line-height: 1.5;
}
</style>
