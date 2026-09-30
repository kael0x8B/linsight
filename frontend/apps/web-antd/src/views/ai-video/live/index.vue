<script lang="ts" setup>
import type { ComponentPublicInstance } from 'vue';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { EntryStationStatus } from '#/api/ai-video/task/entry-access';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';

import { useFullscreen, useWebSocket } from '@vueuse/core';
import {
  Alert,
  Badge,
  Button,
  message,
  Select,
  Space,
  Spin,
  Switch,
  Tooltip,
} from 'ant-design-vue';

import { getCamera, getCameraPage } from '#/api/ai-video/camera';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { CameraPreviewPlayer } from '#/components/ai-video';
import CameraCapabilities from '#/components/ai-video/camera-capabilities.vue';
import CameraRecognitionOverlay from '#/components/ai-video/camera-recognition-overlay.vue';
import {
  cameraPreviewNode,
  capabilityKey,
  layerColor,
} from '#/components/ai-video/recognition-layers';
import {
  recognitionRegionKey,
  useDisplayPreferences,
} from '#/components/ai-video/use-display-preferences';
import { $t } from '#/locales';

import {
  acceptsTaskFrame,
  describeObject,
  isFreshFrame,
} from './modules/overlay-presentation';

const router = useRouter();

interface PreviewPlayerExpose extends ComponentPublicInstance {
  takeScreenshot: () => void;
  toggleFullscreen: () => Promise<void>;
  toggleMute: () => boolean;
}

interface WebSocketMessage {
  content?: string | unknown;
  type?: string;
}

const route = useRoute();
const accessStore = useAccessStore();
const { hasAccessByCodes } = useAccess();
const canPreview = computed(() =>
  hasAccessByCodes(['ai-video:camera:preview']),
);

const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const cameraLoading = ref(false);
const cameraError = ref('');
const selectedCameraId = ref<number>();
const selectedNodeId = ref<number>();
const displayPrefs = useDisplayPreferences(selectedCameraId);
const session = ref<AiVideoCameraApi.PreviewSession>();
const overlayFrames = ref<Record<string, AiVideoCameraApi.OverlayFrame>>({});
const overlayFrame = computed(() =>
  selectedTask.value
    ? overlayFrames.value[`task-${selectedTask.value.taskId}`]
    : undefined,
);
const showRecognitionRoi = ref(true);
const stageRef = ref<HTMLElement>();
const { isFullscreen, toggle: toggleStageFullscreen } = useFullscreen(stageRef);
async function toggleFullscreen() {
  try {
    await toggleStageFullscreen();
  } catch {
    message.warning('无法进入全屏，请检查浏览器权限后重试。');
  }
}
const muted = ref(true);
const playerRef = ref<PreviewPlayerExpose>();
const selectedTaskId = ref<number | string>();
const entryStatus = ref<EntryStationStatus>();
const showAllObjects = ref(false);
const capabilityError = ref(false);
const capabilityLoading = ref(false);
const now = ref(Date.now());
let capabilityTimer: ReturnType<typeof setInterval> | undefined;
let ageTimer: ReturnType<typeof setInterval> | undefined;
let capabilityRequest = 0;
let disposed = false;

const selectedCamera = computed(() =>
  cameras.value.find((camera) => camera.id === selectedCameraId.value),
);
const capabilities = computed(
  () => selectedCamera.value?.recognitionCapabilities,
);
const continuousCapabilities = computed(() =>
  (capabilities.value ?? []).filter(
    (value): value is AiVideoCameraApi.CameraCapability & { taskId: number } =>
      typeof value.taskId === 'number',
  ),
);
const selectedTask = computed(() =>
  selectedTaskId.value === undefined
    ? undefined
    : continuousCapabilities.value.find(
        (value) => value.taskId === selectedTaskId.value,
      ),
);
const selectedEntry = computed(() =>
  capabilities.value?.find(
    (value) =>
      value.entryAccessId &&
      `entry-${value.entryAccessId}` === selectedTaskId.value,
  ),
);
const nodeCapabilities = capabilities;
const activeCapabilityName = computed(() => '全部算法叠加');
function selectCapability(value: AiVideoCameraApi.CameraCapability) {
  selectedTaskId.value = value.entryAccessId
    ? `entry-${value.entryAccessId}`
    : (value.taskId ?? undefined);
}
const entryDecision = computed(
  () =>
    entryStatus.value?.latestScan?.result?.decision ||
    entryStatus.value?.latestScan?.result?.status ||
    entryStatus.value?.latestScan?.status,
);
const maxResultAgeMs = computed(() =>
  Math.max(15_000, 3000 / (selectedTask.value?.sampleFps || 1)),
);
const resultFresh = computed(
  () =>
    selectedTask.value?.effectiveStatus === 'RUNNING' &&
    isFreshFrame(overlayFrame.value, now.value, maxResultAgeMs.value),
);
const shownObjects = computed(() =>
  resultFresh.value
    ? (overlayFrame.value?.objects ?? []).filter(
        (object) =>
          showAllObjects.value || describeObject(object).visibleByDefault,
      )
    : [],
);
function takeScreenshot() {
  playerRef.value?.takeScreenshot();
}

