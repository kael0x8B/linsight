<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoWebhookApi } from '#/api/ai-video/webhook';

import { ref } from 'vue';

import { confirm, Page, useVbenDrawer } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Badge,
  Button,
  message,
  Progress,
  TabPane,
  Tabs,
  Tag,
} from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  deleteWebhook,
  getWebhookDeliveryPage,
  getWebhookPage,
  replayWebhookDelivery,
  testWebhook,
  updateWebhookStatus,
} from '#/api/ai-video/webhook';
import { AiPageHeader } from '#/components/ai-video';

import {
  deliveryColumns,
  deliverySearchSchema,
  endpointColumns,
  endpointSearchSchema,
} from './data';
import DeliveryDrawerComponent from './modules/delivery-drawer.vue';
import WebhookDrawerComponent from './modules/webhook-drawer.vue';

const activeTab = ref('endpoints');

const [WebhookDrawer, webhookDrawerApi] = useVbenDrawer({
  connectedComponent: WebhookDrawerComponent,
  destroyOnClose: true,
});
const [DeliveryDrawer, deliveryDrawerApi] = useVbenDrawer({
  connectedComponent: DeliveryDrawerComponent,
  destroyOnClose: true,
});

const [EndpointGrid, endpointGridApi] = useVbenVxeGrid({
  formOptions: { schema: endpointSearchSchema(), submitOnChange: true },
  gridOptions: {
    columns: endpointColumns(),
    height: 'auto',
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          getWebhookPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          }),
      },
    },
    rowConfig: { isHover: true, keyField: 'id' },
    toolbarConfig: { refresh: true },
  } as VxeTableGridOptions<AiVideoWebhookApi.Endpoint>,
});

const [DeliveryGrid, deliveryGridApi] = useVbenVxeGrid({
  formOptions: { schema: deliverySearchSchema(), submitOnChange: true },
  gridOptions: {
    columns: deliveryColumns(),
    height: 'auto',
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) =>
          getWebhookDeliveryPage({
            pageNo: page.currentPage,
            pageSize: page.pageSize,
            ...formValues,
          }),
      },
    },
    rowConfig: { isHover: true, keyField: 'id' },
    toolbarConfig: { refresh: true },
  } as VxeTableGridOptions<AiVideoWebhookApi.Delivery>,
});

function openCreate() {
  webhookDrawerApi.setData(undefined).open();
}

function openEdit(row: AiVideoWebhookApi.Endpoint) {
  webhookDrawerApi.setData(row).open();
}

async function handleToggle(row: AiVideoWebhookApi.Endpoint) {
  const target = row.status === 0 ? 1 : 0;
  await updateWebhookStatus(row.id, target);
  message.success(target === 0 ? 'Webhook 已启用' : 'Webhook 已停用');
  await endpointGridApi.query();
}

async function handleTest(row: AiVideoWebhookApi.Endpoint) {
  const deliveryId = await testWebhook(row.id);
  message.success(`模拟事件已进入可靠投递队列，投递 ID：${deliveryId}`);
  activeTab.value = 'deliveries';
  await deliveryGridApi.query();
}

async function handleDelete(row: AiVideoWebhookApi.Endpoint) {
  await confirm(
    `确认删除 Webhook“${row.name}”吗？历史投递记录会保留用于审计。`,
  );
  await deleteWebhook(row.id);
  message.success('Webhook 已删除');
  await endpointGridApi.query();
}

function openDelivery(row: AiVideoWebhookApi.Delivery) {
  deliveryDrawerApi.setData({ id: row.id }).open();
}

async function handleReplay(row: AiVideoWebhookApi.Delivery) {
  await confirm(
    `确认重放死信投递 ${row.id} 吗？业务事件正文与幂等键保持不变。`,
  );
  await replayWebhookDelivery(row.id);
  message.success('死信已重新进入投递队列');
  await deliveryGridApi.query();
}

function scopeText(row: AiVideoWebhookApi.Endpoint) {
  const types =
    row.eventTypes.length > 0 ? row.eventTypes.join(', ') : '全部事件';
  const levels =
    row.severities.length > 0 ? row.severities.join(', ') : '全部等级';
  return `${types} · ${levels}`;
}
</script>

<template>
  <Page auto-content-height>
    <WebhookDrawer @success="endpointGridApi.query" />
    <DeliveryDrawer />
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="Webhook 集成"
        description="管理事件订阅与投递记录。"
        icon="lucide:webhook"
      >
        <template #extra>
          <Button type="primary" @click="openCreate">
            <IconifyIcon icon="lucide:plus" />新增端点
          </Button>
        </template>
      </AiPageHeader>

      <Tabs v-model:active-key="activeTab" class="min-h-0 flex-1">
        <TabPane key="endpoints" tab="端点">
          <EndpointGrid table-title="Webhook 端点">
            <template #status="{ row }">
              <Badge
                :status="row.status === 0 ? 'success' : 'default'"
                :text="row.status === 0 ? '启用' : '停用'"
              />
            </template>
            <template #scope="{ row }">
              <span :title="scopeText(row)">{{ scopeText(row) }}</span>
            </template>
            <template #successRate="{ row }">
              <Progress
                v-if="row.successRate != null"
                :percent="row.successRate"
                :show-info="false"
                size="small"
              />
              <span>{{
                row.successRate == null ? '-' : `${row.successRate}%`
              }}</span>
            </template>
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    auth: ['ai-video:webhook:update'],
                    label: '编辑',
                    onClick: openEdit.bind(null, row),
                    type: 'link',
                  },
                ]"
                :drop-down-actions="[
                  {
                    auth: ['ai-video:webhook:test'],
                    disabled: row.status !== 0,
                    label: '模拟测试',
                    onClick: handleTest.bind(null, row),
                    type: 'link',
                  },
                  {
                    auth: ['ai-video:webhook:update-status'],
                    label: row.status === 0 ? '停用' : '启用',
                    onClick: handleToggle.bind(null, row),
                    type: 'link',
                  },
                  {
                    auth: ['ai-video:webhook:delete'],
                    danger: true,
                    label: '删除',
                    onClick: handleDelete.bind(null, row),
                    type: 'link',
                  },
                ]"
              />
            </template>
          </EndpointGrid>
        </TabPane>
        <TabPane key="deliveries" tab="投递记录">
          <DeliveryGrid table-title="可靠投递与死信">
            <template #status="{ row }">
              <Tag
                :color="
                  row.status === 'SUCCEEDED'
                    ? 'success'
                    : row.status === 'DEAD'
                      ? 'error'
                      : row.status === 'RETRY'
                        ? 'warning'
                        : 'processing'
                "
              >
                {{ row.status }}
              </Tag>
            </template>
            <template #duration="{ row }">
              {{ row.durationMs == null ? '-' : `${row.durationMs} ms` }}
            </template>
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    auth: ['ai-video:webhook:query'],
                    label: '详情',
                    onClick: openDelivery.bind(null, row),
                    type: 'link',
                  },
                  {
                    auth: ['ai-video:webhook:replay'],
                    disabled: row.status !== 'DEAD',
                    label: '重放',
                    onClick: handleReplay.bind(null, row),
                    type: 'link',
                  },
                ]"
              />
            </template>
          </DeliveryGrid>
        </TabPane>
      </Tabs>
    </div>
  </Page>
</template>
