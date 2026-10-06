<script setup lang="ts">
import type { UploadFile } from 'ant-design-vue';
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { ExecutableModelOption } from '#/api/ai-video/model';
import type {
  GatewayCapacityPreflight,
  GatewayEvent,
  GatewayOverlay,
  GatewaySnapshot,
  GatewayTask,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';
import type { PreviewTransport } from '#/components/ai-video/preview-transport';

import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, Page, useVbenModal } from '@vben/common-ui';

import {
  Alert,
  Button,
  Empty,
  Input,
  InputNumber,
  message,
  Select,
  TabPane,
  Tabs,
  Tag,
  Upload,
} from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getExecutableModelOptions } from '#/api/ai-video/model';
import { $t } from '#/locales';

import LocalPackageModal from '../algorithm/modules/local-package-modal.vue';
import PackageParameters from '../algorithm/modules/package-parameters.vue';
import PlateTaskModal from '../algorithm/modules/plate-task-modal.vue';
import {
  eventTypes,
  formatTime,
  recognitionResult,
} from '../event/presentation';
import {
  confirmationLatencyMessage,
  conflictsWithVisibilityTarget,
  estimateConfirmationLatency,
} from '../rule/confirmation-latency';
import {
  gatewayCapacitySummary,
  requireGatewayCapacity,
} from './gateway-capacity';
import {
  gatewayModelRoles,
  gatewayRoleModelId,
  gatewayRoleModelOptions,
  updateGatewayModelBindings,
} from './gateway-model-bindings';
import {
  gatewayPackageManifest,
  gatewayParameterDefinition,
  gatewaySpecificParameters,
  mergeGatewayParameters,
} from './gateway-task-parameters';
import GatewayEventDelivery from './modules/gateway-event-delivery.vue';
import ApplicationUpgrade from './modules/application-upgrade.vue';
import GatewayRecognitionPreview from './modules/gateway-recognition-preview.vue';
import GatewayRuleEditor from './modules/gateway-rule-editor.vue';
import ImageRecognitionModal from './modules/image-recognition-modal.vue';

const props = withDefaults(
  defineProps<{
    canEdit?: boolean;
    local?: boolean;
    section?: 'delivery' | 'events' | 'models' | 'preview';
    transport: GatewayTransport;
  }>(),
  { canEdit: true, section: undefined },
);
const snapshot = ref<GatewaySnapshot>({
  tasks: [],
  models: [],
  historyDays: 7,
});
const error = ref('');
const loading = ref(false);
const hasSnapshot = ref(false);
const changingTask = ref<number>();
const previewPanel = ref<HTMLElement>();
let refreshGeneration = 0;
const activeTab = ref(
  props.section === 'preview' ? 'tasks' : props.section || 'tasks',
);
defineExpose({ edit, selectTask, refresh });
const selected = ref<number>();
const { hasAccessByCodes } = useAccess();
const [ImageRecognition, imageRecognitionApi] = useVbenModal({
  connectedComponent: ImageRecognitionModal,
  destroyOnClose: true,
});
function recognizeImage(task: GatewayTask) {
  imageRecognitionApi
    .setData({
      task,
      validationSupported: snapshot.value.capabilities?.includes('task.image-validation.v1') ?? false,
      supported:
        snapshot.value.capabilities?.includes('task.image-recognition.v1') ??
        false,
    })
    .open();
}
const canPreview = computed(
  () => props.local || hasAccessByCodes(['ai-video:camera:preview']),
);
const editing = ref<GatewayTask>();
const supportsLocalStreams = computed(() =>
  snapshot.value.capabilities?.includes('task.stream-switch.v1') ?? false,
);
const canSelectStream = computed(() =>
  supportsLocalStreams.value || (!props.local && editing.value?.platformManaged === true),
);
let editGeneration = 0;
const algorithmParameters = ref<InstanceType<typeof PackageParameters>>();
const editingParameterDefinition = computed(() =>
  editing.value ? gatewayParameterDefinition(editing.value.config) : undefined,
);
const editingStatistics = computed(() =>
  editing.value
    ? gatewayPackageManifest(editing.value.config)?.outputMode === 'STATISTICS'
    : false,
);
const ruleText = ref('');
const editingSampleFps = ref(1);
const editingRule = computed<Record<string, unknown> | undefined>(() => {
  try {
    return ruleText.value ? JSON.parse(ruleText.value) : undefined;
  } catch {
    return undefined;
  }
});
const editingLatency = computed(() =>
  estimateConfirmationLatency(editingRule.value, editingSampleFps.value),
);
const editingLatencyConflict = computed(
  () =>
    editingRule.value?.eventType === 'PHONE_CALL' &&
    conflictsWithVisibilityTarget(editingLatency.value),
);
const editingLatencyBlocked = computed(
  () =>
    editingLatencyConflict.value &&
    (!editing.value ||
      editing.value.revision === 0 ||
      editingSampleFps.value !==
        Number(editing.value.config.parameters.sampleFps) ||
      JSON.stringify(editingRule.value) !==
        JSON.stringify(editing.value.config.rule)),
);
const modelCatalog = ref<ExecutableModelOption[]>([]);
const editingModelRoles = computed(() =>
  editing.value ? gatewayModelRoles(editing.value.config) : [],
);
const editError = ref('');
const editingImage = ref<string>();
const editingImageSize = ref<{ height: number; width: number }>();
const editTab = ref('basic');
const ruleEditor = ref<InstanceType<typeof GatewayRuleEditor>>();
const editingCamera = computed(() =>
  editing.value
    ? {
        id: editing.value.config.cameraId,
        code: `camera-${editing.value.config.cameraId}`,
        name:
          snapshot.value.names?.cameras[editing.value.config.cameraId] ??
          '当前摄像头',
        status: 0,
      }
    : undefined,
);
const editingPreviewTransport = computed<PreviewTransport>(() => {
  const taskId = editing.value?.config.taskId;
  return {
    create: (offer) => props.transport('preview.open', { taskId, ...offer }),
    get: (sessionId: string) =>
      props.transport('preview.status', { taskId, sessionId }),
    release: (sessionId: string) =>
      props.transport('preview.close', { taskId, sessionId }),
  };
});
const evidenceImage = ref('');
const evidenceId = ref('');
const evidenceVideo = ref(false);
const evidenceEvent = ref<GatewayEvent>();
const videoUrl = ref('');
const videoLoading = ref(false);
const videoProgress = ref(0);
let videoGeneration = 0;
const packageFile = ref<File>();
const packageFileList = ref<UploadFile[]>([]);
const packageError = ref('');
const [PackageModal, packageModal] = useVbenModal({
  connectedComponent: LocalPackageModal,
  destroyOnClose: true,
});
const [PlateModal, plateModal] = useVbenModal({
  connectedComponent: PlateTaskModal,
  destroyOnClose: true,
});
function configurePipeline(template: string) {
  if (template === 'license-plate') plateModal.open();
}
const [PackageUpload, packageUpload] = useVbenModal({
  class: 'w-[560px] max-w-[calc(100vw-32px)]',
  confirmDisabled: true,
  confirmText: '安装',
  title: '安装算法包',
  onOpenChange(open) {
    if (open) return;
    packageFile.value = undefined;
    packageFileList.value = [];
    packageError.value = '';
    packageUpload.setState({ confirmDisabled: true });
  },
  onConfirm: installPackage,
});
function choosePackage(file: FileType) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    packageFile.value = undefined;
    packageFileList.value = [];
    packageError.value = '仅支持 ZIP 格式的算法包';
    packageUpload.setState({ confirmDisabled: true });
    return Upload.LIST_IGNORE;
  }
  if (file.size > 8 * 1024 * 1024) {
    packageFile.value = undefined;
    packageFileList.value = [];
    packageError.value = '算法包不能超过 8 MB';
    packageUpload.setState({ confirmDisabled: true });
    return Upload.LIST_IGNORE;
  }
  packageFile.value = file;
  packageError.value = '';
  packageUpload.setState({ confirmDisabled: false });
  return false;
}
function removePackage() {
  packageFile.value = undefined;
  packageError.value = '';
  packageUpload.setState({ confirmDisabled: true });
  return true;
}
async function installPackage() {
  if (!packageFile.value || packageFile.value.size > 8 * 1024 * 1024) {
    packageError.value = '请选择不超过 8 MB 的算法 ZIP';
    return;
  }
  packageUpload.lock();
  packageError.value = '';
  try {
    const data = await packageFile.value.arrayBuffer();
    let binary = '';
    for (const byte of new Uint8Array(data))
      binary += String.fromCodePoint(byte);
    await props.transport('algorithm.install', { base64: btoa(binary) });
    packageUpload.close();
    packageFile.value = undefined;
    message.success('算法已安装，可添加识别配置');
  } catch (error) {
    packageError.value = error instanceof Error ? error.message : '安装失败';
  } finally {
    packageUpload.unlock();
  }
}
const modelFile = ref<File>();
const modelManifest = ref('');
const modelVersion = ref(Date.now());
const modelDisplayName = ref('');
const modelReleaseVersion = ref('');

