<script lang="ts" setup>
import type { AiVideoSettingsApi } from '#/api/ai-video/settings';

import { computed, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, Page } from '@vben/common-ui';

import {
  Alert,
  Button,
  Card,
  message,
  RadioButton,
  RadioGroup,
  Select,
  Space,
  Table,
  Tag,
} from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import {
  getGlobalSettings,
  getGlobalSettingsVersions,
  saveGlobalSettings,
} from '#/api/ai-video/settings';
import { getTaskPage } from '#/api/ai-video/task';

const { hasAccessByCodes } = useAccess();
const current = ref<AiVideoSettingsApi.Current>();
const versions = ref<AiVideoSettingsApi.Version[]>([]);
const runningTasks = ref<{ label: string; value: number }[]>([]);
const applyScope = ref<AiVideoSettingsApi.SaveRequest['applyScope']>('NEW_TASKS');
const grayTaskIds = ref<number[]>([]);
const saving = ref(false);

const [VideoForm, videoApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 140 },
  layout: 'horizontal',
  schema: [
    {
      component: 'InputNumber',
      componentProps: { max: 10, min: 0.1, step: 0.1 },
      fieldName: 'defaultFps',
      label: '默认分析 FPS',
      rules: z.number().min(0.1).max(10),
    },
  ],
  showDefaultActions: false,
});
const [InferenceForm, inferenceApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 140 },
  layout: 'horizontal',
  schema: [
    {
      component: 'InputNumber',
      componentProps: { max: 1, min: 0.01, step: 0.01 },
      fieldName: 'defaultConfidence',
      label: '默认置信度',
      rules: z.number().min(0.01).max(1),
    },
  ],
  showDefaultActions: false,
});
const [EvidenceForm, evidenceApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 150 },
  layout: 'horizontal',
  schema: [
    { component: 'InputNumber', componentProps: { max: 120, min: 0 }, fieldName: 'recordBeforeSeconds', label: '事件前录像（秒）', rules: z.number().min(0).max(120) },
    { component: 'InputNumber', componentProps: { max: 120, min: 0 }, fieldName: 'recordAfterSeconds', label: '事件后录像（秒）', rules: z.number().min(0).max(120) },
    { component: 'Select', componentProps: { disabled: true, options: [{ label: '对象存储', value: 'OBJECT_STORAGE' }] }, fieldName: 'evidenceStorageMode', label: '证据存储', rules: z.literal('OBJECT_STORAGE') },
    { component: 'InputNumber', componentProps: { max: 3650, min: 1 }, fieldName: 'evidenceRetentionDays', label: '证据保留期（天）', rules: z.number().min(1).max(3650) },
  ],
  showDefaultActions: false,
});
const [NodeForm, nodeApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 150 },
  layout: 'horizontal',
  schema: [
    { component: 'InputNumber', componentProps: { max: 3600, min: 10 }, fieldName: 'nodeOfflineThresholdSeconds', label: '节点离线阈值（秒）', rules: z.number().min(10).max(3600) },
  ],
  showDefaultActions: false,
});
const [NotificationForm, notificationApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 140 },
  layout: 'horizontal',
  schema: [
    { component: 'Switch', fieldName: 'notificationsEnabled', label: '启用事件通知' },
  ],
  showDefaultActions: false,
});

const canDeploy = computed(() => hasAccessByCodes(['ai-video:settings:deploy']));

async function load() {
  const [settings, history, tasks] = await Promise.all([
    getGlobalSettings(),
    getGlobalSettingsVersions(),
    getTaskPage({ actualStatus: 'RUNNING', pageNo: 1, pageSize: 100 }),
  ]);
  current.value = settings;
  versions.value = history;
  runningTasks.value = tasks.list.map((task) => ({
    label: `${task.name}（${task.code} / ID ${task.id}）`,
    value: task.id,
  }));
  const value = settings.settings;
  await Promise.all([
    videoApi.setValues(value),
    inferenceApi.setValues(value),
    evidenceApi.setValues(value),
    nodeApi.setValues(value),
    notificationApi.setValues(value),
  ]);
}

async function collectSettings(): Promise<AiVideoSettingsApi.Settings | undefined> {
  const validations = await Promise.all([
    videoApi.validate(),
    inferenceApi.validate(),
    evidenceApi.validate(),
    nodeApi.validate(),
    notificationApi.validate(),
  ]);
  if (validations.some(({ valid }) => !valid)) return;
  const values = await Promise.all([
    videoApi.getValues(),
    inferenceApi.getValues(),
    evidenceApi.getValues(),
    nodeApi.getValues(),
    notificationApi.getValues(),
  ]);
  return Object.assign({ schemaVersion: '1.0' as const }, ...values) as AiVideoSettingsApi.Settings;
}

