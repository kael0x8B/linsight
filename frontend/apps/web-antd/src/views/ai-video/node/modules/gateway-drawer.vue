<script setup lang="ts">
import { ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenDrawer } from '@vben/common-ui';

import { platformGateway } from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';

import GatewayWorkbench from '../gateway-workbench.vue';

const nodeId = ref<number>();
const { hasAccessByCodes } = useAccess();
const [Drawer, drawer] = useVbenDrawer({
  title: $t('ai-video-gateway.m452a957e11'),
  class: 'w-[min(1400px,96vw)]',
  footer: false,
  onOpenChange(open) {
    const data = drawer.getData<{ id: number; name?: string }>();
    nodeId.value = open ? data.id : undefined;
    if (open)
      drawer.setState({
        title: data.name
          ? $t('ai-video-gateway.nodeWorkbench', { name: data.name })
          : $t('ai-video-gateway.m452a957e11'),
      });
  },
});
function transport<T>(
  action: string,
  payload?: Record<string, unknown>,
): Promise<T> {
  if (!nodeId.value)
    return Promise.reject(new Error($t('ai-video-gateway.mf45046c681')));
  return platformGateway<T>(nodeId.value, action, payload);
}
</script>
<template>
  <Drawer>
    <GatewayWorkbench
      v-if="nodeId"
      :key="nodeId"
      :transport="transport"
      :can-edit="
        hasAccessByCodes(['ai-video:node:operate']) &&
        hasAccessByCodes(['ai-video:task:update'])
      "
    />
  </Drawer>
</template>
