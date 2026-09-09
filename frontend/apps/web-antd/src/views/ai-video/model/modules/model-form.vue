<script lang="ts" setup>
import type { AiVideoModelApi } from '#/api/ai-video/model';

import { useVbenModal } from '@vben/common-ui';

import { Alert, message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { createModel } from '#/api/ai-video/model';

import { useModelFormSchema } from '../data';

const emit = defineEmits(['success']);

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 96,
  },
  layout: 'horizontal',
  schema: useModelFormSchema(),
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;

    modalApi.lock();
    try {
      const values = (await formApi.getValues()) as Omit<
        AiVideoModelApi.Model,
        'status'
      >;
      await createModel({ ...values, status: 0 });
      await modalApi.close();
      emit('success');
      message.success('模型资产已创建');
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen) {
    if (!isOpen) {
      await formApi.resetForm();
      return;
    }
    await formApi.setValues({ sourceType: 'CUSTOM' });
  },
});
</script>

<template>
  <Modal class="w-[640px]" title="新增模型">
    <Alert class="mx-4 mb-4" message="已有模型的新版权重或其他部署格式，请在原模型的“版本与部署”中上传新版本，无需重复新建模型。" type="info" show-icon />
    <Form class="mx-4" />
  </Modal>
</template>
