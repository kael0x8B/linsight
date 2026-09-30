<script setup lang="ts">
import type { AiVideoNode } from '#/api/ai-video/node';

import {
  computed,
  onActivated,
  onBeforeUnmount,
  onDeactivated,
  onMounted,
  ref,
} from 'vue';
import { useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime } from '@vben/utils';

import {
  Alert,
  Button,
  Empty,
  Input,
  Select,
  Skeleton,
  Tag,
} from 'ant-design-vue';

import { getNodeList } from '#/api/ai-video/node';
import { AiPageHeader, AiResourceGauge } from '#/components/ai-video';

import DeploymentDrawerComponent from './modules/deployment-drawer.vue';
import DeploymentHistoryDrawerComponent from './modules/deployment-history-drawer.vue';
import TokenModalComponent from './modules/token-modal.vue';
import { gatewayLocation, nodeResources, nodeStatus } from './presentation';

const router = useRouter();
const { hasAccessByCodes } = useAccess();
const [TokenModal, tokenApi] = useVbenModal({
  connectedComponent: TokenModalComponent,
  destroyOnClose: true,
});
const [DeploymentDrawer, deploymentApi] = useVbenDrawer({
  connectedComponent: DeploymentDrawerComponent,
  destroyOnClose: true,
});
const [HistoryDrawer, historyApi] = useVbenDrawer({
  connectedComponent: DeploymentHistoryDrawerComponent,
  destroyOnClose: true,
});
const error = ref('');
const loading = ref(true);
const nodes = ref<AiVideoNode[]>([]);
const search = ref('');
const status = ref<number>();
const online = computed(
  () => nodes.value.filter((n) => n.onlineStatus === 1).length,
);
const filtered = computed(() =>
  nodes.value.filter(
    (n) =>
      (status.value === undefined || n.onlineStatus === status.value) &&
      `${n.name} ${n.code} ${n.ipAddress ?? ''}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()),
  ),
);
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let active = false;
async function refresh(quiet = false) {
  if (!active) return;
  clearTimeout(timer);
  const request = ++generation;
  if (!quiet) loading.value = true;
  try {
    const result = await getNodeList(quiet);
    if (request === generation) {
      nodes.value = result;
      error.value = '';
    }
  } catch {
    if (request === generation)
      error.value = '网关状态更新失败，当前显示上次结果。';
  } finally {
    if (request === generation && active) {
      loading.value = false;
      timer = setTimeout(() => {
        if (document.visibilityState === 'visible') void refresh(true);
        else schedule();
      }, 10_000);
    }
  }
}
function schedule() {
  clearTimeout(timer);
  timer = setTimeout(() => void refresh(true), 10_000);
}
function start() {
  active = true;
  void refresh(nodes.value.length > 0);
}
function stop() {
  active = false;
  generation++;
  clearTimeout(timer);
}
onMounted(start);
onActivated(start);
onDeactivated(stop);
onBeforeUnmount(stop);
</script>
<template>
  <Page>
    <TokenModal /><DeploymentDrawer @success="refresh()" /><HistoryDrawer />
    <div class="ai-page ai-page-stack">
      <AiPageHeader
        title="边缘网关"
        description="选择网关，统一管理识别算法、模型和设备运行。"
        icon="lucide:server-cog"
      >
        <template #extra>
          <div class="flex flex-wrap gap-2">
            <Button
              v-if="hasAccessByCodes(['ai-video:node:create'])"
              @click="tokenApi.open()"
            >
              注册令牌
            </Button>
            <Button
              v-if="hasAccessByCodes(['ai-video:node:query'])"
              @click="historyApi.open()"
            >
              全部部署记录
            </Button>
            <Button
              v-if="hasAccessByCodes(['ai-video:node:deploy'])"
              type="primary"
              @click="deploymentApi.setData({}).open()"
            >
              <IconifyIcon icon="lucide:plus" />添加网关
            </Button>
          </div>
        </template>
      </AiPageHeader>
      <div
        class="flex flex-wrap items-center justify-between gap-4 rounded-xl border bg-card p-4"
      >
        <div class="flex items-center gap-5 text-sm">
          <span
            >共 <b class="text-lg">{{ nodes.length }}</b> 个网关</span
          ><span class="text-green-600">{{ online }} 在线</span
          ><span class="text-muted-foreground"
            >{{ nodes.length - online }} 离线 / 未知</span
          >
        </div>
        <div class="flex flex-wrap gap-2">
          <Input
            v-model:value="search"
            allow-clear
            placeholder="搜索名称、编码或 IP"
            aria-label="搜索网关"
            class="!w-60"
          /><Select
            v-model:value="status"
            allow-clear
            placeholder="全部状态"
            aria-label="网关状态"
            class="w-32"
            :options="[
              { label: '在线', value: 1 },
              { label: '离线', value: 2 },
              { label: '未知', value: 0 },
            ]"
          /><Button :loading="loading" @click="refresh()">刷新</Button>
        </div>
      </div>
      <Alert v-if="error" :message="error" show-icon type="warning" />
      <Skeleton v-if="loading && !nodes.length" active />
      <div
        v-else-if="filtered.length"
        class="grid gap-5 md:grid-cols-2 2xl:grid-cols-3"
      >
        <button
          v-for="node in filtered"
          :key="node.id"
          type="button"
          class="gateway-card group rounded-xl border bg-card p-6 text-left transition hover:border-primary focus-visible:outline focus-visible:outline-2 focus-visible:outline-primary"
          :aria-label="`管理网关 ${node.name}`"
          @click="router.push(gatewayLocation(node.id))"
        >
          <div class="flex items-start gap-3">
            <span class="rounded-lg bg-primary/10 p-3 text-primary"
              ><IconifyIcon icon="lucide:server" class="size-6"
            /></span>
            <div class="min-w-0 flex-1">
              <h2 class="truncate text-base font-semibold" :title="node.name">
                {{ node.name }}
              </h2>
              <p class="mt-1 truncate text-xs text-muted-foreground">
                {{ node.ipAddress || 'IP 未上报' }} · {{ node.code }}
              </p>
            </div>
            <Tag :color="node.onlineStatus === 1 ? 'green' : 'default'">
              {{ nodeStatus(node) }}
            </Tag>
          </div>
          <div
            class="my-6 grid grid-cols-2 gap-x-6 gap-y-4"
            :class="{ 'opacity-50': node.onlineStatus !== 1 }"
          >
            <AiResourceGauge
              label="CPU"
              :value="nodeResources(node.resourceSnapshot).cpu"
            /><AiResourceGauge
              label="内存"
              :value="nodeResources(node.resourceSnapshot).memory"
            /><AiResourceGauge
              label="GPU / NPU"
              :value="nodeResources(node.resourceSnapshot).accelerator"
            /><AiResourceGauge
              label="磁盘"
              :value="nodeResources(node.resourceSnapshot).disk"
            />
          </div>
          <p
            v-if="nodeResources(node.resourceSnapshot).cleanupSummary"
            class="mb-4 text-xs"
            :class="
              nodeResources(node.resourceSnapshot).cleanupStatus ===
              'STILL_HIGH'
                ? 'text-red-600'
                : 'text-green-600'
            "
          >
            {{ nodeResources(node.resourceSnapshot).cleanupSummary }}
          </p>
          <div
            class="flex flex-wrap justify-between gap-2 border-t pt-4 text-sm"
          >
            <span class="text-muted-foreground"
              >{{ node.taskCount ?? '—' }} 个任务 ·
              {{ node.modelCount ?? '—' }} 个模型</span
            ><span class="flex items-center gap-1 font-medium text-primary"
              >进入管理<IconifyIcon icon="lucide:arrow-right"
            /></span>
          </div>
          <p class="mt-3 truncate text-xs text-muted-foreground">
            {{
              node.onlineStatus === 1 ? '最近心跳' : '上次心跳（资源为历史值）'
            }}：{{
              node.lastHeartbeatTime
                ? formatDateTime(node.lastHeartbeatTime)
                : '尚未收到'
            }}
          </p>
        </button>
      </div>
      <Empty
        v-else
        :description="nodes.length ? '没有符合条件的网关' : '暂无边缘网关'"
      >
        <Button
          v-if="!nodes.length && hasAccessByCodes(['ai-video:node:deploy'])"
          type="primary"
          @click="deploymentApi.setData({}).open()"
        >
          添加网关
        </Button>
      </Empty>
    </div>
  </Page>
</template>
<style scoped>
.gateway-card {
  cursor: pointer;
  box-shadow: 0 2px 8px rgb(0 0 0 / 2%);
}

.gateway-card:hover {
  box-shadow: 0 6px 22px rgb(0 0 0 / 5%);
}
</style>
