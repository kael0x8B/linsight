<script lang="ts" setup>
import type { VbenFormSchema } from '#/adapter/form';
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoEventApi } from '#/api/ai-video/event';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';

import { Page, useVbenDrawer } from '@vben/common-ui';
import { useAccessStore } from '@vben/stores';

import { useWebSocket } from '@vueuse/core';
import { Alert, Badge, Button, Image, Tag } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getEventPage } from '#/api/ai-video/event';
import { AiPageHeader } from '#/components/ai-video';

import EventDetail from './modules/event-detail.vue';
import {
  eventTypes,
  evidenceText,
  firstEvidence,
  formatTime,
  recognitionResult,
  severityColor,
  severityText,
  statusColor,
  statusText,
} from './presentation';

const accessStore = useAccessStore();
const route = useRoute();
const error = ref('');
const newEvents = ref(false);
const [DetailDrawer, drawerApi] = useVbenDrawer({
  connectedComponent: EventDetail,
  destroyOnClose: true,
});
const options = (values: Record<string, string>) =>
  Object.entries(values).map(([value, label]) => ({ label, value }));
const schema: VbenFormSchema[] = [
  {
    fieldName: 'eventNo',
    label: '事件编号',
    component: 'Input',
    componentProps: { allowClear: true, placeholder: '输入事件编号' },
  },
  {
    fieldName: 'eventType',
    label: '事件类型',
    component: 'Select',
    componentProps: {
      allowClear: true,
      options: options(eventTypes),
      placeholder: '全部类型',
    },
  },
  {
    fieldName: 'severity',
    label: '事件等级',
    component: 'Select',
    componentProps: {
      allowClear: true,
      options: options(severityText),
      placeholder: '全部等级',
    },
  },
  {
    fieldName: 'status',
    label: '处理状态',
    component: 'Select',
    componentProps: {
      allowClear: true,
      options: options(statusText),
      placeholder: '全部状态',
    },
  },
];
const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: { schema },
  gridOptions: {
    height: 'auto',
    keepSource: true,
    cellConfig: { height: 82 },
    columns: [
      {
        field: 'media',
        title: '告警截图',
        width: 140,
        slots: { default: 'snapshot' },
      },
      {
        field: 'eventNo',
        title: '识别事件',
        minWidth: 220,
        fixed: 'left',
        slots: { default: 'identity' },
      },
      {
        field: 'occurredTime',
        title: '告警时间（北京时间）',
        width: 190,
        formatter: ({ cellValue }) => formatTime(cellValue),
      },
      {
        field: 'objectSnapshot',
        title: '识别结果',
        minWidth: 160,
        formatter: ({ row }) => recognitionResult(row.objectSnapshot),
      },
      {
        field: 'cameraName',
        title: '摄像头',
        minWidth: 210,
        formatter: ({ row }) => row.cameraName || `摄像头 ${row.cameraId}`,
      },
      {
        field: 'severity',
        title: '等级',
        width: 90,
        slots: { default: 'severity' },
      },
      {
        field: 'status',
        title: '处理状态',
        width: 105,
        slots: { default: 'status' },
      },
      {
        field: 'evidenceStatus',
        title: '证据',
        minWidth: 150,
        formatter: ({ cellValue }) => evidenceText[cellValue] || '待确认',
      },
      {
        field: 'actions',
        title: '操作',
        width: 110,
        fixed: 'right',
        slots: { default: 'actions' },
      },
    ],
    rowConfig: { keyField: 'id', isHover: true },
    toolbarConfig: { refresh: true, search: true },
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) => {
          error.value = '';
          newEvents.value = false;
          try {
            return await getEventPage({
              ...values,
              pageNo: page.currentPage,
              pageSize: page.pageSize,
              cameraId: Number(route.query.cameraId) || undefined,
            });
          } catch (cause) {
            error.value = '事件列表暂时加载失败，请刷新重试。';
            throw cause;
          }
        },
      },
    },
  } as VxeTableGridOptions<AiVideoEventApi.Event>,
});
function openDetail(row: AiVideoEventApi.Event) {
  drawerApi.setData({ id: row.id }).open();
}
const websocketUrl = computed(
  () =>
    `${`${import.meta.env.VITE_BASE_URL}/infra/ws`.replace('http', 'ws')}?token=${accessStore.refreshToken ?? ''}`,
);
const { close, data, status } = useWebSocket(websocketUrl, {
  autoReconnect: { delay: 3000, retries: Number.POSITIVE_INFINITY },
  heartbeat: true,
  immediate: Boolean(accessStore.refreshToken),
});
watch(data, (raw) => {
  if (!raw || raw === 'pong') return;
  try {
    if (JSON.parse(raw).type === 'ai-video-event') newEvents.value = true;
  } catch {
    /* Other message domains are ignored. */
  }
});
function openLinkedEvent() {
  const id = Number(route.query.eventId);
  if (Number.isSafeInteger(id) && id > 0) drawerApi.setData({ id }).open();
}
onMounted(openLinkedEvent);
watch(() => route.query.eventId, openLinkedEvent);
onBeforeUnmount(close);
</script>

