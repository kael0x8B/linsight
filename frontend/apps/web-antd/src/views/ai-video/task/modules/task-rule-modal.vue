<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, ref, watch } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Alert, Checkbox, FormItem, message, Select } from 'ant-design-vue';

import { getAlgorithm } from '#/api/ai-video/algorithm';
import { getPublishedRules, getRuleVersions } from '#/api/ai-video/rule';
import {
  getTask,
  startTask,
  stopTask,
  updateTaskRule,
} from '#/api/ai-video/task';
const emit = defineEmits(['success']);
const task = ref<AiVideoTaskApi.Task>();
const rules = ref<AiVideoRuleApi.Rule[]>([]);
const versions = ref<AiVideoRuleApi.RuleVersion[]>([]);
const confirmed = ref(false);
const error = ref('');
const loading = ref(false);
const progress = ref('');
const ruleId = ref<number>();
const versionId = ref<number>();
const restart = ref(false);
let generation = 0;
const selectedVersion = computed(() =>
  versions.value.find((v) => v.id === versionId.value),
);
const [Modal, api] = useVbenModal({
  async onOpenChange(open) {
    if (!open) return;
    error.value = '';
    progress.value = '';
    confirmed.value = false;
    loading.value = true;
    try {
      const row = api.getData<AiVideoTaskApi.Task>();
      task.value = await getTask(row.id);
      restart.value = task.value.actualStatus === 'RUNNING';
      const [algorithm, list] = await Promise.all([
        getAlgorithm(task.value.algorithmId),
        getPublishedRules(),
      ]);
      rules.value = list.filter((r) => r.eventType === algorithm.eventType);
      ruleId.value = task.value.ruleId;
    } catch {
      error.value = '读取任务或规则失败，请关闭后重试。';
    } finally {
      loading.value = false;
    }
  },
  async onConfirm() {
    if (
      loading.value ||
      !task.value ||
      !ruleId.value ||
      !selectedVersion.value ||
      !confirmed.value
    ) {
      message.warning('请选择已发布规则版本，并确认区域适用于当前摄像头');
      return;
    }
    api.lock();
    error.value = '';
    const original = task.value;
    try {
      let current = await getTask(original.id);
      if (current.configVersion !== original.configVersion)
        throw new Error('任务配置已被其他操作更新，请关闭并重新打开');
      if (current.actualStatus === 'RUNNING') {
        if (!restart.value) throw new Error('任务运行状态已改变，请重新打开');
        progress.value = '正在停止任务，等待节点确认…';
        await stopTask(current.id);
        current = await waitStatus(current.id, 'STOPPED');
      }
      if (!['DRAFT', 'STOPPED'].includes(current.actualStatus))
        throw new Error(`当前状态 ${current.actualStatus} 不可切换规则`);
      progress.value = '正在保存规则版本…';
      await updateTaskRule({
        id: current.id,
        expectedConfigVersion: current.configVersion,
        ruleId: ruleId.value,
        ruleVersionId: versionId.value!,
      });
      task.value = await getTask(current.id);
      if (restart.value) {
        progress.value = '正在按新规则启动任务…';
        await startTask(current.id);
        await waitStatus(current.id, 'RUNNING');
      }
      emit('success');
      message.success(restart.value ? '已按新规则恢复运行' : '已切换规则版本');
      await api.close();
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '切换失败';
      emit('success');
      progress.value = '请检查任务状态；已完成的步骤会保留，可修复后重试。';
    } finally {
      api.unlock();
    }
  },
});
async function waitStatus(id: number, status: string) {
  const until = Date.now() + 90_000;
  while (Date.now() < until) {
    const row = await getTask(id);
    if (row.actualStatus === status) return row;
    if (['FAILED', 'OFFLINE'].includes(row.actualStatus))
      throw new Error(row.errorMessage ?? `节点返回 ${row.actualStatus}`);
    await new Promise((resolve) => setTimeout(resolve, 1500));
  }
  throw new Error('等待节点确认超时，请检查任务监控页');
}
watch(ruleId, async (id) => {
  const request = ++generation;
  versions.value = [];
  versionId.value = undefined;
  if (!id) return;
  loading.value = true;
  try {
    const list = await getRuleVersions(id);
    if (request !== generation) return;
    versions.value = list.filter((v) => v.validationStatus === 'PUBLISHED');
    versionId.value =
      versions.value.find((v) => v.id === task.value?.ruleVersionId)?.id ??
      versions.value[0]?.id;
  } catch {
    error.value = '规则版本加载失败，请重新选择规则';
  } finally {
    if (request === generation) loading.value = false;
  }
});
</script>
<template>
  <Modal
    title="更换任务规则"
    :confirm-text="restart ? '停止、切换并启动' : '保存规则版本'"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
    class="ai-dialog"
  >
    <Alert
      class="mb-4"
      :message="`${task?.name ?? ''}：当前规则版本 #${task?.ruleVersionId ?? '无'}`"
      :description="
        restart
          ? '会短暂停止此任务，等待节点停止后切换规则，再重新启动。'
          : '保存后在下次启动时使用新规则。'
      "
      type="info"
      show-icon
    />
    <FormItem label="规则">
      <Select
        v-model:value="ruleId"
        class="w-full"
        :loading="loading"
        :options="rules.map((r) => ({ label: r.name, value: r.id }))"
      />
    </FormItem>
    <FormItem label="已发布版本">
      <Select
        v-model:value="versionId"
        class="w-full"
        :loading="loading"
        :options="
          versions.map((v) => ({
            label: `v${v.version} · ${v.naturalSummary ?? ''}`,
            value: v.id,
          }))
        "
      />
    </FormItem>
    <Checkbox v-model:checked="confirmed">
      已确认此版本的区域、目标类别和生效时间适用于当前摄像头
    </Checkbox>
    <Alert
      v-if="progress"
      class="mt-4"
      :message="progress"
      type="info"
      show-icon
    />
    <Alert v-if="error" class="mt-4" :message="error" type="error" show-icon />
  </Modal>
</template>