async function refreshCapabilities() {
  const id = selectedCameraId.value;
  if (!id || capabilityLoading.value) return;
  const request = ++capabilityRequest;
  capabilityLoading.value = true;
  try {
    const camera = await getCamera(id);
    if (request !== capabilityRequest || id !== selectedCameraId.value) return;
    cameras.value = cameras.value.map((value) =>
      value.id === id ? camera : value,
    );
    capabilityError.value = false;
  } catch {
    if (request === capabilityRequest) capabilityError.value = true;
  } finally {
    if (request === capabilityRequest) capabilityLoading.value = false;
  }
}

watch(capabilities, () => {
  if (selectedTask.value || selectedEntry.value) return;
  const first =
    capabilities.value?.find((value) => value.effectiveStatus === 'RUNNING') ??
    capabilities.value?.[0];
  if (first) selectCapability(first);
  else selectedTaskId.value = undefined;
});
watch(
  [
    selectedTaskId,
    () => selectedTask.value?.activeRunId,
    () => selectedTask.value?.effectiveStatus,
  ],
  () => {
    entryStatus.value = undefined;
  },
);
const cameraOptions = computed(() =>
  cameras.value
    .filter(
      (camera): camera is AiVideoCameraApi.Camera & { id: number } =>
        camera.id !== undefined,
    )
    .map((camera) => ({
      disabled: camera.status !== 0,
      label: camera.name,
      value: camera.id,
    })),
);
const nodeOptions = computed(() =>
  nodes.value.map((node) => ({
    disabled:
      node.status !== 0 ||
      node.onlineStatus !== 1 ||
      !node.previewTunnelConnected,
    label: `视频来源：${node.name} · ${
      node.previewTunnelConnected
        ? $t('page.aiVideo.live.previewTunnelReady')
        : $t('page.aiVideo.live.previewTunnelDisconnected')
    }`,
    value: node.id,
  })),
);
const refreshToken = computed(() => accessStore.refreshToken);
const websocketUrl = computed(() => {
  const base = `${import.meta.env.VITE_BASE_URL}/infra/ws`.replace(
    'http',
    'ws',
  );
  return `${base}?token=${refreshToken.value ?? ''}`;
});
const {
  close: closeWebSocket,
  open: openWebSocket,
  status: websocketStatus,
} = useWebSocket(websocketUrl, {
  autoReconnect: { delay: 3000, retries: Number.POSITIVE_INFINITY },
  heartbeat: true,
  onMessage: (_socket, event) => receiveOverlay(event.data),
  immediate: Boolean(refreshToken.value),
});

async function loadCameras() {
  if (!canPreview.value) return;
  cameraLoading.value = true;
  cameraError.value = '';
  try {
    const page = await getCameraPage({ pageNo: 1, pageSize: 50 });
    cameras.value = page.list;
    const queryId = Number(route.query.cameraId);
    let queryCamera = cameras.value.find((camera) => camera.id === queryId);
    if (queryId && !queryCamera) {
      queryCamera = await getCamera(queryId);
      if (queryCamera) cameras.value.unshift(queryCamera);
    }
    selectedCameraId.value =
      queryCamera?.id ??
      cameras.value.find(
        (camera) => camera.onlineStatus === 1 && camera.status === 0,
      )?.id ??
      cameras.value.find((camera) => camera.status === 0)?.id;
  } catch {
    cameraError.value = $t('page.aiVideo.live.cameraLoadFailed');
  } finally {
    cameraLoading.value = false;
  }
}