function taskEventType(task: GatewayTask) {
  const descriptor = task.config.pipeline.algorithmPackage as
    | undefined
    | { manifest?: { eventType?: string } };
  return String(
    task.config.rule?.eventType ?? descriptor?.manifest?.eventType ?? '',
  );
}
function resolvedAlgorithmName(task: GatewayTask) {
  const descriptor = task.config.pipeline.algorithmPackage as
    | undefined
    | { manifest?: { name?: string } };
  return (
    task.displayNames?.algorithm ||
    task.config.displayNames?.algorithm ||
    snapshot.value.names?.algorithms?.[task.config.algorithmId] ||
    descriptor?.manifest?.name ||
    eventTypes[taskEventType(task)]
  );
}
function algorithmName(task: GatewayTask) {
  return (
    resolvedAlgorithmName(task) ||
    $t('ai-video-gateway.algorithmFallback', { id: task.config.algorithmId })
  );
}
function taskName(task: GatewayTask) {
  const published =
    task.platformManaged === false
      ? undefined
      : snapshot.value.names?.tasks[task.config.taskId];
  const raw =
    task.displayNames?.task ||
    task.config.displayNames?.task ||
    published ||
    task.name;
  return /^任务\s*#?\d+$/.test(raw || '') && resolvedAlgorithmName(task)
    ? `${resolvedAlgorithmName(task)}任务`
    : raw || $t('ai-video-gateway.taskFallback', { id: task.config.taskId });
}
function cameraName(task: GatewayTask) {
  return (
    task.displayNames?.camera ||
    task.config.displayNames?.camera ||
    (task.platformManaged === false
      ? undefined
      : snapshot.value.names?.cameras[task.config.cameraId]) ||
    $t('ai-video-gateway.cameraFallback', { id: task.config.cameraId })
  );
}
function modelName(id: number) {
  const installed = snapshot.value.models.find(
    (model) => model.modelVersionId === id,
  );
  const roleNames = snapshot.value.tasks.flatMap((task) => {
    const descriptor = task.config.pipeline.algorithmPackage as
      | undefined
      | { manifest?: { models?: { name?: string; slot: string }[] } };
    return (descriptor?.manifest?.models ?? [])
      .filter(
        (role) => task.config.modelBindings[role.slot] === id && role.name,
      )
      .map((role) => role.name!);
  });
  return (
    snapshot.value.names?.models[id]?.name ||
    installed?.displayName ||
    [...new Set(roleNames)][0] ||
    $t('ai-video-gateway.modelFallback', { id })
  );
}
function modelVersionLabel(id: number) {
  return (
    snapshot.value.names?.models[id]?.version ||
    snapshot.value.models.find((model) => model.modelVersionId === id)
      ?.version ||
    `版本 #${id}`
  );
}
function eventTypeName(value: unknown) {
  const code = String(value || '');
  return eventTypes[code] || code || '未记录';
}
function eventTaskName(event: GatewayEvent) {
  const taskId = Number(event.payload.taskId);
  const task = snapshot.value.tasks.find(
    (value) => value.config.taskId === taskId,
  );
  const saved = event.payload.taskSnapshot as
    | undefined
    | { displayNames?: { task?: string } };
  return task
    ? taskName(task)
    : String(
        event.payload.taskName ||
          saved?.displayNames?.task ||
          $t('ai-video-gateway.taskFallback', { id: taskId }),
      );
}
function percent(value: unknown) {
  return typeof value === 'number' ? `${Math.round(value * 100)}%` : '—';
}
function analysisFps(task: GatewayTask) {
  const fps = task.status.metrics.analysisFps;
  return task.status.status === 'RUNNING' && typeof fps === 'number'
    ? `${fps.toFixed(1)} FPS`
    : '—';
}
function captureBackend(value: unknown) {
  const code = String(value || 'PENDING');
  return (
    {
      PENDING: '等待视频帧',
      ROCKCHIP_MPP_RGA: 'MPP 硬解 + RGA',
      SOFTWARE_FFMPEG: 'FFmpeg 软件解码',
      SOFTWARE_PYAV: 'PyAV 软件解码',
      SOFTWARE_PYAV_FALLBACK: 'PyAV 软件解码（硬解回退）',
    }[code] || code
  );
}
const previewTasks = computed(() =>
  snapshot.value.tasks.map((task) => ({ ...task, name: taskName(task) })),
);
const taskOptions = computed(() => [
  ...new Map(
    snapshot.value.tasks.map((t) => [
      t.config.cameraId,
      { label: cameraName(t), value: t.config.cameraId },
    ]),
  ).values(),
]);
function selectPreviewCamera(value: unknown) {
  const tasks = snapshot.value.tasks.filter(
    (t) => t.config.cameraId === Number(value),
  );
  selected.value = (
    tasks.find((t) => t.enabled && t.status.status === 'RUNNING') ?? tasks[0]
  )?.config.taskId;
}
const selectedTask = computed(() =>
  snapshot.value.tasks.find((t) => t.config.taskId === selected.value),
);
const runningCount = computed(
  () =>
    snapshot.value.tasks.filter((t) => t.status.status === 'RUNNING').length,
);
const stoppedCount = computed(
  () => snapshot.value.tasks.filter((t) => !t.enabled).length,
);
const tableHeight = computed(() =>
  Math.min(420, Math.max(132, snapshot.value.tasks.length * 68 + 58)),
);
const previewState = computed(() => {
  if (error.value) return 'offline';
  if (!hasSnapshot.value) return 'loading';
  if (!selectedTask.value) return 'empty';
  if (
    snapshot.value.tasks.some(
      (t) =>
        t.config.cameraId === selectedTask.value?.config.cameraId &&
        t.enabled &&
        t.status.status === 'RUNNING',
    )
  )
    return 'live';
  if (!selectedTask.value.enabled) return 'stopped';
  if (selectedTask.value.status.status !== 'RUNNING') return 'recovering';
  return 'live';
});
const previewMessages = computed(() => ({
  offline: [
    $t('ai-video-gateway.previewOffline'),
    $t('ai-video-gateway.previewOfflineHint'),
  ],
  loading: [
    $t('ai-video-gateway.previewLoading'),
    $t('ai-video-gateway.previewLoadingHint'),
  ],
  empty: [
    $t('ai-video-gateway.previewEmpty'),
    $t('ai-video-gateway.previewEmptyHint'),
  ],
  stopped: [
    $t('ai-video-gateway.previewStopped'),
    $t('ai-video-gateway.previewStoppedHint'),
  ],
  recovering: [
    $t('ai-video-gateway.previewRecovering'),
    selectedTask.value?.status.errorMessage ||
      $t('ai-video-gateway.previewRecoveringHint'),
  ],
  waiting: [
    $t('ai-video-gateway.previewWaiting'),
    $t('ai-video-gateway.previewWaitingHint'),
  ],
  live: ['', ''],
}));
function selectTask(task: GatewayTask) {
  selected.value = task.config.taskId;
  previewPanel.value?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function taskModelSummary(task: GatewayTask) {
  return gatewayModelRoles(task.config)
    .map((role) => {
      const id = gatewayRoleModelId(task.config, role.slot);
      return `${role.name}：${id ? modelName(id) : '未绑定'}`;
    })
    .join('；');
}
function taskModelLabel(task: GatewayTask) {
  const roles = gatewayModelRoles(task.config);
  return roles.length > 1
    ? `${roles.length} 个模型 · ${roles.map((role) => role.name.replace(/模型$/, '')).join(' / ')}`
    : modelName(task.config.modelVersionId);
}
const statusLabels: Record<string, string> = {
  RUNNING: $t('ai-video-gateway.m5942497005'),
  STOPPED: $t('ai-video-gateway.m75dddf524e'),
  FAILED: $t('ai-video-gateway.m0d6f3ca3f8'),
  OFFLINE: $t('ai-video-gateway.m211357d22f'),
};
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

const [TaskGrid, taskGrid] = useVbenVxeGrid<GatewayTask>({
  gridOptions: {
    columns: [
      {
        field: 'name',
        title: $t('ai-video-gateway.taskAndCamera'),
        minWidth: 260,
        fixed: 'left',
        slots: { default: 'task' },
      },
      {
        field: 'config.algorithmId',
        title: '识别算法 / 模型',
        minWidth: 240,
        slots: { default: 'model' },
      },
      {
        field: 'status.status',
        title: $t('ai-video-gateway.mdce7fbef3c'),
        width: 130,
        slots: { default: 'status' },
      },
      {
        field: 'config.parameters.confidence',
        title: $t('ai-video-gateway.recognitionParameters'),
        minWidth: 180,
        slots: { default: 'parameters' },
      },
      {
        field: 'operation',
        title: $t('ai-video-gateway.mf3ea6d345e'),
        width: 310,
        fixed: 'right',
        slots: { default: 'operation' },
      },
    ],
    data: [],
    height: 'auto',
    rowConfig: { height: 68 },
    pagerConfig: { enabled: false },
    toolbarConfig: { refresh: false },
  },
});
const [EventGrid, eventGrid] = useVbenVxeGrid<GatewayEvent>({
  gridOptions: {
    columns: [
      {
        field: 'payload.occurredTime',
        title: $t('ai-video-gateway.m51f85a78ca'),
        minWidth: 190,
        formatter: ({ cellValue }: { cellValue: number }) =>
          cellValue ? new Date(cellValue).toLocaleString() : '—',
      },
      {
        field: 'payload.eventType',
        title: $t('ai-video-gateway.m5b2d75aa54'),
        minWidth: 170,
        formatter: ({ cellValue }: { cellValue: unknown }) =>
          eventTypeName(cellValue),
      },
      {
        field: 'payload.objectSnapshot',
        title: $t('ai-video-gateway.recognitionResult'),
        minWidth: 170,
        formatter: ({ row }: { row: GatewayEvent }) =>
          recognitionResult(row.payload.objectSnapshot),
      },
      {
        field: 'payload.taskId',
        title: $t('ai-video-gateway.m3172b317f9'),
        minWidth: 200,
        formatter: ({ row }: { row: GatewayEvent }) => eventTaskName(row),
      },
      {
        field: 'delivered',
        title: $t('ai-video-gateway.ma358e3aedd'),
        width: 120,
        formatter: ({ row }: { row: GatewayEvent }) => {
          if (row.localOnly) return $t('ai-video-gateway.mb502dbc708');
          return row.delivered
            ? $t('ai-video-gateway.m76ce8e3d5e')
            : $t('ai-video-gateway.m3d9f3a0516');
        },
      },
      {
        field: 'operation',
        title: $t('ai-video-gateway.m68d4cdfc09'),
        width: 120,
        fixed: 'right',
        slots: { default: 'operation' },
      },
    ],
    height: 390,
    proxyConfig: {
      ajax: {
        query: async ({
          page,
        }: {
          page: { currentPage: number; pageSize: number };
        }) =>
          props.transport('events', {
            page: page.currentPage,
            size: page.pageSize,
          }),
      },
    },
  },
});
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'name',
      label: $t('ai-video-gateway.m2e30469899'),
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'confidence',
      label: $t('ai-video-gateway.mb78c2dc2e2'),
      component: 'InputNumber',
      componentProps: { min: 0.01, max: 1, step: 0.05 },
      rules: 'required',
    },
    {
      fieldName: 'sampleFps',
      label: $t('ai-video-gateway.m733e5b154f'),
      component: 'InputNumber',
      componentProps: {
        min: 0.1,
        max: 10,
        step: 0.1,
        onChange: (value: number) => {
          editingSampleFps.value = Number(value);
        },
      },
      rules: 'required',
    },
    {
      fieldName: 'streamType',
      label: $t('ai-video-gateway.streamType'),
      component: 'Select',
      help: $t('ai-video-gateway.streamSwitchHelp'),
      componentProps: () => ({
        disabled: !canSelectStream.value,
        options: [
          { label: $t('ai-video-gateway.streamSub'), value: 'SUB' },
          { label: $t('ai-video-gateway.streamMain'), value: 'MAIN' },
        ],
      }),
    },
  ],
});
const [AdvancedForm, advancedForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  schema: [
    {
      fieldName: 'sourceUrl',
      label: $t('ai-video-gateway.m94437713c2'),
      component: 'InputPassword',
      componentProps: {
        placeholder: $t('ai-video-gateway.ma568145dbc'),
        autocomplete: 'new-password',
      },
    },
    ...(['MAIN', 'SUB'] as const).map((stream) => ({
      fieldName: stream === 'MAIN' ? 'mainStreamUrl' : 'subStreamUrl',
      label: $t(`ai-video-gateway.stream${stream === 'MAIN' ? 'Main' : 'Sub'}Url`),
      component: 'InputPassword' as const,
      help: $t('ai-video-gateway.streamAddressHelp'),
      dependencies: {
        triggerFields: [],
        show: () => supportsLocalStreams.value,
      },
      componentProps: () => ({
        autocomplete: 'new-password',
        placeholder: $t(
          editing.value?.availableStreamTypes?.includes(stream)
            ? 'ai-video-gateway.streamAddressSaved'
            : 'ai-video-gateway.streamAddressMissing',
        ),
      }),
    })),
  ],
});
const [ModelForm, modelForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [],
});
const [EditModal, editModal] = useVbenModal({
  title: '编辑算法配置',
  class: 'w-[820px]',
  onConfirm: save,
  onClosed: () => {
    editGeneration++;
    editing.value = undefined;
    void advancedForm.resetForm();
  },
});
const [EvidenceModal, evidenceModal] = useVbenModal({
  title: $t('ai-video-gateway.m6e7be762da'),
  class: 'w-[900px]',
  footer: false,
  onClosed: () => {
    evidenceImage.value = '';
    evidenceId.value = '';
    evidenceEvent.value = undefined;
    releaseVideo();
  },
});
const [ModelModal, modelModal] = useVbenModal({
  title: $t('ai-video-gateway.m32a9d23644'),
  class: 'w-[700px]',
  onConfirm: uploadModel,
  onOpenChange(open) {
    if (!open) {
      modelFile.value = undefined;
      modelDisplayName.value = '';
      modelReleaseVersion.value = '';
    }
  },
});
const [PasswordForm, passwordForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1',
  schema: [
    {
      fieldName: 'password',
      label: $t('ai-video-gateway.passwordNew'),
      component: 'InputPassword',
      rules: z.string().min(6, $t('ai-video-gateway.passwordLength')).max(256),
      componentProps: { autocomplete: 'new-password', maxlength: 256 },
    },
    {
      fieldName: 'confirmPassword',
      label: $t('ai-video-gateway.passwordConfirm'),
      component: 'InputPassword',
      rules: 'required',
      componentProps: { autocomplete: 'new-password', maxlength: 256 },
    },
  ],
});
const [PasswordModal, passwordModal] = useVbenModal({
  title: $t('ai-video-gateway.me6d20b5e5b'),
  onConfirm: savePassword,
  onClosed: () => {
    void passwordForm.resetForm();
  },
});