async function handleSave() {
  if (!current.value) return;
  if (applyScope.value !== 'NEW_TASKS' && !canDeploy.value) {
    message.error('当前账号没有批量下发权限');
    return;
  }
  if (applyScope.value === 'GRAY' && grayTaskIds.value.length === 0) {
    message.warning('请选择至少一个运行任务作为灰度范围');
    return;
  }
  const settings = await collectSettings();
  if (!settings) return;
  const labels: Record<string, string> = {
    defaultConfidence: '默认置信度', defaultFps: '默认分析 FPS', evidenceRetentionDays: '证据保留期',
    evidenceStorageMode: '证据存储', nodeOfflineThresholdSeconds: '节点离线阈值', notificationsEnabled: '事件通知',
    recordAfterSeconds: '事件后录像', recordBeforeSeconds: '事件前录像', schemaVersion: 'Schema 版本',
  };
  const changes = Object.entries(settings)
    .filter(([key, value]) => current.value?.settings[key as keyof AiVideoSettingsApi.Settings] !== value)
    .map(([key, value]) => `${labels[key] || key}: ${String(current.value?.settings[key as keyof AiVideoSettingsApi.Settings])} → ${String(value)}`);
  if (changes.length === 0) {
    message.info('参数没有变化');
    return;
  }
  const scopeText = applyScope.value === 'NEW_TASKS' ? '仅影响新任务' : applyScope.value === 'GRAY' ? `灰度下发 ${grayTaskIds.value.length} 个运行任务` : `下发全部 ${runningTasks.value.length} 个运行任务`;
  await confirm(`即将生成版本 v${current.value.versionNo + 1}（${scopeText}）：\n${changes.join('\n')}\n\n运行任务参数变更会立即影响推理与证据采集，请确认影响范围。`);
  saving.value = true;
  try {
    const result = await saveGlobalSettings({
      applyScope: applyScope.value,
      expectedVersionNo: current.value.versionNo,
      grayTaskIds: applyScope.value === 'GRAY' ? grayTaskIds.value : [],
      settings,
    });
    message.success(`全局参数 v${result.versionNo} 已保存，创建 ${result.commandCount} 条下发命令`);
    await load();
  } finally {
    saving.value = false;
  }
}

const historyColumns = [
  { dataIndex: 'versionNo', title: '版本', width: 80 },
  { dataIndex: 'applyScope', title: '作用范围', width: 130 },
  { dataIndex: 'status', title: '状态', width: 110 },
  { dataIndex: 'summary', title: '字段差异' },
  { dataIndex: 'commands', title: '任务 / 命令', width: 120 },
  { dataIndex: 'creator', title: '操作人', width: 100 },
  { dataIndex: 'appliedAt', title: '保存时间', width: 180 },
];

onMounted(load);
</script>

<template>
  <Page title="AI 全局参数" description="强类型参数聚合、版本审计与运行任务安全下发">
    <div class="ai-page">
    <Alert
      class="mb-4"
      message="系统默认值来自基础参数配置；每次保存生成租户内不可变版本。批量下发不会重启任务，而是通过耐久节点命令热更新 Runtime 参数。"
      show-icon
      type="info"
    />
    <div class="grid grid-cols-1 gap-4 xl:grid-cols-2">
      <Card title="视频"><p class="text-muted-foreground mb-4 text-sm">默认分析采样速率，范围 0.1–10 FPS；影响算力占用和响应速度。</p><VideoForm /></Card>
      <Card title="推理"><p class="text-muted-foreground mb-4 text-sm">新任务未显式覆盖时采用的默认置信度；灰度或全量下发会热更新运行任务。</p><InferenceForm /></Card>
      <Card title="事件证据"><p class="text-muted-foreground mb-4 text-sm">录像窗口 0–120 秒，保留期 1–3650 天；V1 固定使用对象存储。</p><EvidenceForm /></Card>
      <Card title="节点"><p class="text-muted-foreground mb-4 text-sm">连续超过阈值未收到心跳时判定离线，范围 10–3600 秒。</p><NodeForm /></Card>
      <Card title="通知"><p class="text-muted-foreground mb-4 text-sm">控制事件通知总开关；具体端点和过滤条件仍在 Webhook 页面管理。</p><NotificationForm /></Card>
      <Card title="保存与作用范围">
        <Space direction="vertical" class="w-full" :size="16">
          <RadioGroup v-model:value="applyScope" button-style="solid">
            <RadioButton value="NEW_TASKS">仅新任务</RadioButton>
            <RadioButton :disabled="!canDeploy" value="GRAY">灰度任务</RadioButton>
            <RadioButton :disabled="!canDeploy" value="ALL_RUNNING">全部运行任务</RadioButton>
          </RadioGroup>
          <Select v-if="applyScope === 'GRAY'" v-model:value="grayTaskIds" class="w-full" mode="multiple" :options="runningTasks" placeholder="选择最多 100 个运行任务" />
          <Alert v-if="applyScope !== 'NEW_TASKS'" message="危险操作：保存后将通过耐久命令热更新选定运行任务。失败任务会保留期望版本并在版本历史中显示 PARTIAL。" show-icon type="warning" />
          <Button v-if="hasAccessByCodes(['ai-video:settings:update'])" :loading="saving" type="primary" @click="handleSave">预览差异并保存</Button>
        </Space>
      </Card>
    </div>
    <Card class="mt-4" title="版本历史（最近 50 个）">
      <Table :columns="historyColumns" :data-source="versions" :pagination="false" row-key="id" size="small">
        <template #bodyCell="{ column, record }">
          <template v-if="column.dataIndex === 'versionNo'">v{{ record.versionNo }}</template>
          <template v-else-if="column.dataIndex === 'status'"><Tag :color="record.status === 'PARTIAL' ? 'warning' : 'success'">{{ record.status }}</Tag></template>
          <template v-else-if="column.dataIndex === 'summary'">{{ Object.keys(record.diff).join('、') || '无字段变化' }}</template>
          <template v-else-if="column.dataIndex === 'commands'">{{ record.affectedTaskCount }} / {{ record.commandCount }}</template>
        </template>
      </Table>
    </Card>
    </div>
  </Page>
</template>
