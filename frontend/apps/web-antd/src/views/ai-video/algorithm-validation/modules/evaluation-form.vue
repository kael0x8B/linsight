<script lang="ts" setup>
import type { AiVideoTaskApi } from '#/api/ai-video/task';
import type { EvaluationCreate } from '#/api/ai-video/task/evaluation';

import { onBeforeUnmount, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { Alert, Button, message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getTask, getTaskPage } from '#/api/ai-video/task';
import { createTaskEvaluation } from '#/api/ai-video/task/evaluation';

import { evaluationPayload, evaluationSchema } from '../data';

const emit = defineEmits<{ success: [id: number] }>();
const task = ref<AiVideoTaskApi.Task>();
const error = ref('');
const taskError = ref('');
const taskLoading = ref(false);
let generation = 0;
let searchGeneration = 0;
let searchTimer: ReturnType<typeof setTimeout> | undefined;
let previousPayload: EvaluationCreate | undefined;

const [Form, formApi] = useVbenForm({
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 md:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: evaluationSchema(),
  showDefaultActions: false,
});

async function loadTasks(name = '') {
  const version = ++searchGeneration;
  taskError.value = '';
  try {
    const result = await getTaskPage({ pageNo: 1, pageSize: 20, name });
    if (version !== searchGeneration) return;
    const options = result.list.map((item) => ({
      label: `${item.name} (#${item.id})`,
      value: item.id,
    }));
    if (
      task.value &&
      !options.some((option) => option.value === task.value?.id)
    ) {
      options.push({
        label: `${task.value.name} (#${task.value.id})`,
        value: task.value.id,
      });
    }
    formApi.updateSchema([
      {
        fieldName: 'taskId',
        componentProps: {
          showSearch: true,
          filterOption: false,
          allowClear: true,
          placeholder: '输入名称搜索任务（每次显示 20 条）',
          options,
          onChange: selectTask,
          onSearch: (name: string) => {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(() => void loadTasks(name), 300);
          },
        },
      },
    ]);
  } catch {
    if (version === searchGeneration)
      taskError.value = '任务目录加载失败，请重试。';
  }
}

async function selectTask(id?: number) {
  const version = ++generation;
  task.value = undefined;
  taskLoading.value = !!id;
  taskError.value = '';
  if (!id) return;
  try {
    const selected = await getTask(id);
    if (version === generation) task.value = selected;
  } catch {
    if (version === generation)
      taskError.value = '任务配置读取失败，请重新选择任务。';
  } finally {
    if (version === generation) taskLoading.value = false;
  }
}

const [Drawer, drawerApi] = useVbenDrawer({
  async onOpenChange(open) {
    if (!open) {
      generation++;
      searchGeneration++;
      clearTimeout(searchTimer);
      return;
    }
    task.value = undefined;
    previousPayload = undefined;
    error.value = '';
    await formApi.resetForm();
    await loadTasks();
  },
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid || !task.value || taskLoading.value || taskError.value) return;
    const values = await formApi.getValues();
    if (values.taskId !== task.value.id) return;
    const payload = evaluationPayload(
      values,
      task.value.configVersion,
      previousPayload?.requestId ?? crypto.randomUUID(),
      task.value.gatewayRevision ?? 0,
    );
    if (
      previousPayload &&
      JSON.stringify(previousPayload) !== JSON.stringify(payload)
    )
      payload.requestId = crypto.randomUUID();
    previousPayload = payload;
    drawerApi.lock();
    error.value = '';
    try {
      const id = await createTaskEvaluation(payload);
      message.success('评测记录已保存');
      emit('success', id);
      await drawerApi.close();
    } catch {
      error.value =
        '保存未完成，请检查错误提示后重试。配置已改变时，请重新选择任务并核对测试版本。';
    } finally {
      drawerApi.unlock();
    }
  },
});
onBeforeUnmount(() => {
  generation++;
  searchGeneration++;
  clearTimeout(searchTimer);
});
</script>

<template>
  <Drawer
    title="记录视频评测"
    confirm-text="保存记录"
    class="w-[900px] max-w-[calc(100vw-24px)]"
  >
    <Alert v-if="error" class="mb-4" type="error" :message="error" show-icon />
    <Alert
      v-if="taskError"
      class="mb-4"
      type="error"
      :message="taskError"
      show-icon
    >
      <template #action><Button @click="loadTasks()">重试</Button></template>
    </Alert>
    <p class="mb-4 text-sm text-muted-foreground">
      人工录入的指标将与所填阈值比较。请核对测试配置；保存后可查阅和导出，修正需新增记录。
    </p>
    <p v-if="task" class="mb-4 text-sm">
      配置 v{{ task.configVersion }} · 网关修订
      {{ task.gatewayRevision ?? '未上报' }} · Pipeline #{{
        task.pipelineVersionId
      }}
      · 节点 #{{ task.nodeId }} · {{ task.actualStatus }}
    </p>
    <p v-if="taskLoading" class="mb-4">正在读取任务配置…</p>
    <Form />
  </Drawer>
</template>
