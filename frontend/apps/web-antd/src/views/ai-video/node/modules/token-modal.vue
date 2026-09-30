<script lang="ts" setup>
import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Input,
  message,
} from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { createNodeBootstrapToken } from '#/api/ai-video/node';

const token = ref('');
const expireTime = ref('');
const confirmText = computed(() => (token.value ? '关闭' : '生成令牌'));

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 96 },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { maxlength: 100, placeholder: '例如：一号边缘服务器' },
      fieldName: 'name',
      label: '用途说明',
      rules: z.string().trim().min(1, '请输入用途说明').max(100),
    },
    {
      component: 'InputNumber',
      componentProps: { class: '!w-full', min: 5, max: 1440 },
      fieldName: 'ttlMinutes',
      label: '有效分钟',
      rules: z.number().min(5).max(1440).default(30),
    },
  ],
  showDefaultActions: false,
});

async function copyToken() {
  await navigator.clipboard.writeText(token.value);
  message.success('注册令牌已复制');
}

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    if (token.value) {
      await modalApi.close();
      return;
    }
    const { valid } = await formApi.validate();
    if (!valid) return;
    modalApi.lock();
    try {
      const values = await formApi.getValues();
      const result = await createNodeBootstrapToken({
        name: String(values.name),
        ttlMinutes: Number(values.ttlMinutes),
      });
      token.value = result.token;
      expireTime.value = result.expireTime;
      message.success('一次性注册令牌已生成');
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen) {
    if (isOpen) return;
    token.value = '';
    expireTime.value = '';
    await formApi.resetForm();
  },
});
</script>

<template>
  <Modal :confirm-text="confirmText" title="生成节点注册令牌">
    <div class="space-y-4">
      <Alert
        message="令牌仅显示一次。请通过安全渠道交给目标边缘节点，使用后立即失效。"
        show-icon
        type="warning"
      />
      <Form v-if="!token" />
      <template v-else>
        <Descriptions bordered :column="1" size="small">
          <DescriptionsItem label="失效时间">{{ expireTime }}</DescriptionsItem>
        </Descriptions>
        <Input.TextArea :value="token" :auto-size="{ minRows: 3 }" readonly />
        <Button block type="primary" @click="copyToken">复制注册令牌</Button>
      </template>
    </div>
  </Modal>
</template>