async function loadNodes() {
  let result: AiVideoNodeSimple[];
  try {
    result = await getNodeSimpleList();
  } catch {
    nodes.value = [];
    selectedNodeId.value = undefined;
    return;
  }
  nodes.value = result;
  const queryNodeId = Number(route.query.nodeId);
  const queryNode = result.find(
    (node) =>
      node.id === queryNodeId &&
      node.onlineStatus === 1 &&
      node.previewTunnelConnected,
  );
  const currentNode = result.find(
    (node) =>
      node.id === selectedNodeId.value &&
      node.onlineStatus === 1 &&
      node.previewTunnelConnected,
  );
  selectedNodeId.value =
    queryNode?.id ??
    currentNode?.id ??
    cameraPreviewNode(selectedCamera.value, result) ??
    result.find(
      (node) =>
        node.status === 0 &&
        node.onlineStatus === 1 &&
        node.previewTunnelConnected,
    )?.id;
}

async function refreshSources() {
  if (websocketStatus.value !== 'OPEN') openWebSocket();
  await Promise.all([loadCameras(), loadNodes()]);
}

function parseOverlayMessage(raw: string) {
  const outer = JSON.parse(raw) as WebSocketMessage;
  if (outer.type !== session.value?.overlayMessageType) return undefined;
  const content =
    typeof outer.content === 'string'
      ? JSON.parse(outer.content)
      : outer.content;
  if (!content || typeof content !== 'object') return undefined;
  const envelope = content as Partial<AiVideoCameraApi.OverlayEnvelope>;
  if (
    envelope.type !== 'preview.overlay.frame' ||
    envelope.version !== '1.0' ||
    !envelope.data
  ) {
    return undefined;
  }
  return envelope as AiVideoCameraApi.OverlayEnvelope;
}

function handleSession(value?: AiVideoCameraApi.PreviewSession) {
  session.value = value;
  if (!value) overlayFrames.value = {};
}

function toggleMute() {
  muted.value = playerRef.value?.toggleMute() ?? muted.value;
}

let searchTimer: ReturnType<typeof setTimeout> | undefined;
let searchGeneration = 0;
function searchCameras(value: string) {
  clearTimeout(searchTimer);
  const generation = ++searchGeneration;
  searchTimer = setTimeout(async () => {
    try {
      const page = await getCameraPage({
        pageNo: 1,
        pageSize: 50,
        name: value || undefined,
      });
      if (generation !== searchGeneration) return;
      const selected = selectedCamera.value;
      cameras.value =
        selected && !page.list.some((camera) => camera.id === selected.id)
          ? [selected, ...page.list]
          : page.list;
    } catch {
      cameraError.value = '摄像头搜索失败，请重试';
    }
  }, 300);
}
onBeforeUnmount(() => {
  clearTimeout(searchTimer);
  searchGeneration++;
});
function receiveOverlay(raw: unknown) {
  if (typeof raw !== 'string' || !raw || !session.value) return;
  try {
    const envelope = parseOverlayMessage(raw);
    if (
      envelope?.data.sessionId === session.value.sessionId &&
      envelope.data.cameraId === selectedCameraId.value
    ) {
      if (
        !acceptsTaskFrame(
          envelope.data,
          continuousCapabilities.value.find(
            (cap) => cap.taskId === envelope.data.taskId,
          ),
          overlayFrames.value[`task-${envelope.data.taskId}`],
        )
      )
        return;
      overlayFrames.value = {
        ...overlayFrames.value,
        [`task-${envelope.data.taskId}`]: envelope.data,
      };
    }
  } catch {
    // Ignore messages from other domains and unsupported schema versions.
  }
}

watch(selectedCameraId, (cameraId) => {
  capabilityRequest += 1;
  capabilityLoading.value = false;
  capabilityError.value = false;
  overlayFrames.value = {};
  session.value = undefined;
  if (!cameraId) return;
  selectedNodeId.value = cameraPreviewNode(
    selectedCamera.value,
    nodes.value,
    selectedNodeId.value,
  );
  void router.replace({
    path: '/ai-video/live',
    query: {
      ...route.query,
      cameraId: String(cameraId),
      ...(selectedNodeId.value ? { nodeId: String(selectedNodeId.value) } : {}),
    },
  });
});

watch(selectedNodeId, (nodeId) => {
  overlayFrames.value = {};
  session.value = undefined;
  if (!nodeId) return;
  void router.replace({
    path: '/ai-video/live',
    query: { ...route.query, nodeId: String(nodeId) },
  });
});

