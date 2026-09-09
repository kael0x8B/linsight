<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoNodeLogApi } from '#/api/ai-video/node-log';

import { computed, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';

import { Alert, Button, message, Space, Switch, Tag } from 'ant-design-vue';

import { ACTION_ICON, TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getNodeDiagnostic, getNodeLogPage, getNodeLogSnapshot } from '#/api/ai-video/node-log';
import { AiPageHeader } from '#/components/ai-video';

import { useLogColumns, useLogFormSchema } from './data';
import ContextDrawerComponent from './modules/context-drawer.vue';
import DiagnosticModalComponent from './modules/diagnostic-modal.vue';

const props = defineProps<{ embedded?: boolean; gatewayId?: number }>();
const route = useRoute();
const router = useRouter();
const { hasAccessByCodes } = useAccess();
const canCreateDiagnostic = computed(() =>
  hasAccessByCodes(['ai-video:node-log:diagnostic']),
);
const nodeId = props.gatewayId ?? Number(route.params.id);
const paused = ref(false);
const follow = ref(true);
const pendingCount = ref(0);
const refreshError = ref('');
const wrapLines = ref(false);
let refreshing = false;
let refreshTimer: ReturnType<typeof setTimeout> | undefined;
let generation = 0;
let pollEpoch = 0;
let disposed = false;
let currentPage = 1;
let pageSize = 20;
let snapshotMaxId: number | undefined;
let cursor = 0;
let rows: AiVideoNodeLogApi.Log[] = [];
let buffered: AiVideoNodeLogApi.Log[] = [];
let filters: Record<string, unknown> = {};
let total = 0;
let failures = 0;
const historical = ref(false);

const [ContextDrawer, contextDrawerApi] = useVbenDrawer({
  connectedComponent: ContextDrawerComponent,
  destroyOnClose: true,
});
const [DiagnosticModal, diagnosticModalApi] = useVbenModal({
  connectedComponent: DiagnosticModalComponent,
  destroyOnClose: true,
});

function openContext(row: AiVideoNodeLogApi.Log) {
  contextDrawerApi.setData(row).open();
}

async function waitForDiagnostic(id: number) {
  const hide = message.loading({ content: '诊断包生成中', duration: 0 });
  try {
    for (let attempt = 0; attempt < 30; attempt += 1) {
      if (disposed) return;
      const result = await getNodeDiagnostic(id);
      if (disposed) return;
      if (result.status === 'READY' && result.accessUrl) {
        window.open(result.accessUrl, '_blank', 'noopener,noreferrer');
        message.success(`诊断包已生成，共 ${result.logCount} 行日志`);
        return;
      }
      if (result.status === 'FAILED') throw new Error(result.errorMessage || '诊断包生成失败');
      await new Promise((resolve) => setTimeout(resolve, 1000));
    }
    message.info('诊断包仍在后台生成，可稍后重新进入页面查看');
  } catch (error) {
    message.error(error instanceof Error ? error.message : '诊断包生成失败');
  } finally {
    hide();
  }
}

const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: { schema: useLogFormSchema() },
  gridOptions: {
    columns: useLogColumns(),
    height: 'auto',
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          const expected = ++generation;
          const changed = JSON.stringify(filters) !== JSON.stringify(formValues);
          if (changed) { snapshotMaxId = undefined; cursor = 0; buffered = []; pendingCount.value = 0; }
          filters = { ...formValues };
          currentPage = page.currentPage;
          pageSize = page.pageSize;
          historical.value = currentPage !== 1 || Boolean(formValues.loggedAt?.length);
          if (snapshotMaxId === undefined) snapshotMaxId = await getNodeLogSnapshot(nodeId);
          if (expected !== generation) return { list: rows, total };
          const result = await getNodeLogPage({
            ...formValues,
            nodeId,
            snapshotMaxId,
            pageNo: page.currentPage,
            pageSize: page.pageSize,
          });
          if (expected === generation) {
            rows = result.list;
            total = result.total;
            cursor = Math.max(cursor, snapshotMaxId ?? 0);
          }
          return result;
        },
      },
    },
    rowConfig: { isHover: true, keyField: 'id' },
    toolbarConfig: { refresh: true, search: true },
  } as VxeTableGridOptions<AiVideoNodeLogApi.Log>,
});