function newRequestId() {
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = ((bytes[6] ?? 0) & 15) | 64;
  bytes[8] = ((bytes[8] ?? 0) & 63) | 128;
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('');
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
    if (!result.tasks.some((t) => t.config.taskId === selected.value))
      selected.value =
        result.tasks.find((t) => t.status.status === 'RUNNING')?.config
          .taskId ?? result.tasks[0]?.config.taskId;
    error.value = '';
  } catch (cause) {
    if (!disposed && generation === refreshGeneration)
      error.value =
        cause instanceof Error
          ? cause.message
          : $t('ai-video-gateway.m04a090194d');
  } finally {
    if (!silent) loading.value = false;
  }
  if (!disposed && activeTab.value === 'events') await eventGrid.query();
}
async function poll() {
  await refresh(hasSnapshot.value);
  if (!disposed) timer = setTimeout(poll, 5000);
}
async function createTask() {
  if (
    props.local &&
    snapshot.value.capabilities?.includes('algorithm.packages.v1')
  ) {
    packageModal.setData({}).open();
    return;
  }
  const model = snapshot.value.models[0];
  if (!model) {
    message.warning($t('ai-video-gateway.m02d425939c'));
    return;
  }
  const id = Date.now();
  await edit({
    name: $t('ai-video-gateway.ma6fac399e4'),
    revision: 0,
    appliedRevision: 0,
    enabled: false,
    config: {
      taskId: id,
      cameraId: id,
      algorithmId: id,
      pipelineVersionId: id,
      runId: newRequestId(),
      configVersion: 1,
      modelVersionId: model.modelVersionId,
      modelBindings: { primary: model.modelVersionId },
      pipeline: {
        schemaVersion: '1.0',
        nodes: [
          { id: 'primary', type: 'DETECTOR', capabilityKey: 'detector.object' },
        ],
        edges: [],
      },
      parameters: {
        schemaVersion: '1.0',
        confidence: 0.5,
        sampleFps: 1,
        temporalN: 2,
        temporalM: 3,
        durationSeconds: 1,
        personConfidence: 0.5,
        ppeConfidence: 0.5,
      },
      rule: null,
    },
    status: { status: 'STOPPED', metrics: {} },
  });
}

