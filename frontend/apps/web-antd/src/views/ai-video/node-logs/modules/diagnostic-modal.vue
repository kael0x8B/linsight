<script lang="ts" setup>
import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';
import dayjs from 'dayjs';

import { useVbenForm, z } from '#/adapter/form';
import { createNodeDiagnostic } from '#/api/ai-video/node-log';

const emit = defineEmits<{ success: [id: number] }>();

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 96 },
  layout: 'vertical',
  wrapperClass: 'ai-form-grid',
  schema: [
    {
      component: 'InputNumber',
      componentProps: { min: 1, placeholder: '留空则包含节点全部任务' },
      fieldName: 'taskId',
      label: '任务 ID',
    },
    {
      component: 'RangePicker',
      componentProps: { allowClear: false, showTime: true },
      fieldName: 'range',
      label: '日志窗口',
      rules: z.array(z.any()).length(2, '请选择开始和结束时间'),
    },
  ],
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const nodeId = Number(modalApi.getData<{ nodeId: number }>()?.nodeId);
    const { valid } = await formApi.validate();
    if (!nodeId || !valid) return;
    const values = await formApi.getValues();
    const range = values.range as [dayjs.Dayjs, dayjs.Dayjs];
    if (range[1].diff(range[0], 'hour', true) > 24) {
      message.warning('单个诊断包的日志窗口不能超过 24 小时');
      return;
    }
    modalApi.lock();
    try {
      const id = await createNodeDiagnostic({
        nodeId,
        rangeEnd: range[1].format('YYYY-MM-DD HH:mm:ss'),
        rangeStart: range[0].format('YYYY-MM-DD HH:mm:ss'),
        taskId: values.taskId ? Number(values.taskId) : undefined,
      });
      await modalApi.close();
      emit('success', id);
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(open) {
    await (open
      ? formApi.setFieldValue('range', [dayjs().subtract(1, 'hour'), dayjs()])
      : formApi.resetForm());
  },
});
</script>

<template>
  <Modal
    title="生成节点诊断包"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
    class="ai-dialog"
  >
    <div class="space-y-4">
      <Form />
    </div>
  </Modal>
</template>
