<script lang="ts" setup>
import type { AiVideoNodeDeployment } from '#/api/ai-video/node';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime } from '@vben/utils';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Empty,
  Progress,
  Spin,
  Tag,
} from 'ant-design-vue';

import { getNodeDeployment, getNodeDeploymentPage } from '#/api/ai-video/node';

import DeploymentTerminal from './deployment-terminal.vue';

const props = defineProps<{ embedded?: boolean; gatewayId?: number }>();
const records = ref<AiVideoNodeDeployment[]>([]);
const nodeId = ref<number>();
const loading = ref(false);
const selected = ref<AiVideoNodeDeployment>();
const drawerTitle = computed(() =>
  selected.value ? `部署详情 #${selected.value.id}` : '节点部署记录',
);
const error = ref('');
let generation = 0;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

function operationLabel(type: AiVideoNodeDeployment['operationType']) {
  return (
    { INITIAL: '初始部署', REDEPLOY: '在线升级', ROLLBACK: '部署回滚' }[type] ??
    type
  );
}

function statusMeta(status: AiVideoNodeDeployment['status']) {
  return (
    {
      FAILED: { color: 'red', text: '失败' },
      QUEUED: { color: 'blue', text: '等待' },
      RUNNING: { color: 'processing', text: '部署中' },
      SUCCEEDED: { color: 'green', text: '已完成' },
    }[status] ?? { color: 'default', text: status }
  );
}

function clearPoll() {
  generation++;
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = undefined;
}

async function refreshDetail(id: number, expectedGeneration: number) {
  const result = await getNodeDeployment(id);
  if (generation !== expectedGeneration) return;
  selected.value = result;
  const index = records.value.findIndex((row) => row.id === result.id);
  if (index !== -1) records.value[index] = result;
  error.value = '';
}

function schedulePoll() {
  const active = selected.value ? [selected.value] : records.value;
  if (!active.some((row) => ['QUEUED', 'RUNNING'].includes(row.status))) return;
  const expectedGeneration = generation;
  const id = selected.value?.id;
  pollTimer = setTimeout(async () => {
    try {
      await (id
        ? refreshDetail(id, expectedGeneration)
        : refreshList(expectedGeneration));
    } catch {
      if (generation === expectedGeneration)
        error.value = '日志刷新失败，正在自动重试。';
    } finally {
      if (generation === expectedGeneration) schedulePoll();
    }
  }, 1500);
}

async function openDetail(item: AiVideoNodeDeployment) {
  clearPoll();
  error.value = '';
  selected.value = item;
  const expectedGeneration = generation;
  loading.value = true;
  try {
    await refreshDetail(item.id, expectedGeneration);
  } catch {
    if (generation === expectedGeneration)
      error.value = '部署详情加载失败，请重试。';
  } finally {
    if (generation === expectedGeneration) {
      loading.value = false;
      schedulePoll();
    }
  }
}

async function refreshList(expectedGeneration: number) {
  const result = await getNodeDeploymentPage({
    nodeId: nodeId.value,
    pageNo: 1,
    pageSize: 50,
  });
  if (generation !== expectedGeneration) return;
  records.value = result.list;
  error.value = '';
}

async function loadList() {
  clearPoll();
  selected.value = undefined;
  const current = generation;
  loading.value = records.value.length === 0;
  try {
    await refreshList(current);
  } catch {
    if (generation === current) error.value = '部署记录加载失败，请重试。';
  } finally {
    if (generation === current) {
      loading.value = false;
      schedulePoll();
    }
  }
}

const [Drawer, drawerApi] = useVbenDrawer({
  footer: false,
  async onOpenChange(open) {
    if (!open) {
      clearPoll();
      selected.value = undefined;
      records.value = [];
      loading.value = false;
      return;
    }
    error.value = '';
    nodeId.value = drawerApi.getData<{ nodeId?: number }>()?.nodeId;
    await loadList();
  },
});

onMounted(() => {
  if (props.embedded) {
    nodeId.value = props.gatewayId;
    void loadList();
  }
});
onBeforeUnmount(clearPoll);
</script>

