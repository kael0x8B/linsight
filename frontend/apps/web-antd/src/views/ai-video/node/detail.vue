<script setup lang="ts">
import type { AiVideoNode } from '#/api/ai-video/node';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { confirm, Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime } from '@vben/utils';

import { Alert, Button, Descriptions, DescriptionsItem, Empty, Input, message, Skeleton, TabPane, Tabs, Tag } from 'ant-design-vue';

import { TableAction } from '#/adapter/vxe-table';
import { deleteNode, getNodeList, restartNode, rollbackNode, shutdownNode } from '#/api/ai-video/node';
import { platformGateway } from '#/api/ai-video/node/gateway';
import { AiResourceGauge } from '#/components/ai-video';
import NodeLogs from '#/views/ai-video/node-logs/index.vue';

import GatewayWorkbench from './gateway-workbench.vue';
import AlgorithmsPanel from './modules/algorithms-panel.vue';
import DeploymentDrawerComponent from './modules/deployment-drawer.vue';
import DeploymentHistory from './modules/deployment-history-drawer.vue';
import HistoryPanel from './modules/history-drawer.vue';
import ModelsPanel from './modules/models-panel.vue';
import UpgradeModalComponent from './modules/upgrade-modal.vue';
import { nodeResources, nodeStatus } from './presentation';

const route = useRoute(); const router = useRouter();
const { hasAccessByCodes: can } = useAccess();
const nodeId = computed(() => Number(route.params.id));
const error = ref(''); const loading = ref(true); const node = ref<AiVideoNode>();
const activeTab = computed({ get: () => String(route.query.tab || 'algorithms'), set: tab => { void router.replace({ query: { ...route.query, tab } }); } });
const localPassword = ref('');
const [AccessModal, accessApi] = useVbenModal({ title: '本地访问设置', async onConfirm() {
  if (localPassword.value.length < 12 || localPassword.value.length > 256) { message.warning('密码长度须为 12–256 位'); return; }
  accessApi.lock();
  try { await transport('access.password', { password: localPassword.value }); localPassword.value = ''; accessApi.close(); message.success('本地访问密码已更新'); }
  finally { accessApi.unlock(); }
}, onClosed() { localPassword.value = ''; } });
const resources = computed(() => nodeResources(node.value?.resourceSnapshot));
const [DeploymentDrawer, deploymentApi] = useVbenDrawer({ connectedComponent: DeploymentDrawerComponent, destroyOnClose: true });
const [UpgradeModal, upgradeApi] = useVbenModal({ connectedComponent: UpgradeModalComponent, destroyOnClose: true });
let disposed = false; let generation = 0; let timer: ReturnType<typeof setTimeout> | undefined;
async function refresh(quiet = false) {
  clearTimeout(timer); const expected = ++generation; if (!quiet) loading.value = true;
  try { const list = await getNodeList(quiet); if (!disposed && expected === generation) { node.value = list.find(n => n.id === nodeId.value); error.value = ''; } }
  catch { if (expected === generation) error.value = '网关信息更新失败，请重试。'; }
  finally { if (!disposed && expected === generation) { loading.value = false; timer = setTimeout(() => void refresh(true), 10_000); } }
}
const transport = <T,>(action: string, payload?: Record<string, unknown>) => platformGateway<T>(nodeId.value, action, payload);
async function operate(action: 'delete' | 'restart' | 'rollback' | 'shutdown') {
  if (!node.value) return;
  const descriptions = { delete: '删除离线网关并使其凭据失效？部署和日志历史会保留，此操作不可直接恢复。', restart: '重启网关？识别任务、画面及上传会短暂中断。', shutdown: '关闭网关？所有识别将停止，需要现场重新开机。', rollback: '回滚签名 Agent？需要重启激活，不会恢复 Runtime 或源码部署。' };
  try { await confirm(`“${node.value.name}”：${descriptions[action]}`); } catch { return; }
  await ({ delete: deleteNode, restart: restartNode, rollback: rollbackNode, shutdown: shutdownNode })[action](nodeId.value);
  message.success(action === 'delete' ? '网关已删除' : '操作已提交，可在操作记录中查看结果');
  if (action === 'delete') await router.push('/ai-video/node'); else { activeTab.value = 'operations'; await refresh(); }
}
onMounted(() => void refresh()); onBeforeUnmount(() => { disposed = true; generation++; clearTimeout(timer); });
</script>
<template>
  <Page>
    <AccessModal><p class="mb-4">设置后可直接访问网关地址，独立管理当前网关。</p><a v-if="node?.ipAddress" :href="`http://${node.ipAddress}:48901`" target="_blank" rel="noopener noreferrer" class="mb-4 block text-primary">打开本地工作台</a><Input.Password v-model:value="localPassword" autocomplete="new-password" placeholder="设置 12–256 位本地密码" /></AccessModal>
    <DeploymentDrawer @success="refresh()" /><UpgradeModal @success="refresh()" />
    <div class="ai-page ai-page-stack">
      <div class="flex flex-wrap items-center justify-between gap-3"><Button type="text" @click="router.push('/ai-video/node')"><IconifyIcon icon="lucide:arrow-left" />全部网关</Button><Button :loading="loading" @click="refresh()">刷新网关信息</Button></div>
      <Alert v-if="error" :message="error" type="error" show-icon />
      <Skeleton v-if="loading && !node" active />
      <Empty v-else-if="!node" description="网关不存在或无权访问" />
      <template v-else>
        <section class="rounded-xl border bg-card p-5">
          <div class="flex flex-wrap items-start justify-between gap-4">
            <div class="flex gap-3"><span class="rounded-xl bg-primary/10 p-3 text-primary"><IconifyIcon icon="lucide:server-cog" class="size-7" /></span><div><div class="flex flex-wrap items-center gap-3"><h1 class="text-xl font-semibold">{{ node.name }}</h1><Tag :color="node.onlineStatus === 1 ? 'green' : 'default'">{{ nodeStatus(node) }}</Tag></div><p class="mt-2 text-sm text-muted-foreground">{{ node.ipAddress || 'IP 未上报' }} · {{ node.code }} · {{ node.previewTunnelConnected ? '管理通道已连接' : '管理通道未连接' }}</p></div></div>
            <div class="flex flex-wrap items-center gap-2">