<template>
  <Page auto-content-height>
    <DetailDrawer @changed="gridApi.query()" />
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="事件中心"
        description="查看告警画面、核实识别结果并完成处置。"
        icon="lucide:siren"
      >
        <template #extra>
          <Badge
            :status="status === 'OPEN' ? 'success' : 'warning'"
            :text="status === 'OPEN' ? '事件通知已连接' : '事件通知重连中'"
          /><Button type="primary" @click="gridApi.query()"> 刷新事件 </Button>
        </template>
      </AiPageHeader>
      <Alert v-if="error" :message="error" type="error" show-icon>
        <template #action>
          <Button @click="gridApi.query()">重试</Button>
        </template>
      </Alert>
      <Alert
        v-if="newEvents"
        message="有新的事件或证据更新"
        type="info"
        show-icon
      >
        <template #action>
          <Button size="small" @click="gridApi.query()"> 点击刷新 </Button>
        </template>
      </Alert>
      <Grid class="min-h-0 flex-1">
        <template #identity="{ row }">
          <div class="event-identity">
            <strong>{{ eventTypes[row.eventType] || '识别事件' }}</strong
            ><span>{{ row.eventNo }}</span>
          </div>
        </template>
        <template #snapshot="{ row }">
          <div class="event-thumb" @click="openDetail(row)">
            <Image
              v-if="
                firstEvidence(row, 'SNAPSHOT')?.accessUrl &&
                firstEvidence(row, 'SNAPSHOT')?.originalContentAvailable !==
                  false
              "
              :src="firstEvidence(row, 'SNAPSHOT')?.accessUrl"
              :preview="false"
            /><span v-else>{{
              firstEvidence(row, 'SNAPSHOT')?.originalContentAvailable === false
                ? '历史原图异常'
                : evidenceText[row.evidenceStatus] || '暂无截图'
            }}</span>
          </div>
        </template>
        <template #severity="{ row }">
          <Tag :color="severityColor[row.severity]">
            {{ severityText[row.severity] || '未分级' }}
          </Tag>
        </template>
        <template #status="{ row }">
          <Tag :color="statusColor[row.status]">
            {{ statusText[row.status] || '待确认' }}
          </Tag>
        </template>
        <template #actions="{ row }">
          <TableAction
            :actions="[
              {
                label: '查看详情',
                type: 'link',
                onClick: () => openDetail(row),
              },
            ]"
          />
        </template>
      </Grid>
    </div>
  </Page>
</template>

<style scoped>
.event-identity {
  display: grid;
  gap: 5px;
}

.event-identity strong {
  font-size: 13px;
}

.event-identity span {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.event-thumb {
  display: grid;
  place-items: center;
  width: 104px;
  height: 65px;
  overflow: hidden;
  font-size: 11px;
  color: #94a3b8;
  cursor: pointer;
  background: #0b111b;
  border-radius: 5px;
}

.event-thumb :deep(img) {
  width: 104px;
  height: 65px;
  object-fit: cover;
}
</style>
