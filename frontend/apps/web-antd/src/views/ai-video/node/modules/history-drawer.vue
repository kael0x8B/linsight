<script lang="ts" setup>
import type { AiVideoNode, AiVideoNodeCommand, AiVideoNodeUpgrade } from '#/api/ai-video/node';

import { onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, useVbenDrawer } from '@vben/common-ui';
import { formatDateTime } from '@vben/utils';

import { Alert, Button, TabPane, Tabs, Tag } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import { getNodeCommandList, getNodeUpgradeList, restartNode } from '#/api/ai-video/node';

import DeploymentHistoryDrawer from './deployment-history-drawer.vue';

const props = defineProps<{ embedded?: boolean; gateway?: AiVideoNode }>();
const node = ref<AiVideoNode>();
const error = ref('');
const activeTab = ref('commands');
const { hasAccessByCodes } = useAccess();
const awaitingActivation = ref(false);
const [SourceHistory, sourceHistoryApi] = useVbenDrawer({ connectedComponent: DeploymentHistoryDrawer, destroyOnClose: true });
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const statusLabels: Record<string, string> = {
  QUEUED: '等待执行', SENT: '已下发', RUNNING: '执行中', SUCCEEDED: '执行请求已完成', FAILED: '失败', EXPIRED: '已超时',
  AWAITING_ACTIVATION: '待重启激活', VERIFYING: '等待新版本健康确认',
};
const commandLabels: Record<string, string> = {
  RESTART_NODE: '重启节点', SHUTDOWN_NODE: '关闭节点', UPGRADE_AGENT: '升级 Agent', ROLLBACK_AGENT: '回滚 Agent',
  START_TASK: '启动任务', STOP_TASK: '停止任务', DEPLOY_MODEL: '部署模型', UNINSTALL_MODEL: '卸载模型', RUN_MODEL_TEST: '测试模型', APPLY_TASK_SETTINGS: '应用任务配置',
};
function commandSummary(row: AiVideoNodeCommand) {
  if (row.errorMessage) return row.errorMessage;
  if (!row.resultSummary) return '等待节点回报';
  try {
    const report = JSON.parse(row.resultSummary) as { result?: { accepted?: boolean; currentVersion?: string }; stage?: string; };
    if (report.result?.accepted) return row.commandType === 'SHUTDOWN_NODE' ? '关机请求已提交，请确认节点离线' : '重启请求已提交，请确认心跳恢复';
    if (report.result?.currentVersion) return `版本目录已切换为 ${report.result.currentVersion}，重启后生效`;
    const stages: Record<string, string> = { READY: '模型已就绪', REMOVED: '模型已卸载', COMPLETED: '已完成', RUNNING: '任务已启动', STOPPED: '任务已停止', SETTINGS_APPLIED: '配置已应用' };
    return stages[report.stage ?? ''] ?? report.stage ?? '节点已回报结果';
  } catch { return '节点已回报结果'; }
}
const dateFormatter = ({ cellValue }: { cellValue: string }) => cellValue ? formatDateTime(cellValue) : '—';
const [UpgradeGrid, upgradeGrid] = useVbenVxeGrid<AiVideoNodeUpgrade>({
  gridOptions: {
    columns: [
      { field: 'action', title: '动作', width: 80, formatter: ({ cellValue }: { cellValue: string }) => cellValue === 'UPGRADE' ? '升级' : '回滚' },
      { field: 'targetVersion', title: '目标版本', minWidth: 120 },
      { field: 'status', title: '状态', width: 150, slots: { default: 'status' } },
      { field: 'stage', title: '阶段', width: 120 },
      { field: 'createTime', title: '创建时间', width: 175, formatter: dateFormatter },
      { field: 'errorMessage', title: '结果', minWidth: 240, formatter: ({ row }: { row: AiVideoNodeUpgrade }) => row.errorMessage || row.resultSummary || '—' },
    ],
    data: [], height: 320, pagerConfig: { enabled: false }, rowConfig: { keyField: 'id' },
  },
});
const [CommandGrid, commandGrid] = useVbenVxeGrid<AiVideoNodeCommand>({
  gridOptions: {
    columns: [
      { field: 'commandType', title: '命令', width: 120, formatter: ({ cellValue }: { cellValue: string }) => commandLabels[cellValue] || cellValue },
      { field: 'status', title: '状态', width: 150, slots: { default: 'status' } },
      { field: 'createTime', title: '创建时间', width: 175, formatter: dateFormatter },
      { field: 'finishTime', title: '完成时间', width: 175, formatter: dateFormatter },
      { field: 'errorMessage', title: '结果 / 诊断', minWidth: 260, formatter: ({ row }: { row: AiVideoNodeCommand }) => commandSummary(row) },
      { field: 'commandId', title: '命令 ID', width: 290 },
    ],
    data: [], height: 360, pagerConfig: { enabled: false }, rowConfig: { keyField: 'commandId' },
  },
});
function stop() {
  generation++;
  if (timer) clearTimeout(timer);
}
async function loadRecords() {
  if (!node.value) return;
  if (timer) clearTimeout(timer);
  const current = ++generation;
  let active = false;
  try {
    const records = activeTab.value === 'upgrades' ? await getNodeUpgradeList(node.value.id) : await getNodeCommandList(node.value.id);
    if (current !== generation) return;
    error.value = '';
    active = records.some(row => ['AWAITING_ACTIVATION', 'QUEUED', 'RUNNING', 'SENT', 'VERIFYING'].includes(row.status));
    if (activeTab.value === 'upgrades') {
      awaitingActivation.value = records.some(row => row.status === 'AWAITING_ACTIVATION');
      upgradeGrid.setGridOptions({ data: records as AiVideoNodeUpgrade[] });
    } else commandGrid.setGridOptions({ data: records as AiVideoNodeCommand[] });
  } catch {
    if (current === generation) error.value = '记录刷新失败，保留已有结果；请点击重试。';
  } finally {
    if (current === generation && active) timer = setTimeout(loadRecords, 3000);
  }
}
const [Drawer, drawerApi] = useVbenDrawer({
  footer: false,
  async onOpenChange(open) {
    stop();
    if (!open) { node.value = undefined; return; }
    node.value = drawerApi.getData<AiVideoNode>();
    await loadRecords();
  },
});
onMounted(() => { if (props.embedded) { node.value = props.gateway; void loadRecords(); } });
onBeforeUnmount(stop);
watch(activeTab, loadRecords);
async function activateUpgrade() {
  if (!node.value) return;
  await confirm('确认重启该节点以激活已安装的 Agent？该节点上的任务会短暂中断，失败时启动器将恢复原版本。');
  await restartNode(node.value.id);
  await loadRecords();
}
</script>
<template>
  <component :is="embedded ? 'div' : Drawer" :class="embedded ? '' : 'w-[1080px] max-w-[calc(100vw-32px)]'">
    <SourceHistory />
    <Button v-if="!embedded" class="mb-3" @click="sourceHistoryApi.setData({ nodeId: node?.id }).open()">部署记录</Button>
    <Alert message="只刷新当前标签页的活动记录，完成后停止。主机关机/重启命令的成功仅表示请求已提交；升级成功须通过新版本心跳确认。" show-icon type="info" />
    <Alert v-if="error" class="mt-3" :message="error" show-icon type="warning"><template #action><Button @click="loadRecords">重试</Button></template></Alert>
    <Tabs v-model:active-key="activeTab">
      <TabPane key="commands" tab="节点命令（最近 50 条）">
        <CommandGrid><template #status="{ row }"><Tag :color="row.status === 'FAILED' || row.status === 'EXPIRED' ? 'error' : row.status === 'SUCCEEDED' ? 'success' : 'processing'">{{ statusLabels[row.status] || row.status }}</Tag></template></CommandGrid>
      </TabPane>
      <TabPane key="upgrades" tab="签名升级与回滚">
        <Button v-if="awaitingActivation && hasAccessByCodes(['ai-video:node:operate'])" class="mb-3" type="primary" @click="activateUpgrade">重启并验证新版本</Button>
        <UpgradeGrid><template #status="{ row }"><Tag :color="row.status === 'FAILED' ? 'error' : row.stage === 'HEALTH_CONFIRMED' ? 'success' : 'processing'">{{ row.status === 'SUCCEEDED' ? row.stage === 'HEALTH_CONFIRMED' ? '目标版本健康已确认' : '历史执行完成（未验证健康）' : statusLabels[row.status] || row.status }}</Tag></template></UpgradeGrid>
      </TabPane>
    </Tabs>
  </component>
</template>