async function edit(row: GatewayTask) {
  if (!props.canEdit) return;
  const hideLoading = message.loading('正在读取算法配置…', 0);
  try {
    await openEditor(row);
  } catch (cause) {
    message.error(
      cause instanceof Error ? cause.message : '打开算法配置失败，请重试。',
    );
  } finally {
    hideLoading();
  }
}
async function openEditor(row: GatewayTask) {
  const generation = ++editGeneration;
  if (row.revision > 0) {
    try {
      const current = await props.transport<GatewaySnapshot>('snapshot');
      if (disposed || generation !== editGeneration) return;
      const actual = current.tasks.find(
        (task) => task.config.taskId === row.config.taskId,
      );
      if (!actual) throw new Error('该识别配置已不在网关上，请刷新任务列表。');
      snapshot.value = current;
      row = actual;
    } catch (cause) {
      if (generation === editGeneration)
        message.error(
          cause instanceof Error
            ? cause.message
            : '读取网关配置失败，请确认网关在线后重试。',
        );
      return;
    }
  }
  editError.value = '';
  editTab.value = 'basic';
  editingImage.value = undefined;
  editingImageSize.value = undefined;
  modelCatalog.value = [];
  const [overlay, catalog] = await Promise.allSettled([
    row.revision > 0
      ? props.transport<GatewayOverlay>('overlay', {
          taskId: row.config.taskId,
        })
      : Promise.resolve(undefined),
    !props.local && hasAccessByCodes(['ai-video:model:query'])
      ? getExecutableModelOptions()
      : Promise.resolve([]),
  ]);
  if (disposed || generation !== editGeneration) return;
  if (overlay.status === 'fulfilled') {
    editingImage.value = overlay.value?.imageBase64;
    if (overlay.value?.sourceWidth && overlay.value.sourceHeight)
      editingImageSize.value = {
        width: overlay.value.sourceWidth,
        height: overlay.value.sourceHeight,
      };
  }
  if (catalog.status === 'fulfilled') modelCatalog.value = catalog.value;
  editing.value = JSON.parse(JSON.stringify(row));
  ruleText.value = row.config.rule
    ? JSON.stringify(row.config.rule, null, 2)
    : '';
  editingSampleFps.value = Number(row.config.parameters.sampleFps ?? 1);
  modelForm.setState({
    schema: editingModelRoles.value.map((role, index) => ({
      fieldName: `role_${index}`,
      label: role.name,
      component: 'Select',
      rules: 'required',
      help: !role.declared
        ? '保留已有绑定；变更模型用途请编辑算法配置。'
        : role.modelId && !modelCatalog.value.length
          ? '保留当前模型；切换版本需在平台读取已发布模型目录。'
          : undefined,
      componentProps: () => ({
        options: gatewayRoleModelOptions(
          role,
          row.config,
          snapshot.value,
          modelCatalog.value,
        ),
        optionFilterProp: 'label',
        showSearch: true,
      }),
    })),
  });
  editModal.open();
  await nextTick();
  await Promise.all([
    form.resetForm(),
    modelForm.resetForm(),
    advancedForm.resetForm(),
  ]);
  await form.setValues({
    name: taskName(row),
    confidence: row.config.parameters.confidence ?? 0.5,
    sampleFps: row.config.parameters.sampleFps ?? 1,
    streamType: row.config.parameters.streamType === 'MAIN' ? 'MAIN' : 'SUB',
  });
  await advancedForm.setValues({ sourceUrl: '', mainStreamUrl: '', subStreamUrl: '' });
  await modelForm.setValues(
    Object.fromEntries(
      editingModelRoles.value.map((role, index) => [
        `role_${index}`,
        gatewayRoleModelId(row.config, role.slot),
      ]),
    ),
  );
}
async function save() {
  if (!props.canEdit || !editing.value) return;
  const row = editing.value;
  const [validation, modelValidation, advancedValidation, specific] =
    await Promise.all([
      form.validate(),
      modelForm.validate(),
      advancedForm.validate(),
      algorithmParameters.value?.values(),
    ]);
  if (editing.value !== row || !props.canEdit) return;
  if (!validation.valid || !specific) {
    editTab.value = 'basic';
    return;
  }
  if (!modelValidation.valid || !advancedValidation.valid) {
    editTab.value = 'advanced';
    return;
  }
  if (ruleEditor.value && !ruleEditor.value.validate()) {
    editTab.value = 'rule';
    return;
  }
  editModal.lock();
  editError.value = '';
  try {
    const values = await form.getValues();
    if (editingLatencyBlocked.value && editingLatency.value)
      throw new Error(
        `${confirmationLatencyMessage(editingLatency.value)} 当前配置超过 2 秒目标，不能保存。`,
      );
    const { sourceUrl, mainStreamUrl, subStreamUrl } = await advancedForm.getValues();
    if (row.revision === 0 && !sourceUrl &&
        !(values.streamType === 'MAIN' ? mainStreamUrl : subStreamUrl)) {
      editTab.value = 'advanced';
      throw new Error($t('ai-video-gateway.m9de37d9a00'));
    }
    const { name, streamType, ...parameters } = values;
    const streamTypeChanged =
      !supportsLocalStreams.value &&
      !props.local &&
      row.platformManaged === true &&
      streamType !==
        (row.config.parameters.streamType === 'MAIN' ? 'MAIN' : 'SUB');
    const platformRouting = props.local
      ? {}
      : {
          platformManaged: row.platformManaged,
          streamTypeChanged,
          ...(supportsLocalStreams.value && row.platformManaged &&
          (!row.availableStreamTypes?.includes('MAIN') || !row.availableStreamTypes.includes('SUB'))
            ? { syncStreamUrls: true }
            : {}),
        };
    const streamUrls = supportsLocalStreams.value
      ? {
          ...(mainStreamUrl?.trim() ? { MAIN: mainStreamUrl.trim() } : {}),
          ...(subStreamUrl?.trim() ? { SUB: subStreamUrl.trim() } : {}),
        }
      : {};
    const roleValues = await modelForm.getValues();
    const models = updateGatewayModelBindings(
      row.config,
      Object.fromEntries(
        editingModelRoles.value.map((role, index) => [
          role.slot,
          roleValues[`role_${index}`],
        ]),
      ),
      snapshot.value,
      modelCatalog.value,
    );
    const configuration = {
      ...row.config,
      sourceUrl: sourceUrl || undefined,
      ...(Object.keys(streamUrls).length ? { streamUrls } : {}),
      ...models,
      parameters: mergeGatewayParameters(
        row.config,
        canSelectStream.value
          ? { ...parameters, streamType }
          : parameters,
        specific,
      ),
      ruleId: ruleText.value.trim()
        ? row.config.ruleId || row.config.taskId
        : null,
      ruleVersionId: ruleText.value.trim()
        ? row.config.ruleVersionId || row.config.taskId
        : null,
      rule: ruleText.value.trim() ? JSON.parse(ruleText.value) : null,
    };
    const capacity = await props.transport<GatewayCapacityPreflight>(
      'task.capacity.preflight',
      {
        taskId: row.config.taskId,
        ...platformRouting,
        configuration,
      },
    );
    if (row.enabled) requireGatewayCapacity(capacity);
    const result = await props.transport<GatewayTask>('task.save', {
      taskId: row.config.taskId,
      expectedRevision: row.revision,
      requestId: newRequestId(),
      ...platformRouting,
      name,
      configuration,
    });
    if (capacity.allowed) {
      if (result.appliedRevision === result.revision)
        message.success($t('ai-video-gateway.md68db4afbf'));
      else message.warning($t('ai-video-gateway.ma40f49775b'));
    } else message.warning(`配置已保存但暂不能启动：${capacity.message}`);
    editModal.close();
    await refresh();
  } catch (error) {
    editError.value =
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.m40525a7328');
  } finally {
    editModal.unlock();
  }
}
async function removeLocalTask(row: GatewayTask) {
  try {
    await confirm(
      row.platformManaged === false
        ? '移除此识别配置？历史事件保留。'
        : '仅从当前盒子移除此识别配置？平台中的任务定义和历史事件会保留；如需同时删除平台任务，请在平台“识别算法”页移除。',
    );
  } catch {
    return;
  }
  try {
    await props.transport('task.remove', {
      taskId: row.config.taskId,
      expectedRevision: row.revision,
      requestId: newRequestId(),
    });
    message.success('已从当前盒子移除识别配置');
    await refresh();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '移除失败');
  }
}
async function toggle(row: GatewayTask) {
  if (changingTask.value !== undefined) return;
  if (row.enabled) {
    try {
      await confirm($t('ai-video-gateway.mef8cd7a5a1', { p0: taskName(row) }));
    } catch {
      return;
    }
  }
  changingTask.value = row.config.taskId;
  try {
    if (!row.enabled) {
      const capacity = await props.transport<GatewayCapacityPreflight>(
        'task.capacity.preflight',
        {
          taskId: row.config.taskId,
        },
      );
      requireGatewayCapacity(capacity);
      message.info(`容量预检通过：${gatewayCapacitySummary(capacity)}`);
    }
    await props.transport('task.save', {
      taskId: row.config.taskId,
      expectedRevision: row.revision,
      requestId: newRequestId(),
      enabled: !row.enabled,
    });
    await refresh();
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.m09e424b5e8'),
    );
  } finally {
    changingTask.value = undefined;
  }
}
async function showEvidence(row: GatewayEvent) {
  releaseVideo();
  evidenceImage.value = '';
  evidenceId.value = '';
  evidenceVideo.value = row.hasVideo;
  try {
    if (row.hasSnapshot) {
      const result = await props.transport<{ imageBase64: string }>(
        'event.snapshot',
        { sourceEventId: row.sourceEventId },
      );
      evidenceImage.value = `data:image/jpeg;base64,${result.imageBase64}`;
    }
    evidenceId.value = row.sourceEventId;
    evidenceEvent.value = row;
    evidenceModal.open();
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.m91a531b9f5'),
    );
  }
}
function releaseVideo() {
  videoGeneration++;
  if (videoUrl.value) URL.revokeObjectURL(videoUrl.value);
  videoUrl.value = '';
  videoLoading.value = false;
  videoProgress.value = 0;
}
async function loadVideo() {
  const generation = ++videoGeneration;
  videoLoading.value = true;
  try {
    const chunks: Uint8Array<ArrayBuffer>[] = [];
    let offset = 0;
    while (true) {
      const chunk = await props.transport<{
        base64: string;
        length: number;
        size: number;
      }>('event.video', { sourceEventId: evidenceId.value, offset });
      if (disposed || generation !== videoGeneration) return;
      if (chunk.size > 128 * 1024 * 1024)
        throw new Error($t('ai-video-gateway.mce78e1adc1'));
      const data = Uint8Array.from(
        atob(chunk.base64),
        (c) => c.codePointAt(0) ?? 0,
      );
      chunks.push(data);
      offset += data.length;
      videoProgress.value =
        chunk.size > 0 ? Math.round((offset / chunk.size) * 100) : 100;
      if (offset >= chunk.size) break;
      if (data.length === 0)
        throw new Error($t('ai-video-gateway.mb7c9204893'));
    }
    videoUrl.value = URL.createObjectURL(
      new Blob(chunks, { type: 'video/mp4' }),
    );
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.m3071a94119'),
    );
  } finally {
    if (generation === videoGeneration) videoLoading.value = false;
  }
}

