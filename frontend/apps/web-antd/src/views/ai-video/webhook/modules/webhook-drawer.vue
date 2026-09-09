<script lang="ts" setup>
import type { AiVideoWebhookApi } from '#/api/ai-video/webhook';

import { h } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { Alert, message, Modal as AntModal } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { createWebhook, updateWebhook } from '#/api/ai-video/webhook';

const emit = defineEmits(['success']);

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 110 },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      fieldName: 'name',
      label: '端点名称',
      rules: z.string().min(1, '请输入端点名称').max(100),
    },
    {
      component: 'Input',
      componentProps: { placeholder: 'https://events.example.com/linsight' },
      fieldName: 'url',
      label: 'HTTPS 地址',
      rules: z.string().url('请输入合法 URL').startsWith('https://', '必须使用 HTTPS'),
    },
    {
      component: 'InputPassword',
      componentProps: { placeholder: '创建时留空自动生成；修改时留空不更换' },
      fieldName: 'secret',
      label: '签名密钥',
      rules: z.string().min(24, '至少 24 个字符').max(256).optional().or(z.literal('')),
    },
    {
      component: 'Select',
      componentProps: {
        mode: 'tags',
        options: [
          'AREA_INTRUSION',
          'PPE_VIOLATION',
          'FIRE_SMOKE',
          'EQUIPMENT_ANOMALY',
        ].map((value) => ({ label: value, value })),
        placeholder: '留空表示全部事件类型',
      },
      fieldName: 'eventTypes',
      label: '事件类型',
    },
    {
      component: 'Select',
      componentProps: {
        mode: 'multiple',
        options: ['INFO', 'WARNING', 'CRITICAL', 'EMERGENCY'].map((value) => ({
          label: value,
          value,
        })),
        placeholder: '留空表示全部等级',
      },
      fieldName: 'severities',
      label: '事件等级',
    },
    {
      component: 'RadioGroup',
      componentProps: {
        options: [
          { label: '启用', value: 0 },
          { label: '停用', value: 1 },
        ],
      },
      fieldName: 'status',
      label: '状态',
    },
    {
      component: 'InputNumber',
      componentProps: { max: 10, min: 1 },
      fieldName: 'maxAttempts',
      label: '最大尝试次数',
      rules: z.number().min(1).max(10),
    },
    {
      component: 'InputNumber',
      componentProps: { max: 10_000, min: 500, step: 500 },
      fieldName: 'timeoutMs',
      label: '超时（ms）',
      rules: z.number().min(500).max(10_000),
    },
  ],
  showDefaultActions: false,
});

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    const { valid } = await formApi.validate();
    if (!valid) return;
    const values = (await formApi.getValues()) as AiVideoWebhookApi.SaveEndpoint;
    drawerApi.lock();
    try {
      if (values.id) {
        await updateWebhook(values);
        message.success('Webhook 端点已更新');
      } else {
        const result = await createWebhook(values);
        AntModal.success({
          content: h('div', { class: 'space-y-2' }, [
            h('p', '签名密钥仅显示这一次，请立即保存到接收方的密钥管理系统。'),
            h('code', { style: 'word-break:break-all;user-select:all' }, result.secret),
          ]),
          title: 'Webhook 创建成功',
          width: 560,
        });
      }
      await drawerApi.close();
      emit('success');
    } finally {
      drawerApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) {
      await formApi.resetForm();
      return;
    }
    const data = drawerApi.getData<AiVideoWebhookApi.Endpoint>();
    await formApi.setValues(
      data
        ? { ...data, secret: '' }
        : { eventTypes: [], maxAttempts: 5, severities: [], status: 0, timeoutMs: 5000 },
    );
  },
});
</script>

<template>
  <Drawer class="w-[640px] max-w-[calc(100vw-32px)]" :title="drawerApi.getData()?.id ? '编辑 Webhook' : '新增 Webhook'">
    <div class="space-y-4">
      <Alert
        message="服务端会校验公网 HTTPS 地址。请求使用 timestamp、nonce 和 HMAC-SHA256 签名；密钥加密保存且不会再次返回。"
        show-icon
        type="info"
      />
      <Form />
    </div>
  </Drawer>
</template>
