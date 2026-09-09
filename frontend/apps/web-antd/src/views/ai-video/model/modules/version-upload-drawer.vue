<script lang="ts" setup>
import type { UploadFile } from 'ant-design-vue';
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { AiVideoModelApi } from '#/api/ai-video/model';

import { computed, ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  message,
  Steps,
  Upload,
} from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import { uploadModelVersion } from '#/api/ai-video/model';

const emit = defineEmits(['success']);

interface UploadConfirmation {
  file?: File;
  licenseSpdx?: string;
  runtimeManifest?: string;
  sourceRepository?: string;
  sourceRevision?: string;
  version?: string;
}

const currentStep = ref(0);
const model = ref<AiVideoModelApi.Model>();
const fileList = ref<UploadFile[]>([]);
const confirmation = ref<UploadConfirmation>({});

const stepItems = [
  { title: '选择文件' },
  { title: '来源与许可证' },
  { title: '校验确认' },
];

const confirmText = computed(() =>
  currentStep.value === stepItems.length - 1 ? '上传并校验' : '下一步',
);

const [FileForm, fileFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 96,
  },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { maxlength: 64, placeholder: '例如 1.0.0' },
      fieldName: 'version',
      label: '版本标识',
      rules: z.string().trim().min(1, '请输入版本标识').max(64),
    },
    {
      component: 'Upload',
      fieldName: 'file',
      help: '支持 ONNX、PT、PTH、ENGINE、RKNN、ZIP；当前直传上限 64 MB。',
      label: '模型文件',
      rules: 'required',
    },
  ],
  showDefaultActions: false,
});

const [MetadataForm, metadataFormApi] = useVbenForm({
  commonConfig: {
    componentProps: { class: 'w-full' },
    formItemClass: 'col-span-2',
    labelWidth: 112,
  },
  layout: 'horizontal',
  schema: [
    {
      component: 'Input',
      componentProps: { maxlength: 500, placeholder: '代码仓库或制品来源地址' },
      fieldName: 'sourceRepository',
      label: '来源仓库',
      rules: z.string().trim().min(1, '请输入来源仓库').max(500),
    },
    {
      component: 'Input',
      componentProps: {
        maxlength: 128,
        placeholder: '固定 commit、tag 或 revision',
      },
      fieldName: 'sourceRevision',
      label: '固定 revision',
      rules: z.string().trim().min(1, '请输入固定 revision').max(128),
    },
    {
      component: 'Input',
      componentProps: { maxlength: 128, placeholder: '例如 Apache-2.0' },
      fieldName: 'licenseSpdx',
      label: 'SPDX 许可证',
      rules: z.string().trim().min(1, '请输入 SPDX 许可证').max(128),
    },
    {
      component: 'Textarea',
      componentProps: {
        autoSize: { maxRows: 12, minRows: 7 },
        placeholder:
          '{"schemaVersion":"1.0","taskType":"OBJECT_DETECTION","preprocess":{"color":"RGB","layout":"NCHW","dtype":"FLOAT32"},"decoder":{"type":"AUTO_DETECTION","labels":["person"]}}',
      },
      fieldName: 'runtimeManifest',
      help: '声明输入预处理和输出协议；常规模型无需新增业务 Adapter。',
      label: 'Runtime Manifest',
      rules: z
        .string()
        .trim()
        .min(1, '请输入 Runtime Manifest')
        .refine(
          isRuntimeManifest,
          'Manifest 必须是包含 schemaVersion、taskType、preprocess、decoder 的 JSON',
        ),
    },
  ],
  showDefaultActions: false,
});

function isRuntimeManifest(value: string) {
  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    return (
      parsed.schemaVersion === '1.0' &&
      typeof parsed.taskType === 'string' &&
      typeof parsed.preprocess === 'object' &&
      typeof parsed.decoder === 'object'
    );
  } catch {
    return false;
  }
}

function beforeUpload(file: FileType) {
  fileFormApi.setFieldValue('file', file);
  return false;
}

async function reset() {
  currentStep.value = 0;
  model.value = undefined;
  fileList.value = [];
  confirmation.value = {};
  await Promise.all([fileFormApi.resetForm(), metadataFormApi.resetForm()]);
}