async function uploadModel() {
  if (!modelFile.value) {
    message.warning($t('ai-video-gateway.m3149101981'));
    return;
  }
  if (!modelDisplayName.value.trim() || !modelReleaseVersion.value.trim()) {
    message.warning('请填写模型名称和版本');
    return;
  }
  modelModal.lock();
  try {
    const file = modelFile.value;
    const metadata = JSON.parse(modelManifest.value);
    const raw = JSON.stringify({
      ...metadata,
      displayName: modelDisplayName.value.trim(),
      version: modelReleaseVersion.value.trim(),
      modelVersionId: modelVersion.value,
    });
    const encoded = btoa(
      String.fromCodePoint(...new TextEncoder().encode(raw)),
    );
    const response = await fetch('/gateway-api/models/upload', {
      method: 'POST',
      headers: {
        'X-Model-Manifest': encoded,
        'Content-Type': 'application/octet-stream',
      },
      body: file,
    });
    const result = await response.json();
    if (!response.ok || !result.ok)
      throw new Error(result.message || $t('ai-video-gateway.ma01a8d5393'));
    modelModal.close();
    message.success($t('ai-video-gateway.m3a75859ea2'));
    await refresh();
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.ma23cfbb6b6'),
    );
  } finally {
    modelModal.unlock();
  }
}
async function uninstallLocalModel(model: GatewaySnapshot['models'][number]) {
  try {
    await confirm(
      `卸载模型 #${model.modelVersionId}？当前网关的关联任务再次启动前需重新安装，历史事件保留。`,
    );
  } catch {
    return;
  }
  try {
    await props.transport('model.uninstall', {
      modelVersionId: model.modelVersionId,
      sha256: model.sha256,
      requestId: newRequestId(),
    });
    message.success('模型已卸载');
    await refresh();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '卸载失败');
  }
}
async function savePassword() {
  if (!(await passwordForm.validate()).valid) return;
  const values = await passwordForm.getValues();
  if (values.password !== values.confirmPassword) {
    message.error($t('ai-video-gateway.passwordMismatch'));
    return;
  }
  passwordModal.lock();
  try {
    await props.transport('access.password', { password: values.password });
    passwordModal.close();
    message.success($t('ai-video-gateway.m04665692b2'));
    if (props.local) window.dispatchEvent(new Event('gateway-session-expired'));
  } catch (error) {
    message.error(
      error instanceof Error
        ? error.message
        : $t('ai-video-gateway.mc75bebd720'),
    );
  } finally {
    passwordModal.unlock();
  }
}
onMounted(poll);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
  releaseVideo();
});
</script>

