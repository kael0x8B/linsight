<script lang="ts" setup>
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  createCameraGroup,
  getCameraGroup,
  updateCameraGroup,
} from '#/api/ai-video/camera';
import { $t } from '#/locales';

import { useCameraGroupFormSchema } from '../data';

const emit = defineEmits(['success']);
const formData = ref<AiVideoCameraApi.CameraGroup>();
const title = computed(() =>
  formData.value?.id
    ? $t('ui.actionTitle.edit', ['摄像头分组'])
    : $t('ui.actionTitle.create', ['摄像头分组']),
);

const [Form, formApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 90,
  },
  layout: 'horizontal',
  schema: useCameraGroupFormSchema(),
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;

    const data = (await formApi.getValues()) as AiVideoCameraApi.CameraGroup;
    modalApi.lock();
    try {
      await (formData.value?.id
        ? updateCameraGroup(data)
        : createCameraGroup(data));
      await modalApi.close();
      emit('success');
      message.success($t('ui.actionMessage.operationSuccess'));
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen: boolean) {
    if (!isOpen) {
      formData.value = undefined;
      await formApi.resetForm();
      return;
    }

    const data = modalApi.getData<Partial<AiVideoCameraApi.CameraGroup>>();
    if (!data?.id) {
      formData.value = undefined;
      await formApi.setValues({
        parentId: data?.parentId ?? 0,
        sort: 0,
        status: 0,
      });
      return;
    }

    modalApi.lock();
    try {
      formData.value = await getCameraGroup(data.id);
      await formApi.setValues(formData.value);
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal :title="title">
    <Form class="mx-4" />
  </Modal>
</template>
