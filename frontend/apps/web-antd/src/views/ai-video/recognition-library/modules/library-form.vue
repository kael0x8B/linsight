<script lang="ts" setup>
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';

import { onMounted, reactive, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  RadioGroup,
  Select,
} from 'ant-design-vue';

import { getModelPage, getModelVersionList } from '#/api/ai-video/model';
import {
  createRecognitionLibrary,
  updateRecognitionLibrary,
} from '#/api/ai-video/recognition-library';

const emit = defineEmits(['success']);
const form = reactive<Partial<AiVideoRecognitionLibraryApi.LibrarySave>>({});
function defaultMatchMode(type: AiVideoRecognitionLibraryApi.LibraryType) {
  if (type === 'FACE') return 'ONE_TO_N';
  if (type === 'PLATE') return 'EXACT';
  return 'CLASSIFICATION';
}
const engineOptions = ref<Array<{ label: string; value: number }>>([]);

const modeOptions = [
  { label: '1:N 相似度检索', value: 'ONE_TO_N' },
  { label: '精确匹配', value: 'EXACT' },
  { label: '姿态分类', value: 'CLASSIFICATION' },
];

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    if (
      !form.name?.trim() ||
      !form.code?.trim() ||
      !form.libraryType ||
      !form.matchMode
    ) {
      message.warning('请完整填写名称、编码、类型和匹配方式');
      return;
    }
    modalApi.lock();
    try {
      await (form.id ? updateRecognitionLibrary : createRecognitionLibrary)(
        form as AiVideoRecognitionLibraryApi.LibrarySave,
      );
      message.success(form.id ? '参考库已更新' : '参考库已创建');
      await modalApi.close();
      emit('success');
    } finally {
      modalApi.unlock();
    }
  },
  onOpenChange(open) {
    if (!open) return;
    const data = modalApi.getData<{
      item?: AiVideoRecognitionLibraryApi.Library;
      libraryType: AiVideoRecognitionLibraryApi.LibraryType;
    }>();
    const type = data.libraryType;
    Object.assign(
      form,
      data.item ?? {
        code: '',
        description: '',
        featureDimension: type === 'FACE' ? 512 : undefined,
        libraryType: type,
        matchMode: defaultMatchMode(type),
        name: '',
        status: 0,
      },
    );
  },
});

onMounted(async () => {
  const models = await getModelPage({ pageNo: 1, pageSize: 100, status: 0 });
  const versionGroups = await Promise.all(
    models.list
      .filter((item) => item.id)
      .map(async (item) => ({
        item,
        versions: await getModelVersionList(item.id!),
      })),
  );
  engineOptions.value = versionGroups.flatMap(({ item, versions }) =>
    versions
      .filter(
        (version) =>
          version.publishStatus === 'PUBLISHED' &&
          version.executionStatus === 'READY',
      )
      .map((version) => ({
        label: `${item.name} / ${version.version}`,
        value: version.id,
      })),
  );
});
</script>

<template>
  <Modal
    :title="form.id ? '编辑识别参考库' : '新增识别参考库'"
    class="ai-dialog w-[640px] max-w-[calc(100vw-32px)]"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <Form :model="form" layout="vertical">
      <div class="grid grid-cols-2 gap-x-4">
        <FormItem label="参考库名称" required>
          <Input v-model:value="form.name" />
        </FormItem>
        <FormItem label="稳定编码" required>
          <Input
            v-model:value="form.code"
            :disabled="Boolean(form.id)"
            placeholder="例如 visitors-face"
          />
        </FormItem>
        <FormItem label="参考库类型" required>
          <Select
            v-model:value="form.libraryType"
            disabled
            :options="[
              { label: '人脸库', value: 'FACE' },
              { label: '车牌库', value: 'PLATE' },
              { label: '场景姿态库', value: 'POSE' },
            ]"
          />
        </FormItem>
        <FormItem label="匹配方式" required>
          <Select v-model:value="form.matchMode" :options="modeOptions" />
        </FormItem>
        <FormItem label="识别引擎">
          <Select
            v-model:value="form.engineModelVersionId"
            allow-clear
            show-search
            :options="engineOptions"
            placeholder="选择已发布且可执行的模型版本"
          />
        </FormItem>
        <FormItem label="特征维度">
          <InputNumber
            v-model:value="form.featureDimension"
            :max="8192"
            :min="1"
            class="w-full"
          />
        </FormItem>
      </div>
      <FormItem label="说明">
        <Input.TextArea
          v-model:value="form.description"
          :maxlength="500"
          :rows="3"
        />
      </FormItem>
      <FormItem label="状态">
        <RadioGroup
          v-model:value="form.status"
          :options="[
            { label: '启用', value: 0 },
            { label: '停用', value: 1 },
          ]"
        />
      </FormItem>
    </Form>
  </Modal>
</template>