<template>
  <ImageRecognition :transport="transport" :available="!error && hasSnapshot" />
  <Page
    :class="{ 'local-workbench': local }"
    :content-class="local ? 'gateway-content' : undefined"
  >
    <div
      v-if="!section"
      class="gateway-workbench-toolbar mb-4 flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-4"
    >
      <div>
        <h1 v-if="local" class="mb-2 text-xl font-semibold">
          {{ $t('ai-video-gateway.m452a957e11') }}
        </h1>
        <div class="flex flex-wrap items-center gap-3">
          <Tag :color="error ? 'warning' : hasSnapshot ? 'green' : 'default'">
            {{
              error
                ? $t('ai-video-gateway.mcf539eb8da')
                : hasSnapshot
                  ? $t('ai-video-gateway.ma5a0e0ac92')
                  : $t('ai-video-gateway.previewLoading')
            }}
          </Tag>
          <span class="text-sm text-muted-foreground">{{
            local
              ? $t('ai-video-gateway.mc187353cb6')
              : $t('ai-video-gateway.ma52e9475a4')
          }}</span>
          <span
            v-if="hasSnapshot"
            class="border-l pl-3 text-sm text-muted-foreground"
            >{{
              $t('ai-video-gateway.taskSummary', {
                total: snapshot.tasks.length,
                running: runningCount,
                stopped: stoppedCount,
              })
            }}</span
          >
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <Button :loading="loading" @click="refresh()">
          {{ $t('ai-video-gateway.m38108eaa1d') }}
        </Button>
        <Button
          v-if="canEdit"
          :disabled="!!error || !hasSnapshot"
          @click="passwordModal.open()"
        >
          {{ $t('ai-video-gateway.mdc132af861') }}
        </Button>
        <Button
          v-if="
            local &&
            canEdit &&
            snapshot.capabilities?.includes('algorithm.packages.v1')
          "
          @click="packageUpload.open()"
        >
          安装算法包
        </Button>
        <Button
          v-if="canEdit"
          type="primary"
          :disabled="!!error || !hasSnapshot"
          @click="createTask"
        >
          {{ $t('ai-video-gateway.m4a238f3444') }}
        </Button>
      </div>
    </div>
    <Alert v-if="error" class="mb-4" type="error" show-icon :message="error" />
    <Tabs
      v-model:active-key="activeTab"
      :class="{ 'gateway-section': section, 'gateway-workspace-tabs': local }"
    >
      <TabPane
        v-if="!section || section === 'preview'"
        key="tasks"
        :tab="$t('ai-video-gateway.tasksTab', { count: snapshot.tasks.length })"
      >
        <div v-if="!section" :style="{ height: `${tableHeight}px` }">
          <TaskGrid>
            <template #task="{ row }">
              <div class="min-w-0 py-2 text-left">
                <div class="truncate font-medium" :title="taskName(row)">
                  {{ taskName(row) }}
                </div>
                <div
                  class="mt-1 truncate text-xs text-muted-foreground"
                  :title="cameraName(row)"
                >
                  {{ cameraName(row) }}
                </div>
              </div>
            </template>
            <template #model="{ row }">
              <div class="min-w-0 py-2 text-left">
                <div class="truncate font-medium" :title="algorithmName(row)">
                  {{ algorithmName(row) }}
                </div>
                <div
                  class="mt-1 truncate text-xs text-muted-foreground"
                  :title="taskModelSummary(row)"
                >
                  {{ taskModelLabel(row) }}
                </div>
              </div>
            </template>
            <template #status="{ row }">
              <Tag
                :color="
                  row.status.status === 'RUNNING'
                    ? 'green'
                    : row.enabled
                      ? 'orange'
                      : 'default'
                "
              >
                {{ statusLabels[row.status.status] || row.status.status }}
              </Tag>
              <div class="mt-1 text-xs text-muted-foreground">
                {{
                  $t('ai-video-gateway.configVersion', {
                    version: row.revision,
                  })
                }}
                <span
                  v-if="row.appliedRevision !== row.revision"
                  class="text-amber-600"
                  >· {{ $t('ai-video-gateway.m8fddb7fe05') }}</span
                >
              </div>
            </template>
            <template #parameters="{ row }">
              <div class="text-sm">
                {{
                  $t('ai-video-gateway.confidenceValue', {
                    value: percent(row.config.parameters.confidence),
                  })
                }}
              </div>
              <div class="mt-1 text-xs text-muted-foreground">
                {{
                  $t('ai-video-gateway.fpsValue', { value: analysisFps(row) })
                }}
                ·
                {{
                  row.config.parameters.streamType === 'MAIN'
                    ? '主码流'
                    : '子码流'
                }}
              </div>
              <div class="mt-1 text-xs text-muted-foreground">
                {{ captureBackend(row.status.metrics.captureBackend) }}
              </div>
            </template>
            <template #operation="{ row }">
              <TableAction
                :actions="[
                  {
                    label: $t('ai-video-gateway.mf4c3988e2b'),
                    onClick: () => selectTask(row),
                    type: 'link',
                  },
                  {
                    label: $t('image-recognition.title'),
                    ifShow: local || hasAccessByCodes(['ai-video:model:test']),
                    disabled: !!error,
                    onClick: () => recognizeImage(row),
                    type: 'link',
                  },
                  {
                    label: $t('ai-video-gateway.ma7f814c0a4'),
                    ifShow: canEdit,
                    disabled: !!error,
                    onClick: () => edit(row),
                    type: 'link',
                  },
                  {
                    label: '移除',
                    ifShow: local && canEdit,
                    disabled: row.enabled || !!error,
                    onClick: () => removeLocalTask(row),
                    type: 'link',
                  },
                  {
                    label: row.enabled
                      ? $t('ai-video-gateway.ma17f70a8d3')
                      : $t('ai-video-gateway.mebd26da421'),
                    ifShow: canEdit,
                    disabled: !!error || changingTask !== undefined,
                    loading: changingTask === row.config.taskId,
                    onClick: () => toggle(row),
                    type: 'link',
                  },
                ]"
              />
            </template>
            <template #empty>
              <Empty :description="$t('ai-video-gateway.m860304c141')" />
            </template>
          </TaskGrid>
        </div>
        <section
          ref="previewPanel"
          class="mt-5 overflow-hidden rounded-xl border bg-card"
        >
          <div
            class="flex flex-wrap items-center justify-between gap-3 border-b px-5 py-4"
          >
            <div>
              <h3 class="font-medium">
                {{ $t('ai-video-gateway.m105a680e17') }}
              </h3>
              <p class="mt-1 text-xs text-muted-foreground">
                {{
                  selectedTask
                    ? cameraName(selectedTask)
                    : $t('ai-video-gateway.previewSelectHint')
                }}
              </p>
            </div>
            <Select
              v-if="taskOptions.length"
              :value="selectedTask?.config.cameraId"
              :options="taskOptions"
              @change="selectPreviewCamera"
              class="w-full sm:w-72"
              aria-label="选择预览摄像头"
            />
          </div>
          <template v-if="previewState === 'live' && selectedTask">
            <Alert
              v-if="!canPreview"
              class="m-4"
              type="warning"
              message="当前账号没有视频预览权限"
              show-icon
            />
            <GatewayRecognitionPreview
              v-else-if="
                snapshot.capabilities?.includes('preview.webrtc.v1') &&
                activeTab === 'tasks'
              "
              :key="selectedTask.config.cameraId"
              :task="selectedTask"
              :tasks="previewTasks"
              :local="local"
              :title="taskName(selectedTask)"
              :camera-name="cameraName(selectedTask)"
              :transport="transport"
            />
            <Alert
              v-else-if="!snapshot.capabilities?.includes('preview.webrtc.v1')"
              class="m-4"
              type="info"
              message="此网关需在线升级后使用统一实时播放器"
              show-icon
            />
          </template>
          <div
            v-else
            class="flex min-h-[210px] flex-col items-center justify-center bg-muted/30 px-6 py-8 text-center"
            aria-live="polite"
          >
            <div
              class="mb-3 flex h-11 w-11 items-center justify-center rounded-full border bg-card text-muted-foreground"
              aria-hidden="true"
            >
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                stroke-width="1.5"
              >
                <rect x="3" y="5" width="14" height="14" rx="3" />
                <path d="m17 10 4-3v10l-4-3" />
              </svg>
            </div>
            <h4 class="text-base font-medium">
              {{ previewMessages[previewState][0] }}
            </h4>
            <p class="mt-2 max-w-lg text-sm text-muted-foreground">
              {{ previewMessages[previewState][1] }}
            </p>
            <div class="mt-4 flex flex-wrap justify-center gap-2">
              <Button
                v-if="
                  previewState === 'stopped' &&
                  canEdit &&
                  !section &&
                  selectedTask
                "
                type="primary"
                :loading="changingTask === selectedTask.config.taskId"
                :disabled="changingTask !== undefined"
                @click="toggle(selectedTask)"
              >
                {{ $t('ai-video-gateway.startRecognition') }}
              </Button>
              <Button
                v-if="selectedTask && canEdit && !error && !section"
                @click="edit(selectedTask)"
              >
                {{ $t('ai-video-gateway.editConfiguration') }}
              </Button>
              <Button
                v-if="previewState === 'empty' && canEdit"
                type="primary"
                @click="createTask"
              >
                {{ $t('ai-video-gateway.m4a238f3444') }}
              </Button>
              <Button
                v-if="previewState === 'offline'"
                :loading="loading"
                @click="refresh()"
              >
                {{ $t('ai-video-gateway.retryConnection') }}
              </Button>
            </div>
          </div>
        </section>
      </TabPane>
      <TabPane
        v-if="!section || section === 'models'"
        key="models"
        :tab="
          $t('ai-video-gateway.modelsTab', { count: snapshot.models.length })
        "
      >
        <div class="mb-4 flex flex-wrap items-center justify-between gap-3">
          <p class="text-sm text-muted-foreground">
            {{
              $t(
                local
                  ? 'ai-video-gateway.localModelsHint'
                  : 'ai-video-gateway.platformModelsHint',
              )
            }}
          </p>
          <Button
            v-if="local && canEdit"
            type="primary"
            @click="modelModal.open()"
          >
            {{ $t('ai-video-gateway.mab7e444b8b') }}
          </Button>
        </div>
        <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          <article
            v-for="model in snapshot.models"
            :key="model.modelVersionId"
            class="min-w-0 rounded-xl border bg-card p-5"
          >
            <h3
              class="truncate font-medium"
              :title="modelName(model.modelVersionId)"
            >
              {{ modelName(model.modelVersionId) }}
            </h3>
            <p
              class="mt-1 truncate text-xs text-muted-foreground"
              :title="modelVersionLabel(model.modelVersionId)"
            >
              {{ modelVersionLabel(model.modelVersionId) }}
            </p>
            <div class="my-4 flex gap-2">
              <Tag>{{ model.artifactFormat }}</Tag
              ><Tag color="blue">{{ model.device }}</Tag>
            </div>
            <details class="border-t pt-3 text-xs text-muted-foreground">
              <summary class="cursor-pointer">
                {{ $t('ai-video-gateway.modelDetails') }}
              </summary>
              <p class="mt-2">
                {{ $t('ai-video-gateway.modelVersionId') }} #{{
                  model.modelVersionId
                }}
              </p>
              <p class="mt-2 break-all font-mono">SHA256 {{ model.sha256 }}</p>
            </details>
            <Button
              v-if="
                local &&
                canEdit &&
                snapshot.capabilities?.includes('model.uninstall.v1')
              "
              danger
              size="small"
              class="mt-4"
              :disabled="
                !!error ||
                snapshot.tasks.some(
                  (t) =>
                    t.enabled &&
                    (t.config.modelVersionId === model.modelVersionId ||
                      Object.values(t.config.modelBindings).includes(
                        model.modelVersionId,
                      )),
                )
              "
              @click="uninstallLocalModel(model)"
            >
              卸载模型
            </Button>
          </article>
        </div>
        <Empty
          v-if="!snapshot.models.length"
          :description="$t('ai-video-gateway.m93b8b014f3')"
        />
      </TabPane>
      <TabPane
        v-if="!section || section === 'events'"
        key="events"
        :tab="$t('ai-video-gateway.m2a05ddf222')"
      >
        <p class="mb-3 text-muted-foreground">
          {{ $t('ai-video-gateway.m81b89296a4') }} {{ snapshot.historyDays }}
          {{ $t('ai-video-gateway.mb0c65d67bd') }}
        </p>
        <div class="h-[390px]">
          <EventGrid>
            <template #operation="{ row }">
              <Button type="link" @click="showEvidence(row)">
                {{ $t('ai-video-gateway.m4160eecfa4') }}
              </Button>
            </template>
          </EventGrid>
        </div>
      </TabPane>
      <TabPane
        v-if="!section || section === 'delivery'"
        key="delivery"
        :tab="$t('ai-video-delivery.interfaces')"
      >
        <GatewayEventDelivery
          v-if="
            activeTab === 'delivery' &&
            snapshot.capabilities?.includes('event.tcp.v3')
          "
          :transport="transport"
          :snapshot="snapshot"
          :can-edit="canEdit"
        />
        <Empty
          v-else-if="
            hasSnapshot && !snapshot.capabilities?.includes('event.tcp.v3')
          "
          :description="$t('ai-video-delivery.upgradeRequired')"
        />
      </TabPane>
      <TabPane v-if="local && canEdit" key="application-upgrade" :tab="$t('application-upgrade.title')">
        <ApplicationUpgrade v-if="activeTab === 'application-upgrade'" :transport="transport" />
      </TabPane>
    </Tabs>
    <PackageModal
      :transport="transport"
      @success="refresh()"
      @configure-pipeline="configurePipeline"
    />
    <PlateModal
      :transport="transport"
      :snapshot="snapshot"
      @saved="refresh()"
    />
    <PackageUpload>
      <div class="space-y-4 py-1">
        <Alert
          v-if="packageError"
          :message="packageError"
          type="error"
          show-icon
        />
        <Upload.Dragger
          v-model:file-list="packageFileList"
          accept=".zip,application/zip"
          :before-upload="choosePackage"
          :max-count="1"
          :multiple="false"
          @remove="removePackage"
        >
          <p class="font-medium">点击或拖拽算法包到此区域</p>
          <p class="mt-2 text-xs text-muted-foreground">
            仅支持供应方提供的 ZIP，最大 8 MB
          </p>
        </Upload.Dragger>
        <Alert
          message="算法包只包含算法逻辑和配置声明；依赖的模型文件请在“本地模型”中单独安装。"
          type="info"
          show-icon
        />
      </div>
    </PackageUpload>
    <EditModal>
      <Alert
        v-if="editError"
        class="mb-4"
        type="error"
        show-icon
        :message="editError"
      />
      <Alert
        v-if="editingLatency && editingLatencyConflict"
        class="mb-4"
        :type="editingLatencyBlocked ? 'error' : 'info'"
        show-icon
        :message="confirmationLatencyMessage(editingLatency)"
        :description="
          editingLatencyBlocked
            ? '接打电话配置明显超过 2 秒目标，请提高分析帧率或降低规则连续帧/持续时间。'
            : '这是保持兼容的历史配置；可继续运行和修改无关参数，变更规则或帧率时必须满足 2 秒目标。'
        "
      />
      <Tabs v-model:active-key="editTab">
        <TabPane key="basic" tab="识别参数" force-render>
          <div class="mb-3 font-medium">
            {{ editing ? algorithmName(editing) : '' }}
          </div>
          <Form />
          <PackageParameters
            v-if="editing && editingParameterDefinition"
            :key="editing.config.taskId"
            ref="algorithmParameters"
            :manifest="editingParameterDefinition"
            :initial="gatewaySpecificParameters(editing.config)"
            :options="editing.resourceOptions"
            gateway-resources
            :local="local"
            :camera="canPreview ? editingCamera : undefined"
            :preview-transport="editingPreviewTransport"
            :snapshot-image="editingImage"
          />
        </TabPane>
        <TabPane key="rule" tab="告警条件" force-render>
          <Empty
            v-if="editingStatistics"
            description="该算法输出统计结果，无需配置告警条件。"
          />
          <GatewayRuleEditor
            v-else-if="editing"
            :key="editing.config.taskId"
            ref="ruleEditor"
            v-model="ruleText"
            :image="editingImage"
            :image-size="editingImageSize"
            :local="local"
            :task-id="editing.config.taskId"
            :disabled="!canEdit"
            :allow-template-import="
              !local && hasAccessByCodes(['ai-video:rule:query'])
            "
            :camera="canPreview ? editingCamera : undefined"
            :preview-transport="editingPreviewTransport"
            :event-type="
              String(editing.config.rule?.eventType ?? 'ALGORITHM_EVENT')
            "
          />
        </TabPane>
        <TabPane key="advanced" tab="高级设置" force-render>
          <div class="mb-3 font-medium">算法模型</div>
          <ModelForm />
          <AdvancedForm />
          <details v-if="!editingStatistics" class="mt-4">
            <summary class="cursor-pointer">ROI / 规则配置 JSON</summary>
            <label class="my-2 block">{{
              $t('ai-video-gateway.m8df9abf997')
            }}</label>
            <Input.TextArea v-model:value="ruleText" :rows="12" />
          </details>
        </TabPane>
      </Tabs>
      <p v-if="editing?.enabled" class="mt-4 text-xs text-muted-foreground">
        保存后当前识别配置会短暂重启。
      </p>
    </EditModal>
    <EvidenceModal>
      <div v-if="evidenceEvent" class="mb-4 space-y-1">
        <div class="text-lg font-semibold">
          {{ $t('ai-video-gateway.recognitionResult') }}：
          {{ recognitionResult(evidenceEvent.payload.objectSnapshot) }}
        </div>
        <div class="text-sm text-muted-foreground">
          {{ eventTaskName(evidenceEvent) }} ·
          {{ formatTime(evidenceEvent.payload.occurredTime) }}
        </div>
      </div>
      <img
        v-if="evidenceImage"
        :src="evidenceImage"
        :alt="$t('ai-video-gateway.mabcefed669')"
        class="w-full rounded"
      />
      <video
        v-if="local && evidenceVideo && evidenceId"
        :key="evidenceId"
        :src="`/gateway-api/events/${evidenceId}/video`"
        controls
        preload="metadata"
        class="mt-4 w-full"
      ></video>
      <Button
        v-if="!local && evidenceVideo && !videoUrl"
        class="mt-4"
        :loading="videoLoading"
        @click="loadVideo"
      >
        {{ $t('ai-video-gateway.mb91dcca025') }}
        {{ videoLoading ? `${videoProgress}%` : '' }}
      </Button>
      <video
        v-if="videoUrl"
        :src="videoUrl"
        controls
        class="mt-4 w-full"
      ></video>
      <Empty
        v-if="!evidenceImage && !evidenceVideo"
        :description="$t('ai-video-gateway.maa0c31c283')"
      />
    </EvidenceModal>
    <ModelModal>
      <p class="mb-4">{{ $t('ai-video-gateway.mb8dacbb1e5') }}</p>
      <label class="mb-2 block">模型名称</label
      ><Input
        v-model:value="modelDisplayName"
        placeholder="例如：通用人员检测"
      />
      <label class="mb-2 mt-4 block">模型版本</label
      ><Input v-model:value="modelReleaseVersion" placeholder="例如：1.0.0" />
      <label class="mb-2 mt-4 block">{{
        $t('ai-video-gateway.m9119ea7fb0')
      }}</label
      ><InputNumber v-model:value="modelVersion" :min="1" class="!w-full" />
      <label class="mb-2 mt-4 block">{{
        $t('ai-video-gateway.md711ab45e4')
      }}</label
      ><input
        type="file"
        accept=".onnx,.rknn"
        @change="modelFile = ($event.target as HTMLInputElement).files?.[0]"
      />
      <label class="mb-2 mt-4 block">{{
        $t('ai-video-gateway.me69bdf6be6')
      }}</label
      ><Input.TextArea v-model:value="modelManifest" :rows="12" />
    </ModelModal>
    <PasswordModal>
      <p class="mb-3">{{ $t('ai-video-gateway.mf3438e176f') }}</p>
      <PasswordForm />
    </PasswordModal>
  </Page>
</template>

<style scoped>
.local-workbench {
  max-width: 1680px;
  margin-inline: auto;
}
.local-workbench :deep(.gateway-content) {
  padding: 24px 32px;
}
.local-workbench .gateway-workbench-toolbar {
  border: 0;
  border-radius: 0;
  background: transparent;
  padding: 0 0 4px;
  gap: 20px;
}
.gateway-workspace-tabs {
  border: 1px solid hsl(var(--border));
  border-radius: 14px;
  padding: 0 20px 20px;
  background: hsl(var(--card));
}
.gateway-workspace-tabs :deep(> .ant-tabs-nav) {
  margin-bottom: 20px;
}
.gateway-workspace-tabs :deep(> .ant-tabs-nav .ant-tabs-tab) {
  padding-block: 18px;
}
@media (max-width: 700px) {
  .local-workbench :deep(.gateway-content) {
    padding: 20px 12px;
  }
  .gateway-workspace-tabs {
    padding: 0 12px 12px;
  }
}

.gateway-section :deep(> .ant-tabs-nav) {
  display: none;
}
</style>