onMounted(async () => {
  await refreshSources();
  if (disposed) return;
  capabilityTimer = setInterval(() => void refreshCapabilities(), 10_000);
  ageTimer = setInterval(() => {
    now.value = Date.now();
  }, 250);
});
onBeforeUnmount(() => {
  disposed = true;
  closeWebSocket();
  capabilityRequest += 1;
  if (capabilityTimer) clearInterval(capabilityTimer);
  if (ageTimer) clearInterval(ageTimer);
});
</script>

<template>
  <Page auto-content-height>
    <Alert
      v-if="!canPreview"
      :message="$t('page.aiVideo.live.noPermission')"
      show-icon
      type="warning"
    />

    <section
      v-else
      class="live-workbench"
      :data-preview-session="session?.sessionId"
      :data-recognition-task="selectedTask?.taskId"
      :data-recognition-run="selectedTask?.activeRunId"
    >
      <header class="live-toolbar">
        <div class="live-toolbar__title">
          <span>摄像头预览</span>
          <h1>
            <template v-if="selectedCamera">
              {{ selectedCamera.name }}
            </template>
            <template v-else>{{ $t('page.aiVideo.live.title') }}</template>
          </h1>
        </div>
        <Select
          v-model:value="selectedCameraId"
          show-search
          :filter-option="false"
          @search="searchCameras"
          :loading="cameraLoading"
          :options="cameraOptions"
          :placeholder="$t('page.aiVideo.live.searchCamera')"
          class="camera-select"
        />
        <Select
          v-model:value="selectedNodeId"
          :options="nodeOptions"
          :placeholder="$t('page.aiVideo.live.selectReadyNode')"
          class="node-select"
        />
        <Space>
          <Badge :status="websocketStatus === 'OPEN' ? 'success' : 'error'" />
          <span class="overlay-status">
            {{
              websocketStatus === 'OPEN' ? '识别结果已连接' : '识别结果重连中'
            }}
          </span>
          <Button :loading="cameraLoading" @click="refreshSources">
            <IconifyIcon icon="lucide:refresh-cw" />
            {{ $t('page.aiVideo.live.refreshCamera') }}
          </Button>
        </Space>
      </header>

      <Alert
        v-if="cameraError"
        :message="cameraError"
        banner
        show-icon
        type="error"
      />
      <Alert
        v-if="!cameraLoading && !selectedNodeId"
        :message="$t('page.aiVideo.live.noReadyNode')"
        banner
        show-icon
        type="warning"
      />

      <div class="live-body">
        <main ref="stageRef" class="preview-stage">
          <div class="stage-toolbar">
            <div class="stage-title">
              <IconifyIcon icon="lucide:scan-eye" /><span>{{
                activeCapabilityName || '识别画面'
              }}</span>
            </div>
            <div class="stage-actions">
              <Tooltip
                :title="
                  showRecognitionRoi
                    ? '隐藏识别标注，识别继续运行'
                    : '显示识别标注'
                "
              >
                <Button
                  type="text"
                  class="stage-tool stage-tool--roi"
                  :class="{ 'is-active': showRecognitionRoi }"
                  :aria-pressed="showRecognitionRoi"
                  aria-label="显示识别标注"
                  @click="showRecognitionRoi = !showRecognitionRoi"
                >
                  <IconifyIcon
                    :icon="
                      showRecognitionRoi ? 'lucide:scan-line' : 'lucide:scan'
                    "
                  /><span>识别标注</span>
                </Button>
              </Tooltip>
              <span class="stage-actions__divider" aria-hidden="true"></span>
              <Tooltip :title="muted ? '取消静音' : '静音'">
                <Button
                  type="text"
                  class="stage-tool stage-tool--icon"
                  :aria-label="muted ? '取消静音' : '静音'"
                  :aria-pressed="!muted"
                  @click="toggleMute"
                >
                  <IconifyIcon
                    :icon="muted ? 'lucide:volume-x' : 'lucide:volume-2'"
                  />
                </Button>
              </Tooltip>
              <Tooltip title="截图">
                <Button
                  type="text"
                  class="stage-tool stage-tool--icon"
                  aria-label="截图"
                  @click="takeScreenshot"
                >
                  <IconifyIcon icon="lucide:camera" />
                </Button>
              </Tooltip>
              <Tooltip :title="isFullscreen ? '退出全屏' : '全屏'">
                <Button
                  type="text"
                  class="stage-tool stage-tool--icon"
                  :aria-label="isFullscreen ? '退出全屏' : '全屏'"
                  @click="toggleFullscreen"
                >
                  <IconifyIcon
                    :icon="isFullscreen ? 'lucide:minimize' : 'lucide:maximize'"
                  />
                </Button>
              </Tooltip>
            </div>
          </div>

          <div class="player-frame">
            <Spin :spinning="cameraLoading" wrapper-class-name="player-spin">
              <CameraPreviewPlayer
                ref="playerRef"
                :camera="selectedCamera"
                :muted="muted"
                :node-id="selectedNodeId"
                :overlay-enabled="false"
                class="analysis-mode"
                @session="handleSession"
              >
                <template #overlay="{ video, clock }">
                  <CameraRecognitionOverlay
                    class="primary-recognition"
                    :camera="selectedCamera"
                    :video="video"
                    :clock="clock"
                    :frames="overlayFrames"
                    :show-all-objects="showAllObjects"
                    :show-overlay="showRecognitionRoi"
                    @entries="
                      (values) =>
                        (entryStatus = selectedEntry?.entryAccessId
                          ? values[`entry-${selectedEntry.entryAccessId}`]
                          : undefined)
                    "
                  />
                </template>
              </CameraPreviewPlayer>
            </Spin>
          </div>
        </main>
        <aside class="recognition-panel">
          <header class="recognition-panel__heading">
            <strong
              >{{ $t('page.aiVideo.recognition.title')
              }}<span class="capability-count">{{
                nodeCapabilities?.length ?? 0
              }}</span></strong
            >
            <Tooltip title="刷新识别能力">
              <Button
                type="text"
                class="panel-refresh"
                :loading="capabilityLoading"
                aria-label="刷新识别能力"
                @click="refreshCapabilities"
              >
                <IconifyIcon icon="lucide:refresh-cw" />
              </Button>
            </Tooltip>
          </header>
          <Alert
            v-if="capabilityError"
            show-icon
            type="error"
            :message="$t('page.aiVideo.recognition.loadFailed')"
          />
          <p class="recognition-panel__hint">
            全部算法同时叠加。开关同步到分屏和平台节点预览；点击卡片仅查看详情，不影响识别与告警。
          </p>
          <div class="capability-list">
            <Alert
              v-if="displayPrefs.error.value"
              :message="displayPrefs.error.value"
              type="warning"
            >
              <template #action>
                <Button size="small" @click="displayPrefs.reload">
                  重试
                </Button>
              </template>
            </Alert>
            <CameraCapabilities
              :capabilities="nodeCapabilities"
              selectable
              :selected-id="selectedTaskId"
              @select="selectCapability"
            >
              <template #actions="{ capability }">
                <div class="layer-visibility" @click.stop @keydown.stop>
                  <span
                    ><i
                      :style="{
                        background: layerColor(capabilityKey(capability)),
                      }"
                    ></i
                    >显示识别标注</span
                  >
                  <Switch
                    size="small"
                    :aria-label="`${capability.algorithmName || capability.taskName}图层`"
                    :checked="
                      !displayPrefs.hidden.value.includes(
                        capabilityKey(capability),
                      )
                    "
                    :disabled="
                      !displayPrefs.ready.value || displayPrefs.saving.value
                    "
                    @change="
                      (value) =>
                        displayPrefs.setVisible(
                          capabilityKey(capability),
                          Boolean(value),
                        )
                    "
                  />
                </div>
                <div class="layer-visibility" @click.stop @keydown.stop>
                  <span :title="$t('rule-canvas.regionDisplayHint')">
                    {{ $t('rule-canvas.showRecognitionRegion') }}
                  </span>
                  <Switch
                    size="small"
                    :aria-label="`${capability.algorithmName || capability.taskName}识别区域`"
                    :checked="
                      !displayPrefs.hidden.value.includes(
                        recognitionRegionKey(capabilityKey(capability)),
                      )
                    "
                    :disabled="
                      !displayPrefs.ready.value || displayPrefs.saving.value
                    "
                    @change="
                      (value) =>
                        displayPrefs.setVisible(
                          recognitionRegionKey(capabilityKey(capability)),
                          Boolean(value),
                        )
                    "
                  />
                </div>
              </template>
            </CameraCapabilities>
          </div>
          <div v-if="!selectedEntry && selectedTask" class="display-options">
            <label class="ai-switch"
              ><span>显示合规与待确认目标</span
              ><Switch v-model:checked="showAllObjects" size="small"
            /></label>
            <p class="recognition-panel__hint">
              仅影响画面显示，不改变告警规则。
            </p>
          </div>
          <section v-if="selectedEntry" class="recognition-results">
            <h3>{{ $t('camera-face.entryState') }}</h3>
            <p>
              {{
                entryStatus
                  ? $t(`entry-access.stationStates.${entryStatus.state}`)
                  : $t('entry-access.queryFailed')
              }}
            </p>
            <p class="recognition-panel__hint">
              {{ $t('camera-face.layerHint') }}
            </p>
            <h3>{{ $t('camera-face.latestVerification') }}</h3>
            <template v-if="entryStatus?.latestScan">
              <p>
                {{
                  entryDecision
                    ? $t(`entry-access.states.${entryDecision}`)
                    : '—'
                }}
              </p>
              <p v-if="entryStatus.latestScan.result?.personName">
                {{ entryStatus.latestScan.result.personName }}
              </p>
              <p class="recognition-panel__hint">
                {{
                  new Date(entryStatus.latestScan.createTime).toLocaleString()
                }}
              </p>
              <p v-if="entryStatus.latestScan.result?.device">
                {{ $t('entry-access.device') }}：{{
                  entryStatus.latestScan.result.device
                }}
              </p>
            </template>
            <p v-else class="recognition-panel__hint">
              {{ $t('camera-face.noVerification') }}
            </p>
          </section>
          <section v-if="!selectedEntry" class="recognition-results">
            <h3>最近一次识别内容</h3>
            <p
              v-if="resultFresh && overlayFrame"
              class="recognition-panel__hint"
            >
              采样时间
              {{
                new Date(overlayFrame.timestamp).toLocaleTimeString()
              }}；目标框与视频同步显示。
            </p>
            <p v-if="!resultFresh" class="recognition-panel__hint">
              {{
                selectedTask
                  ? selectedTask.effectiveStatus === 'RUNNING'
                    ? '等待新的识别结果'
                    : '该能力当前未运行，可在边缘盒子中查看状态并启动识别。'
                  : '选择一项识别能力查看结果。'
              }}
            </p>
            <p v-else-if="!shownObjects.length" class="recognition-panel__hint">
              本次分析未发现已确认的告警目标。被遮挡或待确认的人可能不会显示为违规。
            </p>
            <div
              v-for="(object, index) in shownObjects"
              :key="object.trackId || index"
              class="recognition-result"
            >
              <strong>{{
                describeObject(object).label ??
                (describeObject(object).labelKey
                  ? $t(
                      `page.aiVideo.recognition.${describeObject(object).labelKey}`,
                    )
                  : object.class)
              }}</strong>
              <span>{{
                describeObject(object).confidence === undefined
                  ? '待确认'
                  : `${((describeObject(object).confidence ?? 0) * 100).toFixed(0)}%`
              }}</span>
            </div>
          </section>
        </aside>
      </div>
    </section>
  </Page>
