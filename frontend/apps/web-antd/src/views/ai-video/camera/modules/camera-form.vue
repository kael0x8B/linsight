<script lang="ts" setup>
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { createCamera, getCamera, updateCamera } from '#/api/ai-video/camera';
import { $t } from '#/locales';

import { useCameraFormSchema } from '../data';

const emit = defineEmits(['success']);
const formData = ref<AiVideoCameraApi.Camera>();
const isEdit = computed(() => Boolean(formData.value?.id));
const title = computed(() =>
  isEdit.value
    ? $t('ui.actionTitle.edit', ['摄像头'])
    : $t('ui.actionTitle.create', ['摄像头']),
);

const [Form, formApi] = useVbenForm({
  commonConfig: {
    formItemClass: 'min-w-0',
  },
  layout: 'vertical',
  wrapperClass: 'ai-form-grid ai-form-grid--two',
  schema: useCameraFormSchema(),
  showDefaultActions: false,
});

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;

    const data = (await formApi.getValues()) as AiVideoCameraApi.Camera;
    if (!isEdit.value && !data.mainStreamUri?.trim()) {
      message.warning('新建摄像头时必须填写主码流路径');
      return;
    }

    modalApi.lock();
    try {
      await (isEdit.value ? updateCamera(data) : createCamera(data));
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

    const data = modalApi.getData<AiVideoCameraApi.Camera>();
    if (!data?.id) {
      formData.value = undefined;
      await formApi.setValues({
        groupId: data?.groupId ?? 0,
        port: 554,
        protocol: 'RTSP',
        status: 0,
      });
      return;
    }

    modalApi.lock();
    try {
      formData.value = await getCamera(data.id);
      await formApi.setValues({
        ...formData.value,
        mainStreamUri: undefined,
        password: undefined,
        subStreamUri: undefined,
        username: undefined,
      });
    } finally {
      modalApi.unlock();
    }
  },
});
</script>

<template>
  <Modal
    :title="title"
    class="ai-dialog w-[760px]"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <div class="ai-workflow">
      <Form />
      <p v-if="isEdit" class="ai-form-note">
        码流路径和访问凭据不回显，留空保留原值。
      </p>
    </div>
  </Modal>
</template>
