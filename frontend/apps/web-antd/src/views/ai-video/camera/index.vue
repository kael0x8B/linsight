<script lang="ts" setup>
import type { Key } from 'ant-design-vue/es/_util/type';
import type { DataNode } from 'ant-design-vue/es/tree';

import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { computed, onMounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { confirm, Page, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime, handleTree } from '@vben/utils';

import {
  Alert,
  Badge,
  Button,
  Card,
  Dropdown,
  Input,
  message,
  Pagination,
  Segmented,
  Space,
  Spin,
  Tooltip,
  Tree,
} from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteCamera,
  deleteCameraGroup,
  getCameraGroupList,
  getCameraPage,
} from '#/api/ai-video/camera';
import { AiPageHeader, AiStatusIndicator } from '#/components/ai-video';
import { $t } from '#/locales';

import { useCameraGridColumns, useCameraGridFormSchema } from './data';
import CameraForm from './modules/camera-form.vue';
import GroupForm from './modules/group-form.vue';

const router = useRouter();

const groups = ref<AiVideoCameraApi.CameraGroup[]>([]);
const groupLoading = ref(false);
const groupError = ref('');
const groupKeyword = ref('');
const cameraError = ref('');
const selectedGroupId = ref<number>();
const selectedTreeKeys = ref<Key[]>([0]);
const viewMode = ref<'card' | 'list'>(
  window.innerWidth < 900 ? 'card' : 'list',
);
const cardLoading = ref(false);
const cardCameras = ref<AiVideoCameraApi.Camera[]>([]);
const cardTotal = ref(0);
const cardQuery = ref({
  name: '',
  onlineStatus: 'all' as 'all' | number,
  pageNo: 1,
  pageSize: 12,
});

const groupNameMap = computed(
  () => new Map(groups.value.map((group) => [group.id, group.name])),
);
const selectedGroup = computed(() =>
  groups.value.find((group) => group.id === selectedGroupId.value),
);
const treeData = computed<DataNode[]>(() => {
  const keyword = groupKeyword.value.trim().toLowerCase();
  const groupTree = handleTree(
    groups.value.map(({ children: _children, ...group }) => ({ ...group })),
    'id',
    'parentId',
    'children',
  ) as AiVideoCameraApi.CameraGroup[];
  const visibleTree = keyword ? filterGroupTree(groupTree, keyword) : groupTree;
  const children = visibleTree.map((group) => toTreeNode(group));
  return [{ key: 0, title: '全部摄像头', children }];
});

function filterGroupTree(
  nodes: AiVideoCameraApi.CameraGroup[],
  keyword: string,
): AiVideoCameraApi.CameraGroup[] {
  return nodes.flatMap((node) => {
    const children = filterGroupTree(node.children ?? [], keyword);
    if (node.name.toLowerCase().includes(keyword) || children.length > 0) {
      return [{ ...node, children }];
    }
    return [];
  });
}

function toTreeNode(group: AiVideoCameraApi.CameraGroup): DataNode {
  return {
    key: group.id!,
    title: group.name,
    children: group.children?.map(toTreeNode),
  };
}

const [CameraModal, cameraModalApi] = useVbenModal({
  connectedComponent: CameraForm,
  destroyOnClose: true,
});
const [GroupModal, groupModalApi] = useVbenModal({
  connectedComponent: GroupForm,
  destroyOnClose: true,
});
async function loadGroups() {
  groupLoading.value = true;
  groupError.value = '';
  try {
    groups.value = await getCameraGroupList();
  } catch {
    groupError.value = '分组加载失败，请检查服务状态后重试。';
  } finally {
    groupLoading.value = false;
  }
}

async function handleGroupChanged() {
  await loadGroups();
  await gridApi.query();
  await loadCardCameras();
}

function handleTreeSelect(keys: Key[]) {
  const key = Number(keys[0] ?? 0);
  selectedTreeKeys.value = [key];
  selectedGroupId.value = key === 0 ? undefined : key;
  gridApi.query();
  void loadCardCameras();
}