</template>

<style scoped>
.layer-visibility {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding-top: 10px;
  margin-top: 10px;
  font-size: 12px;
  border-top: 1px solid hsl(var(--border));
}

.layer-visibility span {
  display: flex;
  gap: 6px;
  align-items: center;
}

.layer-visibility i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.live-workbench {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 560px;
  overflow: hidden;
  color: hsl(var(--foreground));
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
  box-shadow: var(--ai-shadow-md);
}

.live-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  min-height: 76px;
  padding: 14px 18px;
  border-bottom: 1px solid hsl(var(--border));
}

.live-toolbar__title {
  flex: 1 1 220px;
  min-width: 180px;
}

.live-toolbar__title > span {
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.live-toolbar h1 {
  margin: 3px 0 0;
  font-size: 16px;
  font-weight: 650;
  line-height: 1.5;
}

.camera-select {
  width: min(340px, 27vw);
}

.node-select {
  width: min(240px, 20vw);
}

.overlay-status {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.live-body {
  display: flex;
  flex: 1;
  min-height: 0;
}

.preview-stage {
  display: flex;
  flex: 1;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
  background: #07101f;
}

.stage-toolbar {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  min-height: 60px;
  padding: 10px 16px;
  color: #e2e8f0;
  background: #101b2b;
  border-bottom: 1px solid rgb(148 163 184 / 12%);
}

.stage-title {
  display: flex;
  gap: 9px;
  align-items: center;
  min-width: 0;
  font-size: 13px;
  font-weight: 600;
}

.stage-title > :first-child {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  color: #93c5fd;
}

.stage-title span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.stage-actions {
  display: flex;
  flex-shrink: 0;
  gap: 6px;
  align-items: center;
}

.stage-actions__divider {
  width: 1px;
  height: 20px;
  margin: 0 6px;
  background: rgb(148 163 184 / 24%);
}

.stage-tool.ant-btn {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  justify-content: center;
  height: 36px;
  padding: 0 12px;
  color: #cbd5e1;
  background: transparent;
  border: 1px solid transparent;
  border-radius: 9px;
  box-shadow: none;
}

.stage-tool.ant-btn:hover {
  color: #fff;
  background: rgb(148 163 184 / 14%);
}

.stage-tool.ant-btn:focus-visible {
  outline: 2px solid #93c5fd;
  outline-offset: 2px;
}

.stage-tool--icon.ant-btn {
  width: 36px;
  padding: 0;
}

.stage-tool.ant-btn :deep(svg) {
  width: 18px;
  height: 18px;
}

.stage-tool.is-active.ant-btn {
  color: #bfdbfe;
  background: rgb(59 130 246 / 15%);
  border-color: rgb(96 165 250 / 28%);
}

.preview-stage:fullscreen {
  width: 100vw;
  height: 100dvh;
  min-height: 0;
}

.recognition-panel {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  gap: 14px;
  width: 320px;
  padding: 18px;
  overflow: auto;
  border-left: 1px solid hsl(var(--border));
}

.recognition-panel__heading {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
}

.recognition-panel__heading strong {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 14px;
}

.capability-count {
  padding: 1px 7px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted));
  border-radius: 6px;
}

