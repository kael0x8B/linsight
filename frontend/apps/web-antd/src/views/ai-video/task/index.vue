<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type {
  AiVideoModelApi,
  ExecutableModelOption,
} from '#/api/ai-video/model';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import {
  computed,
  nextTick,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  reactive,
  ref,
  watch,
} from 'vue';
import { useRouter } from 'vue-router';

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

import { useVbenForm } from '#/adapter/form';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getAlgorithm,
  getPipelineVersions,
  getRunnableAlgorithms,
} from '#/api/ai-video/algorithm';
import { getCamera, getCameraPage } from '#/api/ai-video/camera';
import {
  getExecutableModelOptions,
  getNodeModelDeployments,
} from '#/api/ai-video/model';
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
import AlgorithmDiagnostic from '#/components/ai-video/algorithm-diagnostic.vue';
import { hasCustomRegions } from '#/components/ai-video/rule-regions';
import { $t } from '#/locales';
import { gatewayLocation } from '#/views/ai-video/node/presentation';

import {
  compatibleTaskRules,
  defaultTaskRule,
  taskModelLabel,
  taskModelOptions,
  taskModelRoles,
} from './configuration-options';
import TaskRuleModal from './modules/task-rule-modal.vue';
import { createQuietRefresh } from './quiet-refresh';

const router = useRouter();

const [RuleModal, ruleModalApi] = useVbenModal({
  connectedComponent: TaskRuleModal,
  destroyOnClose: true,
});

const { hasAccessByCodes } = useAccess();
const canCreate = computed(() => hasAccessByCodes(['ai-video:task:create']));
const canStart = computed(() => hasAccessByCodes(['ai-video:task:start']));
const canStop = computed(() => hasAccessByCodes(['ai-video:task:stop']));
const canDelete = computed(() => hasAccessByCodes(['ai-video:task:delete']));

const loading = ref(false);
const error = ref('');
const tasks = ref<AiVideoTaskApi.Task[]>([]);
const algorithms = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const selectableAlgorithms = computed(() =>
  algorithms.value.filter(
    (item) =>
      item.status === 0 &&
      !!item.currentPipelineVersionId &&
      !item.capabilityKey?.startsWith('package.') &&
      ['PASS', 'PENDING'].includes(item.pipelineAcceptanceStatus),
  ),
);
const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const modelConfigError = ref(false);
const catalogEntryError = ref('');
let modelConfigGeneration = 0;
const pipelineModelNodes = ref<
  Array<{ label: string; modelId: number; modelIds?: number[]; nodeId: string }>
>([]);
const modelCatalog = ref<ExecutableModelOption[]>([]);
const modelConfigLoading = ref(false);
const rules = ref<AiVideoRuleApi.Rule[]>([]);
const ruleLoadError = ref('');
const ruleLoading = ref(false);
const compatibleRules = computed(() =>
  compatibleTaskRules(rules.value, selectedAlgorithm.value?.eventType),
);
const deployments = ref<AiVideoModelApi.ModelDeployment[]>([]);
const deploymentLoading = ref(false);
const deploymentError = ref('');
let deploymentGeneration = 0;

const wizardOpen = ref(false);
const batchCameraIds = ref<number[]>([]);
const batchResults = ref<AiVideoTaskApi.BatchResult[]>([]);
const batchRegionsConfirmed = ref(false);
const batchRuleVersion = ref<AiVideoRuleApi.RuleVersion>();
const batchRuleLoading = ref(false);
const batchHasRegions = computed(() =>
  hasCustomRegions(batchRuleVersion.value?.ast.regions),
);
let batchRuleGeneration = 0;
let batchRequestId = '';
let batchPayload: AiVideoTaskApi.BatchCreate | undefined;
const [TaskWizard, taskWizardApi] = useVbenDrawer({
  showConfirmButton: false,
  showCancelButton: false,
  onOpenChange(open) {
    wizardOpen.value = open;
  },
});

const wizardStep = ref(0);
const saving = ref(false);
const validationOnly = ref(false);
const wizard = reactive<
  Partial<AiVideoTaskApi.TaskSave> & { modelBindings: Record<string, number> }
