<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { createRule } from '#/api/ai-video/rule';

import { eventTypes } from '../../event/presentation';

const emit = defineEmits(['success']);
const eventTypeOptions = Object.entries(eventTypes).map(([value, label]) => ({
  label: `${label}（${value}）`,
  value,
}));

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'ai-form-span-full',
    labelWidth: 96,
  },
  layout: 'vertical',
  wrapperClass: 'ai-form-grid',
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: '规则名称',
      component: 'Input',
      componentProps: { maxlength: 100, placeholder: '例如：厂区车辆违停告警' },
      rules: z.string().trim().min(1, '请输入规则名称').max(100),
    },
    {
      fieldName: 'code',
      label: '稳定编码',
      component: 'Input',
      componentProps: {
        maxlength: 64,
        placeholder: '例如：vehicle-parking-alert',
      },
      rules: z
        .string()
        .regex(
          /^[a-z][a-z0-9-]{1,63}$/,
          '以小写字母开头，仅含小写字母、数字和连字符',
        ),
    },
    {
      fieldName: 'eventType',
      label: '事件类型',
      component: 'AutoComplete',
      rules: z
        .string()
        .regex(
          /^[A-Z][A-Z0-9_]{1,63}$/,
          '请输入大写字母、数字和下划线组成的事件编码',
        ),
      componentProps: {
        class: 'w-full',
        options: eventTypeOptions,
        placeholder: '选择已有事件类型，或输入大写事件编码',
        filterOption: (
          input: string,
          option: { label?: string; value?: string },
        ) =>
          `${option.label ?? ''} ${option.value ?? ''}`
            .toLowerCase()
            .includes(input.toLowerCase()),
      },
    },
    {
      fieldName: 'description',
      label: '说明',
      component: 'Textarea',
      componentProps: {
        maxlength: 500,
        placeholder: '简要说明适用场景',
        rows: 3,
      },
    },
  ],
});
const [Modal, api] = useVbenModal({
  async onConfirm() {
    const validation = await formApi.validate();
    if (!validation.valid) return;
    api.lock();
    try {
      await createRule({
        ...((await formApi.getValues()) as AiVideoRuleApi.RuleSave),
        status: 0,
      });
      emit('success');
      await api.close();
      message.success('规则已创建，请编辑并发布首个版本');
    } finally {
      api.unlock();
    }
  },
});
</script>
<template>
  <Modal
    class="ai-dialog w-[640px] max-w-[calc(100vw-32px)]"
    title="创建规则"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <Form />
  </Modal>
</template>
