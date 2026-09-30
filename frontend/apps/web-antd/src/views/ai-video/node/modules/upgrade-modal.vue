<script lang="ts" setup>
import type { UploadFile } from 'ant-design-vue';
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { AiVideoNode } from '#/api/ai-video/node';

import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message, Upload } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { upgradeNode } from '#/api/ai-video/node';

const emit = defineEmits(['success']);
const node = ref<AiVideoNode>();
const fileList = ref<UploadFile[]>([]);

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' }, labelWidth: 100 },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { maxlength: 64, placeholder: '例如 1.1.0' },
      fieldName: 'targetVersion',
      label: '目标版本',
      rules: z
        .string()
        .trim()
        .min(1)
        .max(64)
        .regex(/^[A-Za-z0-9._-]+$/, '版本格式不正确'),
    },
    {
      component: 'Input',
      componentProps: {
        maxlength: 64,
        placeholder: '64 位小写十六进制 HMAC-SHA256',
      },
      fieldName: 'signature',
      label: '发布签名',
      rules: z.string().regex(/^[0-9a-f]{64}$/, '请输入 64 位小写十六进制签名'),
    },
    {
      component: 'Upload',
      fieldName: 'file',
      label: '升级包',
      rules: 'required',
    },
  ],
  showDefaultActions: false,
});

function beforeUpload(file: FileType) {
  const validName = file.name.endsWith('.tar.gz') || file.name.endsWith('.tgz');
  if (!validName) {
    message.error('仅支持 .tar.gz 或 .tgz 升级包');
    return Upload.LIST_IGNORE;
  }
  if (file.size > 64 * 1024 * 1024) {
    message.error('升级包不能超过 64 MB');
    return Upload.LIST_IGNORE;
  }
  void formApi.setFieldValue('file', file);
  return false;
}

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    if (!node.value?.id) return;
    const { valid } = await formApi.validate();
    if (!valid) return;
    const values = await formApi.getValues();
    const file = values.file as File | undefined;
    if (!file) return;
    modalApi.lock();
    try {
      await upgradeNode({
        file,
        nodeId: node.value.id,
        signature: String(values.signature),
        targetVersion: String(values.targetVersion),
      });
      message.success(
        '升级命令已下发；安装完成后请在节点菜单执行重启以启用新版本',
      );
      await modalApi.close();
      emit('success');
    } finally {
      modalApi.unlock();
    }
  },
  async onOpenChange(isOpen) {
    if (isOpen) {
      node.value = modalApi.getData<AiVideoNode>();
      return;
    }
    node.value = undefined;
    fileList.value = [];
    await formApi.resetForm();
  },
});
</script>

<template>
  <Modal :title="`升级 Edge Agent · ${node?.name ?? ''}`">
    <div class="space-y-4">
      <Form>
        <template #file>
          <Upload.Dragger
            v-model:file-list="fileList"
            accept=".tar.gz,.tgz"
            :before-upload="beforeUpload"
            :max-count="1"
          >
            <p class="font-medium">点击或拖拽已签名的 Edge Agent 升级包</p>
            <p class="text-muted-foreground mt-1 text-xs">
              仅支持 tar.gz/tgz，最大 64 MB。节点需配置发布签名密钥。
            </p>
          </Upload.Dragger>
        </template>
      </Form>
      <p class="text-xs text-muted-foreground">
        安装完成后，需重启节点启用新版本。
      </p>
    </div>
  </Modal>
</template>