.panel-refresh {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  padding: 0;
  color: hsl(var(--muted-foreground));
}

.capability-list :deep(.capabilities) {
  gap: 8px;
}

.capability-list :deep(.capability) {
  padding: 12px 14px;
  border-radius: 10px;
}

.capability-list :deep(.capability__detail) {
  margin: 5px 0;
}

.recognition-panel h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
}

.recognition-panel__hint {
  margin: 0;
  font-size: 12px;
  line-height: 1.7;
  color: hsl(var(--muted-foreground));
}

.display-options {
  padding: 12px;
  background: hsl(var(--muted) / 50%);
  border-radius: 10px;
}

.ai-switch {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 6px;
  font-size: 12px;
}

.primary-recognition {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.analysis-mode :deep(.camera-preview-player__statusbar) {
  display: none;
}

.recognition-results {
  display: grid;
  gap: 10px;
  padding: 14px;
  background: hsl(var(--muted) / 35%);
  border: 1px solid hsl(var(--border));
  border-radius: 10px;
}

.recognition-results h3,
.recognition-results p {
  margin: 0;
}

.recognition-result {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  color: #9f1239;
  background: #fff1f2;
  border-radius: 6px;
}

.player-frame {
  flex: 1;
  min-height: 0;
  background: #030711;
}

.player-frame :deep(.player-spin),
.player-frame :deep(.ant-spin-container),
.player-frame :deep(.ant-spin-nested-loading) {
  width: 100%;
  height: 100%;
}

@media (max-width: 1050px) {
  .live-body {
    flex-direction: column;
    overflow: auto;
  }

  .preview-stage {
    flex: none;
    height: min(70vh, 650px);
    min-height: 360px;
  }

  .recognition-panel {
    width: auto;
    overflow: visible;
    border-top: 1px solid hsl(var(--border));
    border-left: 0;
  }

  .capability-list :deep(.capabilities) {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .camera-select,
  .node-select {
    flex: 1 1 230px;
    width: auto;
  }

  .live-toolbar__title {
    flex-basis: 100%;
  }
}

@media (max-width: 600px) {
  .live-workbench {
    height: auto;
    min-height: 0;
  }

  .live-toolbar {
    padding: 14px;
  }

  .stage-toolbar {
    gap: 6px;
    padding: 8px;
  }

  .stage-title {
    max-width: 100px;
  }

  .stage-actions {
    gap: 2px;
  }

  .stage-actions__divider {
    margin: 0 2px;
  }

  .recognition-panel {
    padding: 14px;
  }

  .capability-list :deep(.capabilities) {
    grid-template-columns: 1fr;
  }
}
</style>