function mergeIncoming() {
  if (historical.value || !buffered.length) return;
  const byId = new Map([...buffered, ...rows].map(row => [row.id, row]));
  rows = [...byId.values()].sort((a, b) => new Date(b.loggedAt).getTime() - new Date(a.loggedAt).getTime() || b.id - a.id).slice(0, pageSize);
  buffered = [];
  pendingCount.value = 0;
  snapshotMaxId = cursor;
  gridApi.setGridOptions({ data: rows, pagerConfig: { total } });
}
function stopRefresh() {
  generation++;
  pollEpoch++;
  if (refreshTimer) clearTimeout(refreshTimer);
  refreshTimer = undefined;
}
function startRefresh() {
  stopRefresh();
  disposed = false;
  const epoch = pollEpoch;
  const poll = async () => {
    const expected = generation;
    if (disposed || epoch !== pollEpoch) return;
    try {
    if (snapshotMaxId !== undefined && !paused.value && !refreshing && !historical.value && document.visibilityState === 'visible') {
      refreshing = true;
      try {
        const result = await getNodeLogPage({ ...filters, nodeId, afterId: cursor, pageNo: 1, pageSize: 100 }, true);
        if (expected !== generation || disposed || epoch !== pollEpoch) return;
        if (result.list.length) {
          cursor = Math.max(cursor, ...result.list.map(row => row.id));
          total += result.list.length;
          buffered = [...result.list, ...buffered].slice(0, 500);
          pendingCount.value += result.list.length;
          if (follow.value) mergeIncoming();
        }
        failures = 0;
        refreshError.value = '';
      } catch {
        if (expected !== generation || disposed || epoch !== pollEpoch) return;
        failures++;
        refreshError.value = '日志更新失败，保留当前内容并稍后重试。';
      } finally { refreshing = false; }
    }
    } finally {
      if (!disposed && epoch === pollEpoch) refreshTimer = setTimeout(poll, Math.min(60_000, 10_000 * 2 ** failures));
    }
  };
  refreshTimer = setTimeout(poll, 10_000);
}
watch(follow, value => { if (value) mergeIncoming(); });
function reloadLatest() {
  snapshotMaxId = undefined;
  cursor = 0;
  buffered = [];
  pendingCount.value = 0;
  void gridApi.query();
}
onMounted(() => {
  if (!Number.isInteger(nodeId) || nodeId <= 0) {
    message.error('节点 ID 无效');
    void router.replace('/ai-video/node');
    return;
  }
  startRefresh();
});
onActivated(startRefresh);
onDeactivated(() => { disposed = true; stopRefresh(); });
onBeforeUnmount(() => { disposed = true; stopRefresh(); });
</script>

<template>
  <component :is="embedded ? 'div' : Page" :auto-content-height="!embedded" :class="embedded ? 'h-[650px]' : ''">
    <ContextDrawer />
    <DiagnosticModal @success="waitForDiagnostic" />
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader v-if="!embedded" :title="`节点日志 · ${nodeId}`" description="按时间、级别、组件和任务定位运行异常；敏感字段已由服务端脱敏。" icon="lucide:terminal-square" status="Diagnostics" />
      <Alert
        message="最新页每 10 秒增量更新；历史页和指定时间范围保持不变。日志保留 DEBUG 1 天、INFO 3 天、WARN 7 天、ERROR 14 天。"
        show-icon
        type="info"
      />
      <Alert v-if="refreshError" :message="refreshError" show-icon type="warning" />
      <div class="min-h-0 flex-1">
        <Grid :table-title="`节点与任务日志 · Node ${nodeId}`">
          <template #toolbar-tools>
            <Space>
              <span>暂停刷新</span><Switch v-model:checked="paused" />
              <Button @click="reloadLatest">获取最新快照</Button>
              <span>跟随最新</span><Switch v-model:checked="follow" :disabled="historical" />
              <Button v-if="pendingCount" @click="mergeIncoming">显示 {{ pendingCount }} 条新日志</Button>
              <span>自动换行</span><Switch v-model:checked="wrapLines" />
              <Button
                v-if="canCreateDiagnostic"
                type="primary"
                @click="diagnosticModalApi.setData({ nodeId }).open()"
              >
生成诊断包
</Button>
            </Space>
          </template>
          <template #level="{ row }">
            <Tag :color="row.level === 'ERROR' ? 'error' : row.level === 'WARN' ? 'warning' : row.level === 'INFO' ? 'processing' : 'default'">
              {{ row.level }}
            </Tag>
          </template>
          <template #message="{ row }">
            <span class="font-mono" :class="wrapLines ? 'whitespace-pre-wrap break-all' : 'block truncate'">{{ row.message }}</span>
          </template>
          <template #actions="{ row }">
            <TableAction
              :actions="[{
                auth: ['ai-video:node-log:query'],
                icon: ACTION_ICON.VIEW,
                label: '上下文',
                onClick: openContext.bind(null, row),
                type: 'link',
              }]"
            />
          </template>
        </Grid>
      </div>
    </div>
  </component>
</template>