>({
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
let initialized = false;
let handledCreateRoute = '';
let queryBusy = false;
let activeQuery: AiVideoTaskApi.TaskPageParams = { pageNo: 1, pageSize: 20 };
let viewActive = true;

const selectedAlgorithm = computed(() =>
  algorithms.value.find((item) => item.id === wizard.algorithmId),
);
const pipelineAccepted = computed(() =>
  pipelineUsable(selectedAlgorithm.value?.pipelineAcceptanceStatus),
);
function pipelineUsable(status?: string) {
  return status === 'PASS' || (validationOnly.value && status === 'PENDING');
}
const parameters = computed(
  () =>
    wizard.parameters as Record<string, boolean | number | string | undefined>,
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
  'confidence',
  'inputHeight',
  'inputWidth',
  'nmsThreshold',
  'sampleFps',
  'schemaVersion',
]);
const parameterFields = computed(() => {
  const schema = selectedAlgorithm.value?.parameterSchema as
    | undefined
    | {
        properties?: Record<
          string,
          {
            description?: string;
            enum?: Array<number | string>;
            maximum?: number;
            minimum?: number;
            title?: string;
            type?: string;
          }
        >;
      };
  return Object.entries(schema?.properties ?? {})
    .filter(([key]) => !commonParameterKeys.has(key))
    .map(([key, definition]) => ({ key, ...definition }));
});
function runnableNodeVersions(nodeId: string) {
  const role = pipelineModelNodes.value.find((node) => node.nodeId === nodeId);
  return role ? taskModelOptions(role, modelCatalog.value) : [];
}
const selectedRule = computed(() =>
  compatibleRules.value.find((item) => item.id === wizard.ruleId),
);
function selectedModel(nodeId: string) {
  return runnableNodeVersions(nodeId).find(
    (model) => model.id === wizard.modelBindings[nodeId],
  );
}
function modelDeploymentState(nodeId: string) {
  const id = wizard.modelBindings[nodeId];
  if (!id) return '未选择';
  const latest = deployments.value
    .filter((deployment) => deployment.modelVersionId === id)
    .toSorted((a, b) => b.configVersion - a.configVersion)[0];
  return latest?.actualStatus === 'READY' ? '已就绪' : '尚未就绪';
}
const [ModelForm, modelForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  schema: [],
  commonConfig: { componentProps: { class: 'w-full' } },
});
const [RuleForm, ruleForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  schema: [
    {
      fieldName: 'ruleId',
      label: '已发布规则',
      component: 'Select',
      componentProps: () => ({
        class: 'w-full',
        allowClear: true,
        showSearch: true,
        optionFilterProp: 'label',
        options: compatibleRules.value.map((rule) => ({
          value: rule.id,
          label: rule.name,
        })),
        placeholder: '选择与当前算法匹配的规则',
        onChange: (id?: number) => {
          wizard.ruleId = id;
        },
      }),
    },
  ],
});
async function syncRuleSelection() {
  ruleForm.updateSchema([
    {
      fieldName: 'ruleId',
      rules: selectedAlgorithm.value?.eventType ? 'required' : undefined,
    },
  ]);
  wizard.ruleId = defaultTaskRule(
    rules.value,
    selectedAlgorithm.value?.eventType,
    wizard.ruleId,
  );
  wizard.ruleVersionId = compatibleRules.value.find(
    (rule) => rule.id === wizard.ruleId,
  )?.currentVersionId;
  await ruleForm.setValues({ ruleId: wizard.ruleId });
  await ruleForm.resetValidate();
}
async function refreshRules() {
  ruleLoading.value = true;
  ruleLoadError.value = '';
  try {
    rules.value = await getPublishedRules();
    await syncRuleSelection();
  } catch {
    ruleLoadError.value = '规则目录读取失败，请重试。';
  } finally {
    ruleLoading.value = false;
  }
}
function openRules() {
  window.open(router.resolve('/ai-video/rule').href, '_blank', 'noopener');
}