function handleCreateCamera() {
  cameraModalApi.setData({ groupId: selectedGroupId.value ?? 0 }).open();
}

function handleEditCamera(row: AiVideoCameraApi.Camera) {
  cameraModalApi.setData(row).open();
}

function handlePreviewCamera(row: AiVideoCameraApi.Camera) {
  if (!row.id) return;
  void router.push({
    path: '/ai-video/live',
    query: { cameraId: String(row.id) },
  });
}

async function handleDeleteCamera(row: AiVideoCameraApi.Camera) {
  const hideLoading = message.loading({
    content: `正在删除 ${row.name}`,
    duration: 0,
  });
  try {
    await deleteCamera(row.id!);
    message.success(`摄像头 ${row.name} 已删除`);
    await gridApi.query();
  } finally {
    hideLoading();
  }
}

async function confirmDeleteCamera(row: AiVideoCameraApi.Camera) {
  await confirm(
    `确认删除摄像头“${row.name}”吗？有关联任务时系统将阻止删除；该操作不可恢复。`,
  );
  await handleDeleteCamera(row);
}

function handleCreateGroup() {
  groupModalApi.setData({ parentId: selectedGroupId.value ?? 0 }).open();
}

function handleEditGroup() {
  if (selectedGroup.value) groupModalApi.setData(selectedGroup.value).open();
}

async function handleDeleteGroup() {
  const group = selectedGroup.value;
  if (!group?.id) return;

  await confirm(
    `确认删除分组“${group.name}”吗？存在下级分组或摄像头时，系统会阻止删除。`,
  );
  const hideLoading = message.loading({
    content: `正在删除 ${group.name}`,
    duration: 0,
  });
  try {
    await deleteCameraGroup(group.id);
    selectedGroupId.value = undefined;
    selectedTreeKeys.value = [0];
    message.success(`分组 ${group.name} 已删除`);
    await handleGroupChanged();
  } finally {
    hideLoading();
  }
}

function handleRefresh() {
  gridApi.query();
  void loadCardCameras();
}

async function loadCardCameras() {
  cardLoading.value = true;
  cameraError.value = '';
  try {
    const result = await getCameraPage({
      groupId: selectedGroupId.value,
      name: cardQuery.value.name || undefined,
      onlineStatus:
        cardQuery.value.onlineStatus === 'all'
          ? undefined
          : cardQuery.value.onlineStatus,
      pageNo: cardQuery.value.pageNo,
      pageSize: cardQuery.value.pageSize,
    });
    if (
      result.list.length === 0 &&
      result.total > 0 &&
      cardQuery.value.pageNo > 1
    ) {
      cardQuery.value.pageNo = Math.max(
        1,
        Math.ceil(result.total / cardQuery.value.pageSize),
      );
      await loadCardCameras();
      return;
    }
    cardCameras.value = result.list;
    cardTotal.value = result.total;
  } catch {
    cameraError.value = '摄像头列表加载失败，请检查服务状态后重试。';
  } finally {
    cardLoading.value = false;
  }
}

async function queryCameraPage(
  page: { currentPage: number; pageSize: number },
  formValues: Record<string, unknown>,
) {
  cameraError.value = '';
  try {
    return await getCameraPage({
      pageNo: page.currentPage,
      pageSize: page.pageSize,
      ...formValues,
      groupId: selectedGroupId.value,
    });
  } catch (error) {
    cameraError.value = '摄像头列表加载失败，请检查服务状态后重试。';
    throw error;
  }
}

const onlineStatus: Record<
  number,
  { status: 'default' | 'error' | 'success'; text: string }
> = {
  0: { status: 'default' as const, text: '未知' },
  1: { status: 'success' as const, text: '在线' },
  2: { status: 'error' as const, text: '离线' },
};

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: { schema: useCameraGridFormSchema() },
  gridOptions: {
    columns: useCameraGridColumns(),
    height: 'auto',
    scrollY: { enabled: false },
    scrollX: { enabled: false },
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          await queryCameraPage(page, formValues),
      },
    },
    rowConfig: { keyField: 'id', isHover: true },
    toolbarConfig: { refresh: true, search: true },
  } as VxeTableGridOptions<AiVideoCameraApi.Camera>,
});

