<script lang="ts" setup>
import type { TaskEvaluation } from '#/api/ai-video/task/evaluation';

import { onBeforeUnmount, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Spin,
  Tag,
} from 'ant-design-vue';

import { getTaskEvaluation } from '#/api/ai-video/task/evaluation';

import { failedCheckLabels, metricFields } from '../data';

const record = ref<TaskEvaluation>();
const error = ref('');
const loading = ref(false);
let generation = 0;
let recordId: number;
async function load() {
  const version = ++generation;
  record.value = undefined;
  loading.value = true;
  error.value = '';
  try {
    const value = await getTaskEvaluation(recordId);
    if (version === generation) record.value = value;
  } catch {
    if (version === generation) error.value = '记录加载失败，请重试。';
  } finally {
    if (version === generation) loading.value = false;
  }
}
const [Drawer, drawerApi] = useVbenDrawer({
  onOpenChange(open) {
    if (!open) {
      generation++;
      return;
    }
    recordId = drawerApi.getData<{ id: number }>().id;
    void load();
  },
});
function exportRecord() {
  if (!record.value) return;
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(record.value, null, 2)], {
      type: 'application/json',
    }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `evaluation-${record.value.id}.json`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
function snapshotText(key: string) {
  const value = record.value?.configurationSnapshot?.[key];
  return value == null ? '未配置 / 未上报' : JSON.stringify(value, null, 2);
}
onBeforeUnmount(() => {
  generation++;
});
</script>

<template>
  <Drawer
    title="视频评测详情"
    :footer="false"
    class="ai-dialog w-[900px] max-w-[calc(100vw-24px)]"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <Alert v-if="error" :message="error" show-icon type="error">
      <template #action><Button @click="load">重试</Button></template>
    </Alert>
    <Spin :spinning="loading">
      <template v-if="record">
        <div class="mb-4 flex items-center justify-between">
          <Tag :color="record.status === 'PASS' ? 'green' : 'orange'">{{
            record.status === 'PASS' ? '指标达标' : '指标未达标'
          }}</Tag>
          <Button @click="exportRecord">导出评测 JSON</Button>
        </div>
        <Descriptions bordered :column="1" size="small">
          <DescriptionsItem label="任务 / 配置"
            >{{ record.taskName }} (#{{ record.taskId }}) · v{{
              record.configVersion
            }}</DescriptionsItem
          >
          <DescriptionsItem label="记录来源"
            >人工视频实测；按本次阈值判定，不代表生产发布批准</DescriptionsItem
          >
          <DescriptionsItem label="测试时间">{{
            new Date(record.measuredAtMillis).toLocaleString('zh-CN', {
              timeZoneName: 'short',
            })
          }}</DescriptionsItem>
          <DescriptionsItem label="测试集">{{
            record.datasetVersion
          }}</DescriptionsItem>
          <DescriptionsItem label="SHA256"
            ><code class="break-all">{{
              record.datasetSha256
            }}</code></DescriptionsItem
          >
          <DescriptionsItem label="证据引用"
            ><code class="break-all">{{
              record.evidenceRef
            }}</code></DescriptionsItem
          >
          <DescriptionsItem label="实测环境">{{
            record.measurement?.environmentDescription
          }}</DescriptionsItem>
          <DescriptionsItem label="未达标项">{{
            record.failedChecks
              .map((key) => failedCheckLabels[key] ?? key)
              .join('、') || '无'
          }}</DescriptionsItem>
          <DescriptionsItem label="记录人 / 记录时间"
            >{{ record.creator }} ·
            {{
              new Date(record.createTime).toLocaleString('zh-CN', {
                timeZoneName: 'short',
              })
            }}</DescriptionsItem
          >
        </Descriptions>
        <h3 class="mb-2 mt-5 font-medium">实测值与本次阈值</h3>
        <Descriptions
          v-if="record.measurement"
          bordered
          :column="1"
          size="small"
        >
          <DescriptionsItem
            v-for="[key, label, threshold, thresholdLabel] in metricFields"
            :key="key"
            :label="label"
          >
            {{ record.measurement.metrics[key] }} · {{ thresholdLabel }}
            {{ record.measurement.thresholds[threshold] }}
          </DescriptionsItem>
          <DescriptionsItem label="冷却与去重">{{
            record.measurement.cooldownDedupPass ? '通过' : '未通过'
          }}</DescriptionsItem>
          <DescriptionsItem label="资源峰值"
            >CPU {{ record.measurement.resourceUsage.cpuPeakPercent }}% · 内存
            {{ record.measurement.resourceUsage.memoryPeakMiB }} MiB · 显存
            {{ record.measurement.resourceUsage.acceleratorMemoryPeakMiB }}
            MiB</DescriptionsItem
          >
          <DescriptionsItem label="备注">{{
            record.measurement.note || '无'
          }}</DescriptionsItem>
        </Descriptions>
        <h3 class="mb-2 mt-5 font-medium">记录时保存的配置快照</h3>
        <p class="mb-3 text-sm text-muted-foreground">
          保存平台版本与网关上报配置；网关本地规则以其上报配置为准。节点环境为最近一次上报，实际测试环境以实测说明和证据为准。
        </p>
        <details
          v-for="[key, label] in [
            ['pipeline', 'Pipeline / 算法包'],
            ['models', '模型版本与 SHA256'],
            ['rule', '规则版本'],
            ['parameters', '任务参数'],
            ['globalSettings', '全局设置'],
            ['gatewayConfiguration', '网关上报配置（含本地规则）'],
            ['nodeAtRecording', '节点环境'],
          ]"
          :key="key"
          class="mb-3 rounded border p-3"
        >
          <summary class="cursor-pointer">{{ label }}</summary>
          <pre
            class="mt-3 max-h-72 overflow-auto whitespace-pre-wrap break-all text-xs"
            >{{ snapshotText(key!) }}</pre
          >
        </details>
      </template>
    </Spin>
  </Drawer>
</template>
