<script lang="ts" setup>
import type { Key } from 'ant-design-vue/es/_util/type';
import type { DataNode } from 'ant-design-vue/es/tree';

import type { ComponentPublicInstance } from 'vue';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { confirm, Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { useAccessStore } from '@vben/stores';

import { useWebSocket } from '@vueuse/core';
import {
  Alert,
  Badge,
  Button,
  Empty,
  Input,
  InputNumber,
  message,
  Radio,
  Select,
  Space,
  Spin,
  Switch,
  Tag,
  Tooltip,
  Tree,
} from 'ant-design-vue';

import {
  activateVideoWallLayout,
  createVideoWallLayout,
  deleteVideoWallLayout,
  getCameraGroupList,
  getCameraPage,
  getVideoWallLayouts,
  updateVideoWallLayout,
} from '#/api/ai-video/camera';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { AiPageHeader, CameraPreviewPlayer } from '#/components/ai-video';
import CameraRecognitionOverlay from '#/components/ai-video/camera-recognition-overlay.vue';
import { cameraPreviewNode } from '#/components/ai-video/recognition-layers';
import { $t } from '#/locales';

import { acceptsTaskFrame } from '../live/modules/overlay-presentation';

const router = useRouter();

type SplitCount = 1 | 4 | 9 | 16;

interface CameraTreeNode extends DataNode {
  camera?: AiVideoCameraApi.Camera;
  children?: CameraTreeNode[];
}

interface WebSocketMessage {
  content?: string | unknown;
  type?: string;
}

const accessStore = useAccessStore();
const { hasAccessByCodes } = useAccess();
const canPreview = computed(() =>
  hasAccessByCodes(['ai-video:camera:preview']),
);

const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const groups = ref<AiVideoCameraApi.CameraGroup[]>([]);
const layouts = ref<AiVideoCameraApi.VideoWallLayout[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const cameraLoading = ref(false);
const layoutLoading = ref(false);
const cameraError = ref('');
const layoutError = ref('');
const cameraKeyword = ref('');
const splitCount = ref<SplitCount>(4);
const cameraIds = ref<Array<null | number>>(
  Array.from({ length: 4 }, () => null),
);
const selectedCell = ref(0);
const previewNodeStorageKey = 'linsight-video-wall-preview-node-id';
const persistedPreviewNodeId =
  typeof window === 'undefined'
    ? 0
    : Number(window.localStorage.getItem(previewNodeStorageKey));
const selectedNodeId = ref<number | undefined>(
  Number.isSafeInteger(persistedPreviewNodeId) && persistedPreviewNodeId > 0
    ? persistedPreviewNodeId
    : undefined,
);
watch(selectedNodeId, (nodeId) => {
  if (typeof window === 'undefined') return;
  if (nodeId) window.localStorage.setItem(previewNodeStorageKey, String(nodeId));
  else window.localStorage.removeItem(previewNodeStorageKey);
});
const directoryCameras = ref<AiVideoCameraApi.Camera[]>([]);
const directoryPage = ref(1);
const directoryTotal = ref(0);
let directoryRequest = 0;
let searchTimer: ReturnType<typeof setTimeout> | undefined;
const overlayEnabled = ref(true);
const patrol = ref(false);
const patrolSeconds = ref(30);
const patrolPage = ref(0);
let patrolTimer: ReturnType<typeof setTimeout> | undefined;
let patrolRequest = 0;
let manualCameraIds: Array<null | number> = [];
async function nextPatrolPage() {
  const request = ++patrolRequest;
  try {
    let pageNo = patrolPage.value + 1;
    let page = await getCameraPage({
      pageNo,
      pageSize: splitCount.value,
      name: cameraKeyword.value || undefined,
      status: 0,
    });
    if (page.list.length === 0 && pageNo > 1) {
      pageNo = 1;
      page = await getCameraPage({
        pageNo,
        pageSize: splitCount.value,
        name: cameraKeyword.value || undefined,
        status: 0,
      });
    }
    if (request !== patrolRequest || !patrol.value || disposed) return;
    cacheCameras(page.list);
    patrolPage.value = pageNo;
    assignCameraIds(
      normalizeCameraIds(
        page.list.map((c) => c.id ?? null),
        splitCount.value,
      ),
    );
  } catch {
    cameraError.value = '轮巡批次加载失败，稍后重试';
  }
  if (request === patrolRequest && patrol.value && !disposed)
    patrolTimer = setTimeout(
      () => void nextPatrolPage(),
      Math.max(10, patrolSeconds.value || 30) * 1000,
    );
}
function togglePatrol() {
  patrol.value = !patrol.value;
  clearTimeout(patrolTimer);
  patrolRequest++;
  if (patrol.value) {
    manualCameraIds = [...cameraIds.value];
    patrolPage.value = 0;
    void nextPatrolPage();
  } else {
    assignCameraIds(normalizeCameraIds(manualCameraIds, splitCount.value));
  }
}

let capabilityTimer: ReturnType<typeof setInterval> | undefined;
let disposed = false;
let refreshingCapabilities = false;
const layoutPanelVisible = ref(false);
const wallGridRef = ref<HTMLElement>();
const cellElements = ref<Array<HTMLElement | undefined>>([]);
const cellMuted = ref<boolean[]>(Array.from({ length: 16 }, () => true));
const sessions = ref<Array<AiVideoCameraApi.PreviewSession | undefined>>([]);
const overlayFrames = ref<Array<Record<string, AiVideoCameraApi.OverlayFrame>>>(
  [],
);

const cameraById = computed(
  () => new Map(cameras.value.map((camera) => [camera.id, camera])),
);
const loadedCount = computed(
  () => cameraIds.value.filter((cameraId) => cameraId !== null).length,
);
const activeLayout = computed(() =>
  layouts.value.find((layout) => layout.active),
);
const layoutSlots = computed(() =>
  Array.from({ length: 15 }, (_, index) => ({
    layout: layouts.value.find((layout) => layout.slotIndex === index + 1),
    slotIndex: index + 1,
  })),
);
const wallCells = computed(() =>
  cameraIds.value.map((cameraId, index) => {
    const camera =
      cameraId === null ? undefined : cameraById.value.get(cameraId);

    return {
      camera,
      cameraId,
      nodeId: cameraPreviewNode(camera, nodes.value, selectedNodeId.value),
      index,
    };
  }),
);
const previewNodeOptions = computed(() =>
  nodes.value
    .filter(
      (node) =>
        node.status === 0 &&
        node.onlineStatus === 1 &&
        node.previewTunnelConnected,
    )
    .map((node) => ({ label: node.name, value: node.id })),
);
const gridStyle = computed<Record<string, string>>(() => ({
  '--wall-columns': String(Math.sqrt(splitCount.value)),
}));

const treeData = computed<CameraTreeNode[]>(() => {
  const visibleCameras = directoryCameras.value;
  const grouped = new Map<number, AiVideoCameraApi.Camera[]>();
  for (const camera of visibleCameras) {
    const values = grouped.get(camera.groupId) ?? [];
    values.push(camera);
    grouped.set(camera.groupId, values);
  }
  const groupNodes = groups.value
    .map((group) => {
      const children = (grouped.get(group.id ?? 0) ?? []).map((camera) =>
        toCameraNode(camera),
      );
      return {
        children,
        key: `group:${group.id}`,
        selectable: false,
        title: `${group.name} (${children.length})`,
      } satisfies CameraTreeNode;
    })
    .filter((node) => node.children.length > 0);
  const ungrouped = (grouped.get(0) ?? []).map((camera) =>
    toCameraNode(camera),
  );
  if (ungrouped.length > 0) {
    groupNodes.unshift({
      children: ungrouped,
      key: 'group:0',
      selectable: false,
      title: `${$t('page.aiVideo.wall.ungrouped')} (${ungrouped.length})`,
    });
  }
  return groupNodes;
});

const refreshToken = computed(() => accessStore.refreshToken);
const websocketUrl = computed(() => {
  const base = `${import.meta.env.VITE_BASE_URL}/infra/ws`.replace(
    'http',
    'ws',
  );
  return `${base}?token=${refreshToken.value ?? ''}`;
});
const { close: closeWebSocket } = useWebSocket(websocketUrl, {
  autoReconnect: { delay: 3000, retries: Number.POSITIVE_INFINITY },
  heartbeat: true,
  onMessage: (_socket, event) => receiveOverlay(event.data),
  immediate: Boolean(refreshToken.value),
});

function toCameraNode(camera: AiVideoCameraApi.Camera): CameraTreeNode {
  return {
    camera,
    disabled: camera.status !== 0,
    isLeaf: true,
    key: `camera:${camera.id}`,
    title: `[${camera.protocol}] ${camera.name}`,
  };
}

function cacheCameras(values: AiVideoCameraApi.Camera[]) {
  const map = new Map(cameras.value.map((camera) => [camera.id, camera]));
  values.forEach((camera) => map.set(camera.id, camera));
  cameras.value = [...map.values()];
}
async function loadDirectory(more = false) {
  const request = ++directoryRequest;
  cameraLoading.value = true;
  cameraError.value = '';
  const pageNo = more ? directoryPage.value + 1 : 1;
  try {
    const page = await getCameraPage({
      pageNo,
      pageSize: 50,
      name: cameraKeyword.value || undefined,
    });
    if (request !== directoryRequest) return;
    directoryCameras.value = more
      ? [...directoryCameras.value, ...page.list]
      : page.list;
    directoryTotal.value = page.total;
    directoryPage.value = pageNo;
    cacheCameras(page.list);
  } catch {
    if (request === directoryRequest)
      cameraError.value = $t('page.aiVideo.live.cameraLoadFailed');
  } finally {
    if (request === directoryRequest) cameraLoading.value = false;
  }
}
async function refreshVisibleCameras() {
  const ids = cameraIds.value.filter((id): id is number => id !== null);
  if (ids.length === 0) return;
  const page = await getCameraPage({ pageNo: 1, pageSize: 16, ids });
  if (!disposed) cacheCameras(page.list);
}
async function loadCamerasAndGroups() {
  await Promise.all([
    loadDirectory(),
    getCameraGroupList()
      .then((value) => (groups.value = value))
      .catch(() => {
        cameraError.value = '摄像头分组读取失败';
      }),
  ]);
}
watch(cameraKeyword, () => {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(() => void loadDirectory(), 300);
});
async function loadNodes() {
  try {
    nodes.value = await getNodeSimpleList();
  } catch {
    nodes.value = [];
    selectedNodeId.value = undefined;
    return;
  }
  const current = nodes.value.find(
    (node) =>
      node.id === selectedNodeId.value &&
      node.onlineStatus === 1 &&
      node.previewTunnelConnected,
  );
  selectedNodeId.value =
    current?.id ??
    nodes.value.find(
      (node) =>
        node.status === 0 &&
        node.onlineStatus === 1 &&
        node.previewTunnelConnected,
    )?.id;
}

async function loadLayouts(restoreActive = false) {
  layoutLoading.value = true;
  layoutError.value = '';
  try {
    layouts.value = await getVideoWallLayouts();
    if (restoreActive) {
      const active = layouts.value.find((layout) => layout.active);
      if (active) applyLayout(active);
    }
  } catch {
    layoutError.value = $t('page.aiVideo.wall.layoutLoadFailed');
  } finally {
    layoutLoading.value = false;
  }
}

function normalizeCameraIds(values: Array<null | number>, count: SplitCount) {
  return Array.from({ length: count }, (_, index) => values[index] ?? null);
}

function assignCameraIds(next: Array<null | number>) {
  const previous = cameraIds.value;
  sessions.value = next.map((id, index) =>
    id !== null && id === previous[index] ? sessions.value[index] : undefined,
  );
  overlayFrames.value = next.map((id, index) =>
    id !== null && id === previous[index]
      ? (overlayFrames.value[index] ?? {})
      : {},
  );
  cameraIds.value = next;
}

function changeSplit(count: SplitCount) {
  if (patrol.value) togglePatrol();
  splitCount.value = count;
  assignCameraIds(normalizeCameraIds(cameraIds.value, count));
  selectedCell.value = Math.min(selectedCell.value, count - 1);
}

function addCamera(camera: AiVideoCameraApi.Camera) {
  if (!camera.id || camera.status !== 0) return;
  const existingIndex = cameraIds.value.indexOf(camera.id);
  if (existingIndex !== -1) {
    selectedCell.value = existingIndex;
    message.info($t('page.aiVideo.wall.cameraAlreadyAdded'));
    return;
  }
  const target =
    cameraIds.value[selectedCell.value] === null
      ? selectedCell.value
      : cameraIds.value.indexOf(null);
  if (target < 0) {
    message.warning($t('page.aiVideo.wall.noEmptyChannel'));
    return;
  }
  cameraIds.value[target] = camera.id;
  selectedCell.value = target;
}

function handleTreeSelect(keys: Key[], info: { node: CameraTreeNode }) {
  if (keys.length > 0 && info.node.camera) addCamera(info.node.camera);
}

function handleDragStart(event: DragEvent, camera: AiVideoCameraApi.Camera) {
  if (!camera.id || !event.dataTransfer) return;
  event.dataTransfer.effectAllowed = 'copy';
  event.dataTransfer.setData('text/plain', String(camera.id));
}

function handleDrop(event: DragEvent, index: number) {
  const cameraId = Number(event.dataTransfer?.getData('text/plain'));
  const camera = cameraById.value.get(cameraId);
  if (!camera) return;
  selectedCell.value = index;
  addCamera(camera);
}

function clearCell(index: number) {
  cameraIds.value[index] = null;
  sessions.value[index] = undefined;
  overlayFrames.value[index] = {};
}

function clearAll() {
  cameraIds.value = Array.from({ length: splitCount.value }, () => null);
  sessions.value = [];
  overlayFrames.value = [];
}

function handleSession(index: number, value?: AiVideoCameraApi.PreviewSession) {
  sessions.value[index] = value;
  if (!value) overlayFrames.value[index] = {};
}

function parseOverlayMessage(raw: string) {
  const outer = JSON.parse(raw) as WebSocketMessage;
  if (outer.type !== 'ai-video-preview-overlay') return undefined;
  const content =
    typeof outer.content === 'string'
      ? JSON.parse(outer.content)
      : outer.content;
  if (!content || typeof content !== 'object') return undefined;
  const envelope = content as Partial<AiVideoCameraApi.OverlayEnvelope>;
  return envelope.type === 'preview.overlay.frame' &&
    envelope.version === '1.0' &&
    envelope.data
    ? (envelope as AiVideoCameraApi.OverlayEnvelope)
    : undefined;
}

function receiveOverlay(raw: unknown) {
  if (typeof raw !== 'string' || !raw) return;
  try {
    const envelope = parseOverlayMessage(raw);
    if (!envelope) return;
    sessions.value.forEach((session, index) => {
      const cell = wallCells.value[index];
      if (
        session?.sessionId === envelope.data.sessionId &&
        cell?.cameraId === envelope.data.cameraId &&
        acceptsTaskFrame(
          envelope.data,
          cell.camera?.recognitionCapabilities?.find(
            (cap) => cap.taskId === envelope.data.taskId,
          ),
          overlayFrames.value[index]?.[`task-${envelope.data.taskId}`],
        )
      ) {
        overlayFrames.value[index] = {
          ...overlayFrames.value[index],
          [`task-${envelope.data.taskId}`]: envelope.data,
        };
      }
    });
  } catch {
    // Ignore other WebSocket domains and unsupported versions.
  }
}

function applyLayout(layout: AiVideoCameraApi.VideoWallLayout) {
  changeSplit(layout.splitCount);
  assignCameraIds(normalizeCameraIds(layout.cameraIds, layout.splitCount));
  void refreshVisibleCameras().catch(() => {
    cameraError.value = '方案中的摄像头加载失败，请刷新';
  });
  const layoutNode = nodes.value.find(
    (node) =>
      node.id === layout.nodeId &&
      node.status === 0 &&
      node.onlineStatus === 1 &&
      node.previewTunnelConnected,
  );
  selectedNodeId.value = layoutNode?.id ?? selectedNodeId.value;
}

async function activateLayout(layout: AiVideoCameraApi.VideoWallLayout) {
  applyLayout(layout);
  await activateVideoWallLayout(layout.id);
  layouts.value = layouts.value.map((item) => ({
    ...item,
    active: item.id === layout.id,
  }));
  message.success($t('page.aiVideo.wall.layoutActivated', [layout.name]));
}

async function saveLayout(slotIndex: number) {
  if (patrol.value) {
    message.info('请先停止轮巡，再保存固定布局');
    return;
  }
  const existing = layouts.value.find(
    (layout) => layout.slotIndex === slotIndex,
  );
  const payload: AiVideoCameraApi.VideoWallLayoutSave = {
    cameraIds: [...cameraIds.value],
    id: existing?.id,
    name:
      existing?.name ?? $t('page.aiVideo.wall.defaultLayoutName', [slotIndex]),

    slotIndex,
    splitCount: splitCount.value,
  };
  if (existing) {
    await confirm($t('page.aiVideo.wall.confirmOverwrite', [existing.name]));
    await updateVideoWallLayout(payload);
  } else {
    await createVideoWallLayout(payload);
  }
  await loadLayouts();
  const saved = layouts.value.find((layout) => layout.slotIndex === slotIndex);
  if (saved) await activateLayout(saved);
  message.success($t('page.aiVideo.wall.layoutSaved'));
}

async function removeLayout(layout: AiVideoCameraApi.VideoWallLayout) {
  await confirm($t('page.aiVideo.wall.confirmDeleteLayout', [layout.name]));
  await deleteVideoWallLayout(layout.id);
  await loadLayouts();
  message.success($t('page.aiVideo.wall.layoutDeleted'));
}

async function fullscreenWall() {
  if (!wallGridRef.value) return;
  await (document.fullscreenElement
    ? document.exitFullscreen()
    : wallGridRef.value.requestFullscreen());
}

function fullscreenCell(index: number) {
  const element = cellElements.value[index];
  if (element) void element.requestFullscreen();
}

function setCellElement(
  index: number,
  element: ComponentPublicInstance | Element | null,
) {
  cellElements.value[index] =
    element instanceof HTMLElement ? element : undefined;
}

onMounted(async () => {
  if (!canPreview.value) return;
  await Promise.all([loadCamerasAndGroups(), loadNodes()]);
  await loadLayouts(true);
  if (!disposed)
    capabilityTimer = setInterval(async () => {
      if (refreshingCapabilities) return;
      refreshingCapabilities = true;
      try {
        await refreshVisibleCameras();
      } catch {
        /* Keep the last state; expired frames are hidden independently. */
      } finally {
        refreshingCapabilities = false;
      }
    }, 10_000);
});
onBeforeUnmount(() => {
  disposed = true;
  patrolRequest++;
  clearTimeout(patrolTimer);
  closeWebSocket();
  clearTimeout(searchTimer);
  if (capabilityTimer) clearInterval(capabilityTimer);
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

    <div v-else class="wall-page">
      <AiPageHeader
        icon="lucide:layout-grid"
        :title="$t('page.aiVideo.wall.title')"
      >
        <template #extra>
          <Space>
            <Badge status="processing" />
            <span class="loaded-copy">
              {{ $t('page.aiVideo.wall.loaded', [loadedCount, splitCount]) }}
            </span>
            <Button :loading="cameraLoading" @click="loadCamerasAndGroups">
              <IconifyIcon icon="lucide:refresh-cw" />
              {{ $t('page.aiVideo.live.refreshCamera') }}
            </Button>
          </Space>
        </template>
      </AiPageHeader>

      <Alert
        v-if="cameraError"
        :message="cameraError"
        banner
        closable
        show-icon
        type="error"
      />
      <Alert
        v-if="layoutError"
        :message="layoutError"
        banner
        closable
        show-icon
        type="warning"
      />

      <div class="wall-workspace">
        <aside class="device-panel">
          <div class="device-panel__title">
            <span
              ><IconifyIcon icon="lucide:folder" />{{
                $t('page.aiVideo.wall.deviceDirectory')
              }}</span
            >
            <span>{{ directoryTotal }}</span>
          </div>
          <Input
            v-model:value="cameraKeyword"
            allow-clear
            :placeholder="$t('page.aiVideo.live.searchCamera')"
          >
            <template #prefix><IconifyIcon icon="lucide:search" /></template>
          </Input>
          <Spin :spinning="cameraLoading">
            <Tree
              v-if="treeData.length"
              block-node
              default-expand-all
              :tree-data="treeData"
              @select="handleTreeSelect"
            >
              <template #title="{ camera, title }">
                <span
                  v-if="camera"
                  class="camera-tree-node"
                  draggable="true"
                  @dragstart="handleDragStart($event, camera)"
                >
                  <IconifyIcon icon="lucide:video" />
                  <span>{{ title }}</span>
                  <Badge
                    :status="
                      camera.onlineStatus === 1
                        ? 'success'
                        : camera.onlineStatus === 2
                          ? 'error'
                          : 'default'
                    "
                  />
                </span>
                <span v-else>{{ title }}</span>
              </template>
            </Tree>
            <Empty
              v-else-if="!cameraLoading"
              :description="$t('page.aiVideo.live.noCamera')"
            />
          </Spin>
          <Button
            v-if="directoryCameras.length < directoryTotal"
            :loading="cameraLoading"
            @click="loadDirectory(true)"
          >
            加载更多（{{ directoryCameras.length }}/{{ directoryTotal }}）
          </Button>
          <p class="device-hint">
            目录按名称搜索；轮巡按当前搜索结果分批播放，每批最多 16
            路，停止后恢复原布局。
          </p>
        </aside>

        <section class="wall-main">
          <div class="wall-controls">
            <div class="wall-toolbar">
              <Radio.Group
                :value="splitCount"
                button-style="solid"
                @change="changeSplit($event.target.value)"
              >
                <Radio.Button :value="1">
                  1{{ $t('page.aiVideo.wall.split') }}
                </Radio.Button>
                <Radio.Button :value="4">
                  4{{ $t('page.aiVideo.wall.split') }}
                </Radio.Button>
                <Radio.Button :value="9">
                  9{{ $t('page.aiVideo.wall.split') }}
                </Radio.Button>
                <Radio.Button :value="16">
                  16{{ $t('page.aiVideo.wall.split') }}
                </Radio.Button>
              </Radio.Group>
              <Tag color="blue">自动视频来源 · 全算法叠加</Tag>
              <label class="toolbar-switch">
                无任务摄像头预览节点
                <Select
                  v-model:value="selectedNodeId"
                  :options="previewNodeOptions"
                  aria-label="无任务摄像头预览节点"
                  style="min-width: 180px"
                />
              </label>
              <Button
                :type="patrol ? 'primary' : 'default'"
                @click="togglePatrol"
              >
                {{ patrol ? '停止轮巡' : '开始轮巡' }}
              </Button>
              <label class="toolbar-switch"
                ><InputNumber
                  v-model:value="patrolSeconds"
                  :min="10"
                  :max="600"
                  size="small"
                  style="width: 66px"
                  aria-label="轮巡间隔秒数"
                />秒 / 批</label
              >
              <Tag v-if="patrol">第 {{ patrolPage }} 批</Tag>
              <Button
                :type="layoutPanelVisible ? 'primary' : 'default'"
                @click="layoutPanelVisible = !layoutPanelVisible"
              >
                <IconifyIcon icon="lucide:panels-top-left" />
                {{ $t('page.aiVideo.wall.layoutPlans') }}
                <Tag v-if="activeLayout" color="blue">
                  {{ activeLayout.name }}
                </Tag>
              </Button>
              <label class="toolbar-switch">
                <Switch v-model:checked="overlayEnabled" />
                识别标注
              </label>
              <span class="toolbar-separator"></span>
              <Button type="primary" @click="fullscreenWall">
                <IconifyIcon icon="lucide:maximize" />
                {{ $t('page.aiVideo.wall.fullscreen') }}
              </Button>
              <Button @click="clearAll">
                {{ $t('page.aiVideo.wall.clearAll') }}
              </Button>
              <span class="toolbar-loaded">
                {{ $t('page.aiVideo.wall.loaded', [loadedCount, splitCount]) }}
              </span>
            </div>

            <div v-if="layoutPanelVisible" class="layout-panel">
              <div class="layout-panel__header">
                <div>
                  <strong
                    ><IconifyIcon icon="lucide:grid-2x2" />{{
                      $t('page.aiVideo.wall.layoutPlans')
                    }}</strong
                  >
                  <span>{{ $t('page.aiVideo.wall.layoutPlanHint') }}</span>
                </div>
                <Button
                  aria-label="close"
                  shape="circle"
                  type="text"
                  @click="layoutPanelVisible = false"
                >
                  <IconifyIcon icon="lucide:x" />
                </Button>
              </div>
              <Spin :spinning="layoutLoading">
                <div class="layout-cards">
                  <article
                    v-for="slot in layoutSlots"
                    :key="slot.slotIndex"
                    class="layout-card"
                    :class="{
                      active: slot.layout?.active,
                      empty: !slot.layout,
                    }"
                  >
                    <template v-if="slot.layout">
                      <div class="layout-card__title">
                        <IconifyIcon icon="lucide:grid-2x2" />
                        <strong>{{ slot.layout.name }}</strong>
                        <Tag v-if="slot.layout.active" color="blue">
                          {{ $t('page.aiVideo.wall.inUse') }}
                        </Tag>
                      </div>
                      <p>
                        {{ slot.layout.splitCount
                        }}{{ $t('page.aiVideo.wall.split') }} ·
                        {{ slot.layout.cameraIds.filter(Boolean).length
                        }}{{ $t('page.aiVideo.wall.channels') }}
                      </p>
                      <div class="layout-card__actions">
                        <Button
                          size="small"
                          @click="activateLayout(slot.layout)"
                        >
                          {{ $t('page.aiVideo.wall.switch') }}
                        </Button>
                        <Button
                          size="small"
                          @click="saveLayout(slot.slotIndex)"
                        >
                          {{ $t('page.aiVideo.wall.overwrite') }}
                        </Button>
                        <Button
                          danger
                          size="small"
                          @click="removeLayout(slot.layout)"
                        >
                          {{ $t('page.action.delete') }}
                        </Button>
                      </div>
                    </template>
                    <template v-else>
                      <div class="layout-card__title">
                        <IconifyIcon icon="lucide:grid-2x2" />
                        <strong>{{
                          $t('page.aiVideo.wall.defaultLayoutName', [
                            slot.slotIndex,
                          ])
                        }}</strong>
                      </div>
                      <button
                        type="button"
                        class="save-empty"
                        @click="saveLayout(slot.slotIndex)"
                      >
                        {{ $t('page.aiVideo.wall.saveCurrent') }}
                      </button>
                    </template>
                  </article>
                </div>
              </Spin>
            </div>
          </div>

          <div ref="wallGridRef" class="wall-grid" :style="gridStyle">
            <article
              v-for="cell in wallCells"
              :key="`${cell.index}:${cell.cameraId ?? 'empty'}`"
              :ref="(element) => setCellElement(cell.index, element)"
              class="wall-cell"
              :class="{ selected: selectedCell === cell.index }"
              @click="selectedCell = cell.index"
              @dragover.prevent
              @drop.prevent="handleDrop($event, cell.index)"
            >
              <template v-if="cell.camera">
                <CameraPreviewPlayer
                  compact
                  :camera="cell.camera"
                  :muted="cellMuted[cell.index]"
                  :node-id="cell.nodeId"
                  :overlay-enabled="false"
                  :class="{ 'analysis-mode': overlayEnabled }"
                  @session="(value) => handleSession(cell.index, value)"
                >
                  <template #overlay="{ video, clock }">
                    <CameraRecognitionOverlay
                      class="wall-recognition"
                      :show-overlay="overlayEnabled"
                      :camera="cell.camera"
                      :video="video"
                      :clock="clock"
                      :frames="overlayFrames[cell.index] || {}"
                    />
                  </template>
                </CameraPreviewPlayer>
                <div class="cell-actions">
                  <Tooltip title="图层显示设置">
                    <Button
                      shape="circle"
                      size="small"
                      aria-label="图层显示设置"
                      @click.stop="
                        router.push({
                          path: '/ai-video/live',
                          query: { cameraId: String(cell.cameraId) },
                        })
                      "
                    >
                      <IconifyIcon icon="lucide:layers" />
                    </Button>
                  </Tooltip>
                  <Tooltip
                    :title="
                      cellMuted[cell.index]
                        ? $t('page.aiVideo.live.unmute')
                        : $t('page.aiVideo.live.mute')
                    "
                  >
                    <Button
                      shape="circle"
                      size="small"
                      @click.stop="
                        cellMuted[cell.index] = !cellMuted[cell.index]
                      "
                    >
                      <IconifyIcon
                        :icon="
                          cellMuted[cell.index]
                            ? 'lucide:volume-x'
                            : 'lucide:volume-2'
                        "
                      />
                    </Button>
                  </Tooltip>
                  <Tooltip :title="$t('page.aiVideo.wall.cellFullscreen')">
                    <Button
                      shape="circle"
                      size="small"
                      @click.stop="fullscreenCell(cell.index)"
                    >
                      <IconifyIcon icon="lucide:maximize-2" />
                    </Button>
                  </Tooltip>
                  <Tooltip :title="$t('page.aiVideo.wall.removeChannel')">
                    <Button
                      danger
                      shape="circle"
                      size="small"
                      @click.stop="clearCell(cell.index)"
                    >
                      <IconifyIcon icon="lucide:x" />
                    </Button>
                  </Tooltip>
                </div>
              </template>
              <template v-else>
                <div class="empty-channel">
                  <IconifyIcon icon="lucide:monitor-up" />
                  <strong>{{
                    $t('page.aiVideo.wall.channel', [cell.index + 1])
                  }}</strong>
                  <span>{{ $t('page.aiVideo.wall.emptyChannelHint') }}</span>
                </div>
              </template>
            </article>
          </div>
        </section>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.wall-recognition {
  position: absolute;
  inset: 0;
  z-index: 1;
  min-height: 0;
}

.analysis-mode :deep(.camera-preview-player__statusbar) {
  display: none;
}

.cell-task-select {
  position: absolute;
  top: 8px;
  left: 8px;
  z-index: 5;
  width: 150px;
}

.wall-page {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 700px;
  overflow: hidden;
  color: hsl(var(--foreground));
  background: hsl(var(--background));
  border: 1px solid hsl(var(--border));
  border-radius: 12px;
}

.wall-page :deep(.ai-page-header) {
  padding: 10px 16px;
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.loaded-copy,
.toolbar-loaded {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.wall-workspace {
  display: grid;
  flex: 1;
  grid-template-columns: 288px minmax(0, 1fr);
  min-height: 0;
}

.device-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: 0;
  padding: 14px;
  overflow: hidden;
  background: hsl(var(--card));
  border-right: 1px solid hsl(var(--border));
}

.device-panel__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 650;
  color: hsl(var(--foreground));
}

.device-panel__title span {
  display: flex;
  gap: 7px;
  align-items: center;
}

.device-panel :deep(.ant-spin-nested-loading) {
  flex: 1;
  min-height: 0;
  overflow: auto;
}

.camera-tree-node {
  display: flex;
  gap: 6px;
  align-items: center;
  min-width: 0;
}

.camera-tree-node span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.device-hint {
  margin: 0;
  font-size: 11px;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.wall-main {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}

.wall-controls {
  position: relative;
  flex-shrink: 0;
}

.wall-toolbar {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  align-items: center;
  min-height: 54px;
  padding: 9px 14px;
  background: hsl(var(--card));
  border-bottom: 1px solid hsl(var(--border));
}

.wall-toolbar > * {
  flex-shrink: 0;
  white-space: nowrap;
}

.toolbar-switch {
  display: inline-flex;
  gap: 7px;
  align-items: center;
  font-size: 12px;
  color: hsl(var(--foreground));
}

.toolbar-separator {
  width: 1px;
  height: 26px;
  background: hsl(var(--border));
}

.toolbar-loaded {
  margin-left: auto;
}

.layout-panel {
  position: absolute;
  inset: 100% 0 auto;
  z-index: 20;
  padding: 18px;
  background: hsl(var(--popover));
  border-bottom: 1px solid hsl(var(--border));
  box-shadow: var(--ai-shadow-md);
}

.layout-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 14px;
}

.layout-panel__header div,
.layout-panel__header strong {
  display: flex;
  gap: 8px;
  align-items: center;
}

.layout-panel__header span {
  font-size: 12px;
  font-weight: 400;
  color: hsl(var(--muted-foreground));
}

.layout-cards {
  display: grid;
  grid-template-columns: repeat(5, minmax(150px, 1fr));
  gap: 10px;
}

.layout-card {
  display: flex;
  flex-direction: column;
  min-height: 132px;
  padding: 10px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
}

.layout-card.active {
  background: hsl(var(--primary) / 9%);
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 1px hsl(var(--primary));
}

.layout-card.empty {
  border-style: dashed;
}

.layout-card__title {
  display: flex;
  gap: 7px;
  align-items: center;
  color: hsl(var(--foreground));
}

.layout-card__title > svg {
  font-size: 22px;
  color: hsl(var(--primary) / 65%);
}

.layout-card__title .ant-tag {
  margin-left: auto;
}

.layout-card p {
  margin: auto 0 10px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.layout-card__actions {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 5px;
}

.save-empty {
  flex: 1;
  font-size: 12px;
  color: hsl(var(--primary));
  cursor: pointer;
  background: transparent;
  border: 0;
}

.wall-grid {
  display: grid;
  flex: 1;
  grid-template-rows: repeat(var(--wall-columns), minmax(0, 1fr));
  grid-template-columns: repeat(var(--wall-columns), minmax(0, 1fr));
  gap: 3px;
  min-height: 0;
  padding: 3px;
  background: hsl(var(--border));
}

.wall-grid:fullscreen {
  height: 100vh;
}

.wall-cell {
  position: relative;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  outline: 1px dashed hsl(var(--border));
  outline-offset: -1px;
  background: hsl(var(--muted) / 45%);
}

.wall-cell.selected {
  z-index: 1;
  outline: 2px solid hsl(var(--primary));
  outline-offset: -2px;
}

.empty-channel {
  display: flex;
  flex-direction: column;
  gap: 7px;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  min-height: 110px;
  color: hsl(var(--muted-foreground));
}

.empty-channel > svg {
  font-size: 22px;
  color: hsl(var(--muted-foreground) / 70%);
}

.empty-channel span {
  font-size: 11px;
}

.cell-actions {
  position: absolute;
  top: 7px;
  right: 7px;
  z-index: 8;
  display: flex;
  gap: 5px;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.wall-cell:hover .cell-actions,
.wall-cell:focus-within .cell-actions {
  opacity: 1;
}

@media (width <= 1200px) {
  .wall-workspace {
    grid-template-columns: 230px minmax(0, 1fr);
  }

  .layout-cards {
    grid-template-columns: repeat(3, 1fr);
    max-height: 430px;
    overflow: auto;
  }
}
</style>