<Button v-if="can(['ai-video:node:operate']) && can(['ai-video:task:update'])" :disabled="!node.previewTunnelConnected" @click="accessApi.open()">本地访问</Button><Button v-if="can(['ai-video:node:deploy'])" @click="deploymentApi.setData({ mode: 'REDEPLOY', node }).open()">在线升级</Button><TableAction
:actions="[]" :drop-down-actions="[
              { label: '部署回滚', auth: ['ai-video:node:deploy'], onClick: () => deploymentApi.setData({ mode: 'ROLLBACK', node }).open() },
              { label: '上传签名升级包', auth: ['ai-video:node:upgrade'], disabled: node.onlineStatus !== 1 || resources.data.activationGuard !== 'v1', onClick: () => upgradeApi.setData(node).open() },
              { label: 'Agent 回滚', auth: ['ai-video:node:rollback'], disabled: node.onlineStatus !== 1 || !resources.data.agentRollbackAvailable, onClick: () => operate('rollback') },
              { label: '重启网关', auth: ['ai-video:node:operate'], disabled: node.onlineStatus !== 1, onClick: () => operate('restart') },
              { label: '关闭网关', danger: true, auth: ['ai-video:node:operate'], disabled: node.onlineStatus !== 1, onClick: () => operate('shutdown') },
              { label: '删除网关', danger: true, auth: ['ai-video:node:delete'], disabled: node.onlineStatus === 1, onClick: () => operate('delete') },
            ]"
/>
</div>
          </div>
          <div class="mt-6 grid gap-5 sm:grid-cols-2 xl:grid-cols-4" :class="{ 'opacity-50': node.onlineStatus !== 1 }"><AiResourceGauge label="CPU" :value="resources.cpu" /><AiResourceGauge label="内存" :value="resources.memory" /><AiResourceGauge label="GPU / NPU" :value="resources.gpu" /><AiResourceGauge label="磁盘" :value="resources.disk" /></div>
          <details class="mt-5 border-t pt-3"><summary class="cursor-pointer text-sm text-muted-foreground">网关信息 · {{ node.agentVersion || '版本未上报' }} · {{ node.onlineStatus === 1 ? '最近心跳' : '上次心跳，资源为历史值' }} {{ node.lastHeartbeatTime ? formatDateTime(node.lastHeartbeatTime) : '未知' }}</summary><Descriptions class="mt-4" :column="2" size="small"><DescriptionsItem label="主机名">{{ node.hostName || '未上报' }}</DescriptionsItem><DescriptionsItem label="版本">{{ node.agentVersion || '未上报' }}</DescriptionsItem><DescriptionsItem label="任务 / 模型">{{ node.taskCount ?? '—' }} / {{ node.modelCount ?? '—' }}</DescriptionsItem><DescriptionsItem label="本地访问">{{ node.ipAddress ? `http://${node.ipAddress}:48901` : 'IP 未上报' }}</DescriptionsItem></Descriptions></details>
        </section>
        <Alert v-if="node.onlineStatus !== 1" message="网关离线，显示最近记录。恢复连接后会继续同步；现场可使用本地工作台。" type="warning" show-icon />
        <section class="rounded-xl border bg-card px-5 pb-5">
          <Tabs v-model:active-key="activeTab" :destroy-inactive-tab-pane="true">
            <TabPane key="algorithms" tab="识别算法"><AlgorithmsPanel v-if="can(['ai-video:camera:query']) && can(['ai-video:task:query'])" :key="node.id" :node="node" /><Empty v-else description="需要摄像头和任务查询权限" /></TabPane>
            <TabPane key="models" tab="模型管理"><ModelsPanel v-if="can(['ai-video:model:query'])" :key="node.id" :node="node" /><Empty v-else description="暂无模型查询权限" /></TabPane>
            <TabPane key="events" tab="本地事件"><GatewayWorkbench :key="node.id" section="events" :transport="transport" :can-edit="false" /></TabPane>
            <TabPane key="logs" tab="网关日志"><NodeLogs v-if="can(['ai-video:node-log:query'])" :key="node.id" embedded :gateway-id="node.id" /><Empty v-else description="暂无网关日志查询权限" /></TabPane>
            <TabPane key="deployments" tab="部署记录"><DeploymentHistory :key="node.id" embedded :gateway-id="node.id" /></TabPane>
            <TabPane key="operations" tab="操作记录"><HistoryPanel :key="node.id" embedded :gateway="node" /></TabPane>
          </Tabs>
        </section>
      </template>
    </div>
  </Page>
</template>