const columns: VxeTableGridOptions<AiVideoTaskApi.Task>['columns'] = [
  {
    field: 'name',
    title: '任务',
    minWidth: 220,
    fixed: 'left',
    showOverflow: false,
    slots: { default: 'name' },
  },
  { field: 'code', title: '编码', minWidth: 190 },
  {
    field: 'actualStatus',
    title: '当前 / 期望',
    width: 150,
    showOverflow: false,
    slots: { default: 'status' },
  },
  {
    field: 'cameraId',
    title: '摄像头',
    minWidth: 220,
    formatter: ({ cellValue }) => cameraName(cellValue),
  },
  {
    field: 'algorithmId',
    title: '算法',
    minWidth: 180,
    formatter: ({ cellValue }) => algorithmName(cellValue),
  },
  {
    field: 'nodeId',
    title: '节点',
    minWidth: 180,
    formatter: ({ cellValue }) => nodeName(cellValue),
  },
  {
    field: 'configVersion',
    title: '配置',
    width: 80,
    formatter: ({ cellValue }) => `v${cellValue}`,
  },
  {
    field: 'metricsSnapshot',
    title: '实时指标',
    width: 220,
    slots: { default: 'metrics' },
  },
  {
    field: 'actions',
    title: '操作',
    width: 250,
    fixed: 'right',
    slots: { default: 'actions' },
  },
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
const captureBackendText: Record<string, string> = {
  PENDING: '等待视频帧',
  ROCKCHIP_MPP_RGA: 'MPP 硬解 + RGA',
  SOFTWARE_FFMPEG: 'FFmpeg 软件解码',
  SOFTWARE_PYAV: 'PyAV 软件解码',
  SOFTWARE_PYAV_FALLBACK: 'PyAV 软件解码（硬解回退）',
};
function captureBackend(value: unknown) {
  const code = String(value || 'PENDING');
  return captureBackendText[code] || code;
}

const [Grid, gridApi] = useVbenVxeGrid<AiVideoTaskApi.Task>({
  formOptions: {
    schema: [
      {
        fieldName: 'name',
        label: '任务名称',
        component: 'Input',
        componentProps: { allowClear: true, placeholder: '搜索任务' },
      },
      {
        fieldName: 'actualStatus',
        label: '运行状态',
        component: 'Select',
        componentProps: {
          allowClear: true,
          placeholder: '全部状态',
          options: Object.entries(statusText).map(([value, label]) => ({
            label,
            value,
          })),
        },
      },
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
          quietRefresh.stop();
          queryBusy = true;
          try {
            activeQuery = {
              name: values.name || undefined,
              actualStatus: values.actualStatus || undefined,
              pageNo: page.currentPage,
              pageSize: page.pageSize,
            };
            const result = await getTaskPage(activeQuery);
            error.value = '';
            tasks.value = result.list;
            if (monitoredTask.value) {
              monitoredTask.value = result.list.find(
                (item) => item.id === monitoredTask.value?.id,
              );
            }
            return result;
          } catch (cause) {
            error.value = '任务列表加载失败，请重试。';
            throw cause;
          } finally {
            queryBusy = false;
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
    cameras.value = cameraPage.list;
    nodes.value = nodeList;
    rules.value = ruleList;
    initialized = true;
    if (!viewActive) return;
    await loadTasks();
    await handleCreateRequest();
  } catch {
    error.value = '任务中心初始化失败，请检查控制面、模型和节点状态。';
  } finally {
    loading.value = false;
  }
}

async function handleCreateRequest() {
  try {
    const route = router.currentRoute.value;
    if (
      !viewActive ||
      route.path !== '/ai-video/task' ||
      !initialized ||
      handledCreateRoute === route.fullPath
    )
      return;
    handledCreateRoute = route.fullPath;
    if (route.query.create === '1' && canCreate.value) {
      if (!route.query.cameraIds) {
        openWizard();
        if (Number(route.query.nodeId))
          wizard.nodeId = Number(route.query.nodeId);
        const selected = algorithms.value.find(
          (item) => item.id === Number(route.query.algorithmId),
        );
        if (
          selected &&
          selectableAlgorithms.value.some((item) => item.id === selected.id)
        ) {
          validationOnly.value =
            selected.pipelineAcceptanceStatus === 'PENDING' &&
            route.query.validationOnly === '1';
          wizard.algorithmId = selected.id;
        } else if (route.query.algorithmId) {
          catalogEntryError.value = `“${selected?.name ?? '所选算法'}”暂不可配置：请确认算法已启用，且运行版本已发布并通过验收或允许现场验证。`;
        }
        return;
      }
      const ids = [
        ...new Set(
          String(route.query.cameraIds ?? '')
            .split(',')
            .map(Number),
        ),
      ];
      if (
        ids.length === 0 ||
        ids.length > 100 ||
        ids.some((id) => !Number.isSafeInteger(id) || id <= 0)
      ) {
        message.warning($t('page.aiVideo.cameraAlgorithms.invalidSelection'));
        return;
      }
      const missing = ids.filter(
        (id) => !cameras.value.some((camera) => camera.id === id),
      );
      cameras.value.push(
        ...(await Promise.all(missing.map((id) => getCamera(id)))),
      );
      openWizard();
      batchCameraIds.value = ids;
      wizard.cameraId = ids[0];
      const selectedId = Number(route.query.algorithmId);
      if (algorithms.value.some((item) => item.id === selectedId))
        wizard.algorithmId = selectedId;
    }
  } catch {
    catalogEntryError.value = '无法读取所选摄像头，请关闭后重试。';
  }
}

async function loadTasks() {
  await gridApi.query();
}

const quietRefresh = createQuietRefresh({
  active: () =>
    viewActive &&
    router.currentRoute.value.path === '/ai-video/task' &&
    !document.hidden &&
    !queryBusy &&
    !wizardOpen.value &&
    (monitorOpen.value ||
      tasks.value.some((item) =>
        ['RUNNING', 'STARTING', 'STOPPING'].includes(item.actualStatus),
      )),
  fetch: () => getTaskPage(activeQuery),
  apply: async (result) => {
    error.value = '';
    tasks.value = result.list;
    if (monitoredTask.value)
      monitoredTask.value = result.list.find(
        (item) => item.id === monitoredTask.value?.id,
      );
    // Polling updates rows without Vxe's query loading mask or rebuilding the page.
    await gridApi.grid.loadData(result.list);
    gridApi.setGridOptions({ pagerConfig: { total: result.total } });
  },
  onError: () => {
    error.value = '运行状态暂时无法更新，正在显示上次结果。';
  },
});
function schedulePoll() {
  quietRefresh.schedule();
}
function visibilityChanged() {
  quietRefresh.stop();
  schedulePoll();
}

function openWizard() {
  catalogEntryError.value = '';
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
  taskWizardApi.open();
}

async function loadVersions() {
  const currentRequest = ++modelConfigGeneration;
  let algorithm = selectedAlgorithm.value;
  modelConfigError.value = false;
  modelConfigLoading.value = true;
  modelCatalog.value = [];
  pipelineModelNodes.value = [];
  modelForm.setState({ schema: [] });
  wizard.modelVersionId = undefined;
  wizard.modelBindings = {};
  wizard.pipelineVersionId = undefined;
  if (!algorithm) {
    modelConfigLoading.value = false;
    return;
  }
  try {
    const [pipelines, catalog, latestAlgorithm, ruleList] = await Promise.all([
      getPipelineVersions(algorithm.id),
      getExecutableModelOptions(),
      getAlgorithm(algorithm.id),
      getPublishedRules(),
    ]);
    if (currentRequest !== modelConfigGeneration) return;
    algorithm = latestAlgorithm;
    algorithms.value = algorithms.value.map((item) =>
      item.id === latestAlgorithm.id ? latestAlgorithm : item,
    );
    rules.value = ruleList;
    ruleLoadError.value = '';
    const current = pipelines.find(
      (item) => item.id === algorithm?.currentPipelineVersionId,
    );
    if (!current) throw new Error('算法已发布版本不可用');
    pipelineModelNodes.value = taskModelRoles(algorithm, current);
    modelCatalog.value = catalog;
    for (const node of pipelineModelNodes.value) {
      const choices = runnableNodeVersions(node.nodeId);
      if (choices.length === 1)
        wizard.modelBindings[node.nodeId] = choices[0]!.id;
    }
    modelForm.setState({
      schema: pipelineModelNodes.value.map((node, index) => ({
        fieldName: `role_${currentRequest}_${index}`,
        label: node.label,
        component: 'Select',
        rules: 'required',
        help:
          runnableNodeVersions(node.nodeId).length === 1
            ? '该用途当前只有 1 个已发布且通过测试的版本；更换模型资产需更新算法配置。'
            : undefined,
        componentProps: () => ({
          options: runnableNodeVersions(node.nodeId).map((model) => ({
            value: model.id,
            label: taskModelLabel(model),
          })),
          optionFilterProp: 'label',
          showSearch: true,
          onChange: (value: number) => {
            wizard.modelBindings[node.nodeId] = value;
            wizard.modelVersionId =
              wizard.modelBindings[pipelineModelNodes.value[0]!.nodeId];
          },
        }),
      })),
    });
    await nextTick();
    if (currentRequest !== modelConfigGeneration) return;
    await modelForm.resetForm(
      {
        values: Object.fromEntries(
          pipelineModelNodes.value.map((node, index) => [
            `role_${currentRequest}_${index}`,
            wizard.modelBindings[node.nodeId],
          ]),
        ),
      },
      { force: true },
    );
    if (currentRequest !== modelConfigGeneration) return;
    wizard.pipelineVersionId = algorithm.currentPipelineVersionId;
    wizard.parameters = JSON.parse(JSON.stringify(algorithm.defaultParameters));
    wizard.modelVersionId = Object.values(wizard.modelBindings)[0];
    await syncRuleSelection();
  } catch {
    if (currentRequest === modelConfigGeneration) modelConfigError.value = true;
  } finally {
    if (currentRequest === modelConfigGeneration)
      modelConfigLoading.value = false;
  }
}

async function submitWizard(startImmediately: boolean) {
  if (
    (batchCameraIds.value.length === 0 && (!wizard.name || !wizard.code)) ||
    !wizard.cameraId ||
    !wizard.algorithmId ||
    !wizard.modelVersionId ||
    modelConfigLoading.value ||
    modelConfigError.value ||
    pipelineModelNodes.value.some((node) => !selectedModel(node.nodeId)) ||
    !wizard.nodeId ||
    !pipelineAccepted.value ||
    (selectedAlgorithm.value?.eventType &&
      (!selectedRule.value || !wizard.ruleVersionId)) ||
    !wizard.parameters ||
    (batchCameraIds.value.length > 0 &&
      (batchRuleLoading.value ||
        (wizard.ruleId && !batchRuleVersion.value) ||
        (batchHasRegions.value && !batchRegionsConfirmed.value)))
  ) {
    message.warning('任务配置未完成，请检查七个步骤');
    return;
  }
  saving.value = true;
  try {
    wizard.parameters.validationOnly = validationOnly.value;
    if (batchCameraIds.value.length > 0) {
      batchPayload ??= JSON.parse(
        JSON.stringify({
          ...wizard,
          cameraIds: batchCameraIds.value,
          requestId: batchRequestId,
          confirmSharedRegions: batchRegionsConfirmed.value,
        }),
      ) as AiVideoTaskApi.BatchCreate;
      batchResults.value = await batchCreateTasks(batchPayload);
      await loadTasks();
      return;
    }
    await createTask(wizard as AiVideoTaskApi.TaskSave);

    message.success('任务配置已保存，请在所属网关启动识别');
    taskWizardApi.close();
    if (startImmediately && wizard.nodeId)
      await router.push(gatewayLocation(wizard.nodeId));
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
watch([saving, () => !!batchPayload], ([disabled, batch]) => {
  modelForm.setDisabled(disabled || batch);
  ruleForm.setDisabled(disabled || batch);
});
watch([() => wizard.nodeId, wizardOpen], async ([nodeId, open]) => {
  const generation = ++deploymentGeneration;
  deployments.value = [];
  deploymentError.value = '';
  deploymentLoading.value = !!nodeId && open;
  if (!nodeId || !open) return;
  try {
    const result = await getNodeModelDeployments(nodeId);
    if (generation === deploymentGeneration) deployments.value = result;
  } catch {
    if (generation === deploymentGeneration)
      deploymentError.value =
        '无法读取此节点的模型部署状态，请在网关模型管理中检查。';
  } finally {
    if (generation === deploymentGeneration) deploymentLoading.value = false;
  }
});
watch(
  [() => wizard.ruleId, () => selectedRule.value?.currentVersionId],
  async ([id, versionId]) => {
    wizard.ruleVersionId = versionId;
    batchRuleVersion.value = undefined;
    batchRegionsConfirmed.value = false;
    const current = ++batchRuleGeneration;
    if (batchCameraIds.value.length === 0 || !id) {
      batchRuleLoading.value = false;
      return;
    }
    batchRuleLoading.value = true;
    try {
      const versions = await getRuleVersions(id);
      if (current === batchRuleGeneration)
        batchRuleVersion.value = versions.find(
          (item) => item.id === wizard.ruleVersionId,
        );
    } catch {
      message.error($t('page.aiVideo.cameraAlgorithms.ruleLoadFailed'));
    } finally {
      if (current === batchRuleGeneration) batchRuleLoading.value = false;
    }
  },
);
watch([monitorOpen, wizardOpen], () => {
  quietRefresh.stop();
  schedulePoll();
});
watch(
  () => router.currentRoute.value.fullPath,
  () => {
    if (viewActive) void handleCreateRequest();
  },
);
onMounted(() => {
  document.addEventListener('visibilitychange', visibilityChanged);
  void loadInitial();
});
onActivated(() => {
  viewActive = true;
  if (initialized) {
    void handleCreateRequest();
    schedulePoll();
  } else if (!loading.value) void loadInitial();
});
onDeactivated(() => {
  viewActive = false;
  handledCreateRoute = '';
  taskWizardApi.close();
  quietRefresh.stop();
});
onBeforeUnmount(() => {
  viewActive = false;
  modelConfigGeneration += 1;
  batchRuleGeneration += 1;
  quietRefresh.stop();
  document.removeEventListener('visibilitychange', visibilityChanged);
});
</script>

<template>
  <Page auto-content-height>
    <RuleModal @success="loadTasks" />
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="AI 任务"
        description="配置识别任务，查看运行状态。"
        icon="lucide:scan-line"
      >
        <template #extra>
          <Button v-if="canCreate" type="primary" @click="openWizard">
            <IconifyIcon icon="lucide:plus" />创建任务
          </Button>
        </template>
      </AiPageHeader>

      <Alert v-if="error" :message="error" show-icon type="error">
        <template #action><Button @click="loadInitial">重试</Button></template>
      </Alert>
      <Grid class="task-grid min-h-0 flex-1" table-title="AI 任务中心">
        <template #name="{ row }">
          <div class="task-name" :title="row.name">{{ row.name }}</div>
          <Tag
            v-if="row.parameters?.validationOnly === true"
            class="mt-1"
            color="orange"
          >
            {{ $t('ai-video-task.validationMode') }}
          </Tag>
          <div
            v-if="row.errorMessage"
            class="task-error mt-1 text-xs text-red-500"
            :title="`${row.errorMessage} · ${row.diagnosticId || ''}`"
          >
            {{ row.errorMessage }} · {{ row.diagnosticId }}
          </div>
        </template>
        <template #status="{ row }">
          <AiStatusIndicator
            :label="statusText[row.actualStatus] || row.actualStatus"
            :status="row.actualStatus"
            :pulse="row.actualStatus === 'RUNNING'"
          />
          <div
            v-if="row.actualStatus !== row.desiredStatus"
            class="mt-1 text-xs text-amber-500"
          >
            期望：{{ statusText[row.desiredStatus] || row.desiredStatus }}
          </div>
        </template>
        <template #metrics="{ row }">
          <div
            v-if="row.metricsSnapshot"
            class="whitespace-nowrap tabular-nums"
          >
            <div>
              {{ row.metricsSnapshot.analysisFps ?? 0 }} FPS ·
              {{ row.metricsSnapshot.inferenceMillis ?? 0 }} ms
            </div>
            <div class="mt-1 text-xs text-muted-foreground">
              {{ captureBackend(row.metricsSnapshot.captureBackend) }}
            </div>
          </div>
          <span v-else class="text-muted-foreground">暂无指标</span>
        </template>
        <template #actions="{ row }">
          <TableAction
            :actions="[
              { label: '监控', type: 'link', onClick: () => openMonitor(row) },
              {
                label: '更换规则',
                type: 'link',
                ifShow:
                  hasAccessByCodes(['ai-video:task:update']) &&
                  (['DRAFT', 'STOPPED'].includes(row.actualStatus) ||
                    (row.actualStatus === 'RUNNING' && canStart && canStop)),
                onClick: () => ruleModalApi.setData(row).open(),
              },
              {
                label: '管理算法',
                type: 'link',
                ifShow: hasAccessByCodes(['ai-video:node:query']),
                onClick: () =>
                  router.push(
                    gatewayLocation(row.nodeId, 'algorithms', row.cameraId),
                  ),
              },
              {
                label: '删除',
                type: 'link',
                danger: true,
                ifShow:
                  canDelete && ['DRAFT', 'STOPPED'].includes(row.actualStatus),
                popConfirm: {
                  title: `确认删除任务“${row.name}”吗？`,
                  confirm: () => remove(row),
                },
              },
            ]"
          />
        </template>
      </Grid>
    </div>

    <TaskWizard
      class="ai-dialog w-[1100px]"
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
    >
      <Alert
        v-if="catalogEntryError"
        class="mb-4"
        type="warning"
        show-icon
        :message="catalogEntryError"
      >
        <template #action>
          <Button @click="router.push('/ai-video/model')">
            前往模型中心
          </Button>
        </template>
      </Alert>
      <template #title>
        {{
          batchCameraIds.length
            ? $t('page.aiVideo.cameraAlgorithms.batchWizardTitle')
            : '任务创建向导'
        }}
      </template>
      <template v-if="batchResults.length">
        <Alert
          v-for="result in batchResults"
          :key="result.cameraId"
          class="mb-3"
          show-icon
          :type="result.status === 'FAILED' ? 'error' : 'success'"
          :message="`${cameraName(result.cameraId)} · ${result.message}`"
        />
        <Space>
          <Button
            v-if="batchResults.some((item) => item.status === 'FAILED')"
            :loading="saving"
            @click="submitWizard(false)"
          >
            {{ $t('page.aiVideo.cameraAlgorithms.retrySave') }}
          </Button>
          <Button
            type="primary"
            @click="
              wizardOpen = false;
              router.push('/ai-video/camera');
            "
          >
            {{ $t('page.aiVideo.cameraAlgorithms.backToCameras') }}
          </Button>
        </Space>
      </template>
      <template v-else>
        <Alert
          v-if="modelConfigError"
          type="error"
          class="mb-3"
          :message="$t('page.aiVideo.cameraAlgorithms.modelLoadFailed')"
        >
          <template #action>
            <Button @click="loadVersions">
              {{ $t('page.aiVideo.cameraAlgorithms.reload') }}
            </Button>
          </template>
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
        <div class="task-wizard-layout">
          <Card class="task-wizard-main" size="small">
            <section v-show="wizardStep === 2">
              <ModelForm />
              <p v-if="modelConfigLoading" class="text-muted-foreground">
                正在读取算法模型版本…
              </p>
              <Alert
                v-else-if="
                  pipelineModelNodes.some(
                    (node) => !runnableNodeVersions(node.nodeId).length,
                  )
                "
                message="当前算法有模型尚未发布或通过测试，请先在模型管理中补齐。"
                show-icon
                type="warning"
              />
            </section>
            <section v-show="wizardStep === 5" class="space-y-3">
              <RuleForm />
              <Alert
                v-if="ruleLoadError"
                :message="ruleLoadError"
                show-icon
                type="error"
              />
              <p v-else-if="selectedRule" class="text-sm text-muted-foreground">
                {{ selectedRule.description || selectedRule.name }} · 版本 #{{
                  wizard.ruleVersionId
                }}
              </p>
              <Alert
                v-else-if="
                  selectedAlgorithm?.eventType && !compatibleRules.length
                "
                message="当前算法没有匹配的已发布规则。请到规则中心创建并发布，然后刷新此处。"
                show-icon
                type="warning"
              />
              <p
                v-else-if="selectedAlgorithm?.eventType"
                class="text-sm text-muted-foreground"
              >
                请选择一项规则，设置事件触发条件。
              </p>
              <Space>
                <Button
                  :loading="ruleLoading"
                  :disabled="saving || !!batchPayload"
                  @click="refreshRules"
                  >刷新规则</Button
                >
                <Button @click="openRules">规则中心</Button>
              </Space>
            </section>
            <Form
              v-show="wizardStep !== 2 && wizardStep !== 5"
              layout="vertical"
              :disabled="saving || !!batchPayload"
            >
              <template v-if="wizardStep === 0">
                <div v-if="batchCameraIds.length" class="space-y-3">
                  <p>
                    {{
                      $t('page.aiVideo.cameraAlgorithms.targets', {
                        count: batchCameraIds.length,
                      })
                    }}
                  </p>
                  <Tag v-for="id in batchCameraIds" :key="id">
                    {{ cameraName(id) }}
                  </Tag>
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
                <FormItem
                  :label="$t('ai-video-task.validationMode')"
                  :help="$t('ai-video-task.validationHelp')"
                >
                  <Switch v-model:checked="validationOnly" />
                </FormItem>
                <FormItem
                  label="可运行算法"
                  required
                  extra="选择算法后检查依赖模型；待验收算法需开启现场验证。节点部署与单图测试将在后续步骤检查。"
                >
                  <Select
                    v-model:value="wizard.algorithmId"
                    :options="
                      selectableAlgorithms.map((item) => ({
                        label: `${item.name}${item.pipelineAcceptanceStatus === 'PASS' ? '' : ' · 现场验证'}${!pipelineUsable(item.pipelineAcceptanceStatus) ? '（请先开启现场验证）' : ''}`,
                        value: item.id,
                        disabled: !pipelineUsable(
                          item.pipelineAcceptanceStatus,
                        ),
                      }))
                    "
                  />
                </FormItem>
                <p v-if="selectedAlgorithm?.description" class="ai-form-note">
                  {{ selectedAlgorithm.description }}
                </p>
                <Alert
                  v-if="selectedAlgorithm && !pipelineAccepted"
                  class="mt-3"
                  :message="`该 Pipeline 尚未通过生产验收（${selectedAlgorithm.pipelineAcceptanceStatus}），不能创建或启动任务。`"
                  show-icon
                  type="warning"
                />
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
                <p v-if="deploymentLoading" class="text-muted-foreground">
                  正在检查模型部署状态…
                </p>
                <Alert
                  v-else-if="deploymentError"
                  :message="deploymentError"
                  type="warning"
                  show-icon
                />
                <div v-else class="space-y-2">
                  <div
                    v-for="role in pipelineModelNodes"
                    :key="role.nodeId"
                    class="flex items-center justify-between gap-3"
                  >
                    <span>{{ role.label }}</span>
                    <Tag
                      :color="
                        modelDeploymentState(role.nodeId) === '已就绪'
                          ? 'green'
                          : 'orange'
                      "
                      >{{ modelDeploymentState(role.nodeId) }}</Tag
                    >
                  </div>
                  <p
                    v-if="
                      pipelineModelNodes.some(
                        (role) =>
                          modelDeploymentState(role.nodeId) !== '已就绪',
                      )
                    "
                    class="text-sm text-muted-foreground"
                  >
                    可先保存草稿；启动前需将所选模型部署到此网关。其他网关上已有模型不会自动复制过来。
                  </p>
                </div>
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
                  <FormItem
                    v-for="field in parameterFields"
                    :key="field.key"
                    :label="field.title || field.key"
                    :help="field.description"
                  >
                    <Select
                      v-if="field.enum?.length"
                      v-model:value="selectParameters[field.key]"
                      :options="
                        field.enum.map((value) => ({
                          label: String(value),
                          value,
                        }))
                      "
                    />
                    <Switch
                      v-else-if="field.type === 'boolean'"
                      v-model:checked="booleanParameters[field.key]"
                    />
                    <InputNumber
                      v-else-if="
                        field.type === 'number' || field.type === 'integer'
                      "
                      v-model:value="numberParameters[field.key]"
                      :max="field.maximum"
                      :min="field.minimum"
                      :precision="field.type === 'integer' ? 0 : undefined"
                      class="w-full"
                    />
                    <Input v-else v-model:value="stringParameters[field.key]" />
                  </FormItem>
                </div>
              </template>
              <template v-else>
                <FormItem
                  v-if="!batchCameraIds.length"
                  label="任务名称"
                  required
                >
                  <Input v-model:value="wizard.name" :maxlength="100" />
                </FormItem>
                <FormItem
                  v-if="!batchCameraIds.length"
                  label="稳定编码"
                  required
                >
                  <Input
                    v-model:value="wizard.code"
                    :maxlength="64"
                    placeholder="person-line-01"
                  />
                </FormItem>
                <FormItem
                  v-if="batchCameraIds.length && batchHasRegions"
                  :label="$t('page.aiVideo.cameraAlgorithms.confirmRegions')"
                >
                  <Switch v-model:checked="batchRegionsConfirmed" />
                  <p class="mt-2 text-xs text-muted-foreground">
                    {{ $t('page.aiVideo.cameraAlgorithms.regionsHint') }}
                  </p>
                </FormItem>
              </template>
            </Form>
          </Card>
          <Card class="task-wizard-summary" size="small" title="配置摘要">
            <Descriptions :column="1" size="small">
              <DescriptionsItem :label="$t('ai-video-task.mode')">
                {{
                  $t(
                    validationOnly
                      ? 'ai-video-task.validationMode'
                      : 'ai-video-task.productionMode',
                  )
                }}
              </DescriptionsItem>
              <DescriptionsItem label="摄像头">
                {{
                  batchCameraIds.length
                    ? $t('page.aiVideo.cameraAlgorithms.targets', {
                        count: batchCameraIds.length,
                      })
                    : wizard.cameraId
                      ? cameraName(wizard.cameraId)
                      : '未选择'
                }}
              </DescriptionsItem>
              <DescriptionsItem label="算法">
                {{
                  wizard.algorithmId
                    ? algorithmName(wizard.algorithmId)
                    : '未选择'
                }}
              </DescriptionsItem>
              <DescriptionsItem label="Pipeline">
                {{
                  wizard.pipelineVersionId
                    ? `#${wizard.pipelineVersionId}`
                    : '未发布'
                }}
              </DescriptionsItem>
              <DescriptionsItem
                v-for="role in pipelineModelNodes"
                :key="role.nodeId"
                :label="role.label"
              >
                {{ taskModelLabel(selectedModel(role.nodeId)) }}
              </DescriptionsItem>
              <DescriptionsItem label="节点">
                {{ wizard.nodeId ? nodeName(wizard.nodeId) : '未选择' }}
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
              <Button
                v-if="!batchCameraIds.length && canStart"
                :loading="saving"
                type="primary"
                @click="submitWizard(true)"
              >
                保存并前往网关
              </Button>
            </template>
          </Space>
        </div>
      </template>
    </TaskWizard>

    <Drawer
      v-model:open="monitorOpen"
      placement="right"
      width="min(1100px, 96vw)"
      root-class-name="ai-dialog"
      :body-style="{ padding: '24px' }"
    >
      <template #title>{{ monitoredTask?.name }} · 运行监控</template>
      <template v-if="monitoredTask">
        <div
          v-if="monitoredTask.gatewayRevision"
          class="mb-4 flex flex-wrap items-center justify-between gap-2"
        >
          <span class="ai-form-note">{{
            $t('ai-video-gateway.executionRevision', {
              revision: monitoredTask.gatewayRevision,
            })
          }}</span>
          <Button
            type="link"
            @click="
              monitorOpen = false;
              router.push(
                gatewayLocation(
                  monitoredTask.nodeId,
                  'algorithms',
                  monitoredTask.cameraId,
                ),
              );
            "
          >
            {{ $t('ai-video-gateway.openWorkbench') }}
          </Button>
        </div>
        <Alert
          v-if="monitoredTask.parameters.validationOnly === true"
          :message="$t('ai-video-task.validationHelp')"
          show-icon
          type="warning"
          class="mb-4"
        />
        <Alert
          v-if="monitoredTask.actualStatus === 'FAILED'"
          :message="`发生了什么：${monitoredTask.errorMessage || monitoredTask.errorCode || '节点执行失败'}`"
          :description="`影响：当前任务未运行。建议：检查模型部署、摄像头连通性和节点资源。诊断 ID：${monitoredTask.diagnosticId || '无'}`"
          show-icon
          type="error"
        />
        <AlgorithmDiagnostic
          :value="monitoredTask.metricsSnapshot?.algorithmError"
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
              {{ monitoredTask.activeRunId || '未运行' }}
            </DescriptionsItem>
            <DescriptionsItem label="配置版本">
              v{{ monitoredTask.configVersion }}
            </DescriptionsItem>
            <DescriptionsItem label="视频解码">
              {{
                captureBackend(monitoredTask.metricsSnapshot?.captureBackend)
              }}
            </DescriptionsItem>
            <DescriptionsItem label="摄像头">
              {{ cameraName(monitoredTask.cameraId) }}
            </DescriptionsItem>
            <DescriptionsItem label="算法">
              {{ algorithmName(monitoredTask.algorithmId) }}
            </DescriptionsItem>
            <DescriptionsItem label="节点">
              {{ nodeName(monitoredTask.nodeId) }}
            </DescriptionsItem>
            <DescriptionsItem label="最近心跳">
              {{ monitoredTask.lastHeartbeatTime || '尚未上报' }}
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
.task-wizard-layout {
  display: grid;
  grid-template-columns: minmax(0, 2fr) minmax(0, 1fr);
  gap: 20px;
  align-items: start;
}

@container (width < 760px) {
  .task-wizard-layout {
    grid-template-columns: minmax(0, 1fr);
  }
}

.task-name,
.task-error {
  display: -webkit-box;
  overflow: hidden;
  -webkit-line-clamp: 2;
  overflow-wrap: anywhere;
  -webkit-box-orient: vertical;
}

.task-name {
  font-weight: 500;
  line-height: 1.5;
}
</style>