watch(viewMode, (mode) => {
  if (mode === 'card') void loadCardCameras();
});
onMounted(async () => {
  await loadGroups();
  await loadCardCameras();
});
</script>

<template>
  <Page auto-content-height>
    <CameraModal @success="handleRefresh" />
    <GroupModal @success="handleGroupChanged" />

    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="摄像头"
        description="管理摄像头、分组和视频接入。"
        icon="lucide:cctv"
      >
        <template #extra>
          <Space>
            <Segmented
              v-model:value="viewMode"
              :options="[
                { label: '列表', value: 'list' },
                { label: '卡片', value: 'card' },
              ]"
            />
            <Button type="primary" @click="handleCreateCamera">
              <IconifyIcon icon="lucide:plus" />新增摄像头
            </Button>
          </Space>
        </template>
      </AiPageHeader>
      <div class="camera-page flex min-h-0 flex-1 gap-4">
        <Card class="group-panel h-full shrink-0" title="摄像头分组">
          <template #extra>
            <TableAction
              :actions="[
                {
                  label: '新增',
                  type: 'link',
                  auth: ['ai-video:camera:create'],
                  onClick: handleCreateGroup,
                },
                {
                  label: '编辑',
                  type: 'link',
                  auth: ['ai-video:camera:update'],
                  disabled: !selectedGroup,
                  onClick: handleEditGroup,
                },
                {
                  label: '删除',
                  type: 'link',
                  danger: true,
                  auth: ['ai-video:camera:delete'],
                  disabled: !selectedGroup,
                  onClick: handleDeleteGroup,
                },
              ]"
            />
          </template>

          <Input
            v-model:value="groupKeyword"
            allow-clear
            class="mb-3"
            placeholder="搜索分组"
          />
          <Alert
            v-if="groupError"
            class="mb-3"
            :message="groupError"
            show-icon
            type="error"
          >
            <template #action>
              <Button size="small" @click="loadGroups">重试</Button>
            </template>
          </Alert>
          <Spin :spinning="groupLoading">
            <Tree
              v-if="treeData.length"
              block-node
              default-expand-all
              :selected-keys="selectedTreeKeys"
              :tree-data="treeData"
              @select="handleTreeSelect"
            />
          </Spin>
        </Card>

        <div class="flex min-h-0 min-w-0 flex-1 flex-col gap-3">
          <Alert
            v-if="cameraError"
            :message="cameraError"
            show-icon
            type="error"
          >
            <template #action>
              <Button size="small" @click="handleRefresh">重试</Button>
            </template>
          </Alert>
          <div v-if="viewMode === 'list'" class="min-h-0 flex-1">
            <Grid
              :table-title="
                selectedGroup ? `${selectedGroup.name} · 摄像头` : '全部摄像头'
              "
            >
              <template #group="{ row }">
                {{ groupNameMap.get(row.groupId) || '未分组' }}
              </template>
              <template #onlineStatus="{ row }">
                <Badge
                  :status="
                    onlineStatus[row.onlineStatus ?? 0]?.status || 'default'
                  "
                  :text="onlineStatus[row.onlineStatus ?? 0]?.text || '未知'"
                />
              </template>
              <template #endpoint="{ row }">
                <span class="font-mono text-xs">{{
                  row.maskedStreamEndpoint || '-'
                }}</span>
              </template>
              <template #actions="{ row }">
                <TableAction
                  :actions="[
                    {
                      label: '预览',
                      type: 'link',
                      auth: ['ai-video:camera:preview'],
                      onClick: handlePreviewCamera.bind(null, row),
                    },
                  ]"
                  :drop-down-actions="[
                    {
                      label: $t('common.edit'),
                      type: 'link',
                      icon: ACTION_ICON.EDIT,
                      auth: ['ai-video:camera:update'],
                      onClick: handleEditCamera.bind(null, row),
                    },
                    {
                      label: $t('common.delete'),
                      type: 'link',
                      danger: true,
                      icon: ACTION_ICON.DELETE,
                      auth: ['ai-video:camera:delete'],
                      popConfirm: {
                        title: `确认删除摄像头“${row.name}”吗？`,
                        confirm: handleDeleteCamera.bind(null, row),
                      },
                    },
                  ]"
                />
              </template>
            </Grid>
          </div>
          <div v-else class="camera-card-view min-h-0 flex-1 overflow-auto">
            <div class="camera-card-filters ai-surface">
              <Input
                v-model:value="cardQuery.name"
                allow-clear
                placeholder="搜索摄像头名称"
                @press-enter="loadCardCameras"
              />
              <Segmented
                v-model:value="cardQuery.onlineStatus"
                :options="[
                  { label: '全部', value: 'all' },
                  { label: '在线', value: 1 },
                  { label: '离线', value: 2 },
                ]"
                @change="loadCardCameras"
              />
              <Button @click="loadCardCameras">
                <IconifyIcon icon="lucide:search" />搜索
              </Button>
            </div>
            <Spin :spinning="cardLoading">
              <div v-if="cardCameras.length" class="camera-card-grid">
                <article
                  v-for="camera in cardCameras"
                  :key="camera.id"
                  class="camera-card ai-surface"
                >
                  <button
                    class="camera-thumb"
                    type="button"
                    @click="handlePreviewCamera(camera)"
                  >
                    <span class="camera-thumb__grid"></span>
                    <IconifyIcon
                      class="camera-thumb__icon"
                      icon="lucide:video"
                    />
                    <span class="camera-thumb__label">打开实时预览</span>
                    <AiStatusIndicator
                      class="camera-thumb__status"
                      :label="
                        onlineStatus[camera.onlineStatus ?? 0]?.text || '未知'
                      "
                      :status="camera.onlineStatus ?? 0"
                      size="sm"
                    />
                  </button>
                  <div class="camera-card__body">
                    <div class="camera-card__title">
                      <div>
                        <strong>{{ camera.name }}</strong
                        ><span>{{ camera.code }}</span>
                      </div>
                      <Tooltip
                        :title="camera.maskedStreamEndpoint || '未配置码流'"
                      >
                        <IconifyIcon icon="lucide:shield-check" />
                      </Tooltip>
                    </div>
                    <dl>
                      <div>
                        <dt>所属分组</dt>
                        <dd>
                          {{ groupNameMap.get(camera.groupId) || '未分组' }}
                        </dd>
                      </div>
                      <div>
                        <dt>接入协议</dt>
                        <dd>{{ camera.protocol }}</dd>
                      </div>
                      <div>
                        <dt>最近在线</dt>
                        <dd>
                          {{
                            camera.lastOnlineTime
                              ? formatDateTime(camera.lastOnlineTime)
                              : '暂无记录'
                          }}
                        </dd>
                      </div>
                    </dl>
                    <div class="camera-card__actions">
                      <Button
                        type="primary"
                        size="small"
                        @click="handlePreviewCamera(camera)"
                      >
                        <IconifyIcon icon="lucide:play" />预览
                      </Button>
                      <Button size="small" @click="handleEditCamera(camera)">
                        <IconifyIcon icon="lucide:settings-2" />编辑
                      </Button>
                      <Dropdown>
                        <Button size="small" aria-label="更多操作">
                          <IconifyIcon icon="lucide:ellipsis" />
                        </Button>
                        <template #overlay>
                          <div class="camera-more-menu">
                            <Button
                              danger
                              type="text"
                              @click="confirmDeleteCamera(camera)"
                            >
                              删除摄像头
                            </Button>
                          </div>
                        </template>
                      </Dropdown>
                    </div>
                  </div>
                </article>
              </div>
              <div v-else-if="!cardLoading" class="camera-empty ai-surface">
                <IconifyIcon icon="lucide:cctv" /><strong>暂无摄像头</strong
                ><span>调整筛选条件，或先接入一路 RTSP / ONVIF 视频源。</span
                ><Button type="primary" @click="handleCreateCamera">
                  新增摄像头
                </Button>
              </div>
            </Spin>
            <Pagination
              v-if="cardTotal > cardQuery.pageSize"
              v-model:current="cardQuery.pageNo"
              class="camera-pagination"
              :page-size="cardQuery.pageSize"
              :total="cardTotal"
              show-less-items
              @change="loadCardCameras"
            />
          </div>
        </div>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.group-panel {
  width: 240px;
}