async function submit() {
  if (!model.value?.id) return;
  const fileValues = await fileFormApi.getValues();
  const metadataValues = await metadataFormApi.getValues();
  const file = fileValues.file as File | undefined;
  if (!file) return;

  drawerApi.lock();
  try {
    await uploadModelVersion({
      file,
      licenseSpdx: metadataValues.licenseSpdx,
      modelId: model.value.id,
      runtimeManifest: metadataValues.runtimeManifest,
      sourceRepository: metadataValues.sourceRepository,
      sourceRevision: metadataValues.sourceRevision,
      version: fileValues.version,
    });
    await drawerApi.close();
    emit('success');
    message.success('模型版本已上传，并完成 SHA256 与格式校验');
  } finally {
    drawerApi.unlock();
  }
}

const [Drawer, drawerApi] = useVbenDrawer({
  async onConfirm() {
    if (currentStep.value === 0) {
      const { valid } = await fileFormApi.validate();
      if (valid) currentStep.value = 1;
      return;
    }
    if (currentStep.value === 1) {
      const { valid } = await metadataFormApi.validate();
      if (valid) {
        confirmation.value = {
          ...(await fileFormApi.getValues()),
          ...(await metadataFormApi.getValues()),
        };
        currentStep.value = 2;
      }
      return;
    }
    await submit();
  },
  async onOpenChange(isOpen) {
    if (!isOpen) {
      await reset();
      return;
    }
    model.value = drawerApi.getData<AiVideoModelApi.Model>();
  },
});
</script>

<template>
  <Drawer
    class="w-[720px] max-w-[calc(100vw-32px)]"
    :confirm-text="confirmText"
    :title="`上传模型版本 · ${model?.name ?? ''}`"
  >
    <div class="space-y-5 px-3 py-2">
      <Steps :current="currentStep" :items="stepItems" size="small" />

      <Alert
        v-if="currentStep === 0"
        message="模型文件上传后不可原地覆盖；相同版本号或相同 SHA256 会被拒绝。"
        show-icon
        type="info"
      />
      <FileForm v-show="currentStep === 0">
        <template #file>
          <Upload.Dragger
            v-model:file-list="fileList"
            accept=".onnx,.pt,.pth,.jit,.torchscript,.engine,.rknn,.zip"
            :before-upload="beforeUpload"
            :max-count="1"
          >
            <p class="font-medium">点击或拖拽模型文件到此区域</p>
            <p class="text-muted-foreground mt-1 text-xs">
              上传后由控制面计算 SHA256，并根据实际扩展名完成格式探测。
            </p>
          </Upload.Dragger>
        </template>
      </FileForm>

      <Alert
        v-if="currentStep === 1"
        message="来源必须固定到可复现的 commit、tag 或 revision；许可证仅作资产来源说明，不参与发布审核。"
        show-icon
        type="info"
      />
      <MetadataForm v-show="currentStep === 1" />

      <template v-if="currentStep === 2">
        <Alert
          message="信息完整。上传成功后版本进入草稿状态，可在格式校验通过后发布。"
          show-icon
          type="success"
        />
        <Descriptions bordered :column="1" size="small">
          <DescriptionsItem label="模型资产">
            {{ model?.name }}
          </DescriptionsItem>
          <DescriptionsItem label="版本">
            {{ confirmation.version }}
          </DescriptionsItem>
          <DescriptionsItem label="文件">
            {{ fileList[0]?.name }}
          </DescriptionsItem>
          <DescriptionsItem label="来源仓库">
            {{ confirmation.sourceRepository }}
          </DescriptionsItem>
          <DescriptionsItem label="固定 revision">
            {{ confirmation.sourceRevision }}
          </DescriptionsItem>
          <DescriptionsItem label="许可证">
            {{ confirmation.licenseSpdx }}
          </DescriptionsItem>
          <DescriptionsItem label="Runtime Manifest">
            <pre class="max-h-40 overflow-auto whitespace-pre-wrap text-xs">{{
              confirmation.runtimeManifest
            }}</pre>
          </DescriptionsItem>
        </Descriptions>
      </template>
    </div>

    <template #prepend-footer>
      <Button v-if="currentStep > 0" @click="currentStep--"> 上一步 </Button>
    </template>
  </Drawer>
</template>