<template>
  <component
    :is="embedded ? 'div' : Drawer"
    :class="embedded ? '' : 'w-[860px] max-w-[calc(100vw-32px)]'"
    :title="embedded ? undefined : drawerTitle"
  >
    <Alert v-if="error" class="mb-3" :message="error" type="warning" show-icon>
      <template #action>
        <Button
          size="small"
          @click="selected ? openDetail(selected) : loadList()"
        >
          重试
        </Button>
      </template>
    </Alert>
    <template v-if="selected">
      <Button class="mb-4" type="text" @click="loadList">
        <IconifyIcon icon="lucide:arrow-left" />返回部署记录
      </Button>
      <Spin :spinning="loading">
        <div class="deployment-detail">
          <div class="detail-progress">
            <div>
              <strong>{{ selected.nodeName }}</strong>
              <span
                >{{ selected.username }}@{{ selected.host }}:{{
                  selected.port
                }}</span
              >
            </div>
            <Tag :color="statusMeta(selected.status).color">
              {{ statusMeta(selected.status).text }}
            </Tag>
          </div>
          <Progress
            :percent="selected.progress"
            :status="
              selected.status === 'FAILED'
                ? 'exception'
                : selected.status === 'SUCCEEDED'
                  ? 'success'
                  : 'active'
            "
          />
          <Descriptions bordered :column="2" size="small">
            <DescriptionsItem label="节点编码">
              {{ selected.nodeCode }}
            </DescriptionsItem>
            <DescriptionsItem label="原版本">
              {{ selected.previousVersion || '未记录' }}
            </DescriptionsItem>
            <DescriptionsItem label="目标版本">
              {{ selected.targetVersion || '尚未生成 / 未记录' }}
            </DescriptionsItem>
            <DescriptionsItem label="部署类型">
              {{ operationLabel(selected.operationType) }}
            </DescriptionsItem>
            <DescriptionsItem label="执行阶段">
              {{ selected.stage }}
            </DescriptionsItem>
            <DescriptionsItem label="开始时间">
              {{ formatDateTime(selected.createTime) }}
            </DescriptionsItem>
            <DescriptionsItem label="完成时间">
              {{
                selected.finishTime
                  ? formatDateTime(selected.finishTime)
                  : '尚未完成'
              }}
            </DescriptionsItem>
            <DescriptionsItem label="状态说明" :span="2">
              {{ selected.message || '暂无' }}
            </DescriptionsItem>
            <DescriptionsItem
              v-if="selected.runtimePackageSha256"
              label="Runtime SHA256"
              :span="2"
            >
              <code>{{ selected.runtimePackageSha256 }}</code>
            </DescriptionsItem>
            <DescriptionsItem
              v-if="selected.diagnosticId"
              label="诊断 ID"
              :span="2"
            >
              <code>{{ selected.diagnosticId }}</code>
            </DescriptionsItem>
          </Descriptions>
          <DeploymentTerminal
            :output="selected.outputLog"
            :status="selected.status"
            :log-status="selected.logStatus"
            :truncated="selected.logTruncated"
          />
        </div>
      </Spin>
    </template>
    <template v-else>
      <div class="mb-3 flex items-center justify-between">
        <span class="text-muted-foreground">最新 50 条部署记录</span>
        <Button size="small" @click="loadList">刷新</Button>
      </div>
      <Spin
        :spinning="loading"
        :class="embedded ? 'block max-h-[650px] overflow-y-auto pr-2' : ''"
      >
        <Empty
          v-if="!loading && !records.length && !error"
          description="暂无部署记录，可从“部署新节点”开始"
        />
        <button
          v-for="item in records"
          :key="item.id"
          type="button"
          class="deployment-record w-full text-left"
          @click="openDetail(item)"
        >
          <div class="record-head">
            <div>
              <strong>{{ item.nodeName }}</strong
              ><span>{{ item.username }}@{{ item.host }}:{{ item.port }}</span>
            </div>
            <Tag :color="statusMeta(item.status).color">
              {{ statusMeta(item.status).text }}
            </Tag>
          </div>
          <Progress
            :percent="item.progress"
            :status="
              item.status === 'FAILED'
                ? 'exception'
                : item.status === 'SUCCEEDED'
                  ? 'success'
                  : 'active'
            "
            size="small"
          />
          <div class="record-meta">
            <span
              >#{{ item.id }} · {{ operationLabel(item.operationType) }}</span
            ><span>{{ formatDateTime(item.createTime) }}</span
            ><span>{{ item.nodeCode }}</span>
          </div>
          <p class="line-clamp-2">{{ item.message || '暂无状态说明' }}</p>
          <span class="detail-link"
            >查看日志<IconifyIcon icon="lucide:chevron-right"
          /></span>
        </button>
      </Spin>
    </template>
  </component>
</template>

<style scoped>
.deployment-record {
  padding: 16px !important;
  margin-bottom: 10px;
  cursor: pointer;
  border: 1px solid hsl(var(--border)) !important;
  border-radius: 10px;
  transition:
    border-color 160ms ease,
    background 160ms ease;
}

.deployment-record:hover,
.deployment-record:focus-visible {
  outline: none;
  background: hsl(var(--primary) / 4%);
  border-color: hsl(var(--primary) / 55%) !important;
}

.record-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  margin-bottom: 10px;
}

.record-head > div {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.record-head strong {
  font-size: 14px;
}

.record-head span,
.record-meta,
.deployment-record p,
.deployment-record code {
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.record-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 7px;
}

.deployment-record p {
  margin: 8px 0 0;
}

.deployment-record code {
  display: block;
  margin-top: 6px;
  overflow-wrap: anywhere;
}

.detail-link {
  display: flex;
  gap: 4px;
  align-items: center;
  justify-content: flex-end;
  margin-top: 10px;
  font-size: 12px;
  color: hsl(var(--primary));
}

.deployment-detail {
  display: grid;
  gap: 16px;
}

.detail-progress {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
}

.detail-progress > div {
  display: flex;
  flex-direction: column;
}

.detail-progress span {
  margin-top: 3px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}

.deployment-detail code {
  font-size: 12px;
  overflow-wrap: anywhere;
}

.deployment-detail :deep(.ant-descriptions-item-label) {
  min-width: 88px;
  white-space: nowrap;
}

.deployment-detail :deep(.ant-descriptions-item-content) {
  overflow-wrap: anywhere;
}
</style>