.camera-page :deep(.ant-card-body) {
  max-height: calc(100% - 57px);
  overflow: auto;
}

.camera-card-view {
  padding: 1px;
}

.camera-card-filters {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px;
  margin-bottom: 14px;
}

.camera-card-filters :deep(.ant-input-affix-wrapper) {
  width: min(320px, 38vw);
}

.camera-card-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(260px, 1fr));
  gap: 14px;
}

.camera-card {
  overflow: hidden;
  transition:
    transform 150ms ease,
    box-shadow 150ms ease;
}

.camera-card:hover {
  box-shadow: var(--ai-shadow-md);
  transform: translateY(-1px);
}

.camera-thumb {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 16 / 8.8;
  overflow: hidden;
  color: #94a3b8;
  background: #090f19;
}

.camera-thumb__grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgb(148 163 184 / 5%) 1px, transparent 1px),
    linear-gradient(90deg, rgb(148 163 184 / 5%) 1px, transparent 1px);
  background-size: 28px 28px;
  mask-image: linear-gradient(to bottom, black, transparent);
}

.camera-thumb__icon {
  z-index: 1;
  font-size: 26px;
}

.camera-thumb__label {
  position: absolute;
  bottom: 14px;
  z-index: 1;
  font-size: 11px;
  opacity: 0;
  transition: opacity 150ms ease;
}

