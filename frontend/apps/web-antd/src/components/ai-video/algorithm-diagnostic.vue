<script lang="ts" setup>
import { computed } from 'vue';

import { Alert, Descriptions, DescriptionsItem } from 'ant-design-vue';

import { algorithmDiagnostic } from './algorithm-diagnostic';

const props = defineProps<{ value?: unknown }>();
const detail = computed(() => algorithmDiagnostic(props.value));
const stages: Record<string, string> = {
  IMPORT: '导入模块',
  INITIALIZE: '初始化',
  PROCESS: '处理帧',
  SDK: '模型调用',
  OUTPUT: '输出校验',
  PROTOCOL: '进程通信',
};
</script>
<template>
  <Alert
    v-if="detail"
    class="my-4"
    type="error"
    :message="detail.message"
    show-icon
  >
    <template #description>
      <Descriptions :column="1" size="small">
        <DescriptionsItem label="阶段 / 错误"
          >{{ stages[detail.stage] ?? detail.stage }} · {{ detail.code }} ·
          {{ detail.exceptionType }}</DescriptionsItem
        >
        <DescriptionsItem label="算法包"
          >{{ detail.packageCode }} @
          {{ detail.packageVersion }}</DescriptionsItem
        >
        <DescriptionsItem label="定位"
          ><span v-if="!detail.frames.length">进程外错误，无包内调用位置</span
          ><code
            v-for="(frame, index) in detail.frames"
            :key="index"
            class="mr-3 break-all"
            >{{ frame.file }}:{{ frame.line }} ({{ frame.function }})</code
          ></DescriptionsItem
        >
        <DescriptionsItem label="帧时间（ms）">{{
          detail.timestampMillis ?? '初始化阶段'
        }}</DescriptionsItem>
        <DescriptionsItem label="诊断 ID"
          ><code>{{ detail.diagnosticId }}</code></DescriptionsItem
        >
        <DescriptionsItem label="包 SHA256"
          ><code class="break-all">{{
            detail.packageSha256
          }}</code></DescriptionsItem
        >
      </Descriptions>
    </template>
  </Alert>
</template>
