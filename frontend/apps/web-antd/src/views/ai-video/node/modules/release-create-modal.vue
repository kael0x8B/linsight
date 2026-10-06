<script setup lang="ts">
import type { ReleaseBuildConfiguration } from '#/api/ai-video/node/application-release';

import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { createRelease } from '#/api/ai-video/node/application-release';
import { $t } from '#/locales';

const emit = defineEmits<{ success: [] }>();
let requestId = '';
let submittedValues = '';
const configuration = ref<ReleaseBuildConfiguration>();
const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 100 },
  layout: 'horizontal',
  showDefaultActions: false,
  schema: [
    {
      component: 'Input',
      fieldName: 'version',
      label: $t('box-release.version'),
      rules: z
        .string()
        .regex(
          /^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$/,
          $t('box-release.versionRule'),
        ),
      componentProps: { maxlength: 64, placeholder: '1.0.6' },
    },
    {
      component: 'Textarea',
      fieldName: 'notes',
      label: $t('box-release.notes'),
      defaultValue: '',
      rules: z.string().max(4000),
      componentProps: { rows: 4, maxlength: 4000 },
    },
  ],
});
const [Modal, modalApi] = useVbenModal({
  async onOpenChange(open) {
    if (!open) return;
    requestId = crypto.randomUUID();
    submittedValues = '';
    await formApi.resetForm();
    configuration.value = modalApi.getData<{
      configuration: ReleaseBuildConfiguration;
    }>().configuration;
  },
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;
    modalApi.lock();
    try {
      const values = await formApi.getValues();
      const data = {
        version: String(values.version),
        notes: String(values.notes || ''),
      };
      const serialized = JSON.stringify(data);
      if (submittedValues && submittedValues !== serialized)
        requestId = crypto.randomUUID();
      submittedValues = serialized;
      await createRelease({ ...data, requestId });
      message.success($t('box-release.queued'));
      emit('success');
      await modalApi.close();
    } finally {
      modalApi.unlock();
    }
  },
});
</script>
<template>
  <Modal
    :title="$t('box-release.generate')"
    :confirm-text="$t('box-release.generate')"
    class="w-[640px] max-w-[calc(100vw-2rem)]"
  >
    <div class="mb-5 space-y-2 text-sm">
      <p class="font-medium">{{ configuration?.label }}</p>
      <p>
        {{ $t('box-release.supportedDevices') }}：
        {{ configuration?.devices.join(' / ').toUpperCase() }}
      </p>
      <p class="text-muted-foreground">{{ $t('box-release.sourceHelp') }}</p>
    </div>
    <Form />
  </Modal>
</template>