.camera-thumb:hover .camera-thumb__label {
  opacity: 1;
}

.camera-thumb__status {
  position: absolute;
  top: 12px;
  left: 12px;
  z-index: 2;
  padding: 4px 8px;
  color: #e2e8f0;
  background: rgb(2 6 23 / 72%);
  border-radius: 999px;
  backdrop-filter: blur(8px);
}

.camera-card__body {
  padding: 14px;
}

.camera-card__title {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
}

.camera-card__title div {
  display: grid;
  min-width: 0;
}

.camera-card__title strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 14px;
  white-space: nowrap;
}

.camera-card__title span {
  margin-top: 2px;
  font-family: ui-monospace, monospace;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.camera-card__title > svg {
  font-size: 16px;
  color: var(--ai-success);
}

.camera-card dl {
  display: grid;
  gap: 7px;
  margin: 14px 0;
}

.camera-card dl div {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
}

.camera-card dt {
  color: hsl(var(--muted-foreground));
}

.camera-card dd {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.camera-card__actions {
  display: flex;
  gap: 7px;
  align-items: center;
  padding-top: 12px;
  border-top: 1px solid hsl(var(--border) / 52%);
}

.camera-more-menu {
  padding: 5px;
  background: hsl(var(--popover));
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  box-shadow: var(--ai-shadow-md);
}

.camera-empty {
  display: flex;
  flex-direction: column;
  gap: 9px;
  align-items: center;
  justify-content: center;
  min-height: 300px;
  color: hsl(var(--muted-foreground));
}

.camera-empty > svg {
  margin-bottom: 6px;
  font-size: 32px;
}

.camera-empty strong {
  color: hsl(var(--foreground));
}

.camera-empty span {
  font-size: 12px;
}

.camera-pagination {
  display: flex;
  justify-content: flex-end;
  padding: 16px 2px 2px;
}

@media (width <= 1500px) {
  .camera-card-grid {
    grid-template-columns: repeat(2, minmax(250px, 1fr));
  }
}

@media (width <= 1100px) {
  .camera-card-grid {
    grid-template-columns: 1fr;
  }

  .group-panel {
    width: 210px;
  }
}

@media (width <= 900px) {
  .camera-page {
    flex-direction: column;
    overflow: auto;
  }

  .group-panel {
    width: 100%;
    height: auto;
    max-height: 190px;
    overflow: auto;
  }

  .camera-card-filters {
    flex-wrap: wrap;
  }
}
</style>
