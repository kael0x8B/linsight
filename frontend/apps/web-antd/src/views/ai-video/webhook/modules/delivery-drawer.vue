<script lang="ts" setup>
import type { AiVideoWebhookApi } from '#/api/ai-video/webhook';

import { ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { Descriptions, DescriptionsItem, Spin, Tag } from 'ant-design-vue';

import { getWebhookDelivery } from '#/api/ai-video/webhook';

const delivery = ref<AiVideoWebhookApi.Delivery>();
const loading = ref(false);

const [Drawer, drawerApi] = useVbenDrawer({
  async onOpenChange(open) {
    if (!open) {
      delivery.value = undefined;
      return;
    }
    const id = Number(drawerApi.getData<{ id: number }>()?.id);
    if (!id) return;
    loading.value = true;
    try {
      delivery.value = await getWebhookDelivery(id);
    } finally {
      loading.value = false;
    }
  },
});
</script>

<template>
  <Drawer class="w-[820px] max-w-[calc(100vw-32px)]" :footer="false" title="Webhook 投递详情">
    <Spin :spinning="loading">
      <template v-if="delivery">
        <Descriptions bordered :column="2" size="small">
          <DescriptionsItem label="状态"><Tag>{{ delivery.status }}</Tag></DescriptionsItem>
          <DescriptionsItem label="尝试次数">{{ delivery.attempts }}</DescriptionsItem>
          <DescriptionsItem label="幂等键">{{ delivery.idempotencyKey }}</DescriptionsItem>
          <DescriptionsItem label="消息 ID">{{ delivery.messageId }}</DescriptionsItem>
          <DescriptionsItem label="HTTP 状态">{{ delivery.responseStatus ?? '-' }}</DescriptionsItem>
          <DescriptionsItem label="耗时">{{ delivery.durationMs == null ? '-' : `${delivery.durationMs} ms` }}</DescriptionsItem>
          <DescriptionsItem :span="2" label="下次重试">{{ delivery.nextAttemptTime || '-' }}</DescriptionsItem>
          <DescriptionsItem :span="2" label="失败摘要">{{ delivery.lastError || '-' }}</DescriptionsItem>
        </Descriptions>
        <h4 class="mb-2 mt-5 font-medium">请求正文（固定业务事件，不含签名密钥）</h4>
        <pre class="max-h-72 overflow-auto rounded bg-[#111827] p-4 text-xs text-slate-200">{{ delivery.payload }}</pre>
        <h4 class="mb-2 mt-5 font-medium">响应摘要（已脱敏、最多 2,000 字符）</h4>
        <pre class="max-h-52 overflow-auto rounded bg-[#111827] p-4 text-xs text-slate-200">{{ delivery.responseBody || '-' }}</pre>
      </template>
    </Spin>
  </Drawer>
</template>
