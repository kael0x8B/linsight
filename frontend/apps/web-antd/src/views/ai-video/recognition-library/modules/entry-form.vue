<script lang="ts" setup>
import type { VbenFormSchema } from '#/adapter/form';
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';

import { computed, nextTick, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { message } from 'ant-design-vue';

import { useVbenForm, z } from '#/adapter/form';
import {
  createRecognitionEntry,
  updateRecognitionEntry,
} from '#/api/ai-video/recognition-library';
import { ImageUpload } from '#/components/upload';

const emit = defineEmits(['success']);
const libraryType = ref<AiVideoRecognitionLibraryApi.LibraryType>('FACE');
const libraryId = ref<number>();
const existing = ref<AiVideoRecognitionLibraryApi.Entry>();
const photo = ref('');
const saving = ref(false);
const isFace = computed(() => libraryType.value === 'FACE');
const title = computed(() => {
  if (isFace.value) return existing.value ? '编辑人员' : '添加人员';
  return existing.value ? '编辑参考条目' : '录入参考条目';
});

function typeText(face: string, plate: string, pose: string) {
  if (isFace.value) return face;
  if (libraryType.value === 'PLATE') return plate;
  return pose;
}

function fields(): VbenFormSchema[] {
  const nameLabel = typeText('人员姓名', '车辆名称', '姿态名称');
  const codeLabel = typeText('工号 / 人员编号', '车牌号码', '姿态编码');
  return [
    {
      fieldName: 'name',
      label: nameLabel,
      component: 'Input',
      componentProps: { placeholder: `请输入${nameLabel}`, maxlength: 100 },
      rules: z.string().trim().min(1, `请输入${nameLabel}`),
    },
    {
      fieldName: 'externalCode',
      label: codeLabel,
      component: 'Input',
      componentProps: { placeholder: `请输入${codeLabel}`, maxlength: 64 },
      rules: z.string().trim().min(1, `请输入${codeLabel}`),
    },
    {
      fieldName: isFace.value ? 'department' : 'category',
      label: isFace.value ? '部门 / 人员分组' : '业务分类',
      component: 'Input',
      componentProps: {
        placeholder: typeText(
          '选填，如生产一部',
          '选填，如内部车辆',
          '选填，如作业姿态',
        ),
        maxlength: 100,
      },
    },
    {
      fieldName: 'riskLevel',
      label: '风险等级',
      component: 'Select',
      defaultValue: 'NORMAL',
      componentProps: {
        options: [
          { label: '普通', value: 'NORMAL' },
          { label: '关注', value: 'WATCH' },
          { label: '高风险', value: 'HIGH' },
        ],
      },
    },
    ...(isFace.value
      ? []
      : [
          {
            fieldName: 'featureStatus',
            label: '特征状态',
            component: 'Select' as const,
            defaultValue: 'PENDING',
            componentProps: {
              options: [
                { label: '待提取', value: 'PENDING' },
                { label: '已就绪', value: 'READY' },
                { label: '失败', value: 'FAILED' },
              ],
            },
          },
        ]),
    {
      fieldName: 'description',
      label: '备注',
      component: 'Textarea',
      formItemClass: 'col-span-full',
      componentProps: {
        placeholder: '填写需要补充的信息（选填）',
        maxlength: 500,
        rows: 3,
        showCount: true,
      },
    },
    {
      fieldName: 'status',
      label: '启用状态',
      component: 'RadioGroup',
      defaultValue: 0,
      formItemClass: 'col-span-full',
      componentProps: {
        options: [
          { label: '启用', value: 0 },
          { label: '停用', value: 1 },
        ],
      },
    },
  ];
}
const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' } },
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  showDefaultActions: false,
  schema: [],
});
const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    const validation = await formApi.validate();
    if (!validation.valid || !libraryId.value) return;
    const values = await formApi.getValues();
    const data: AiVideoRecognitionLibraryApi.EntrySave = {
      id: existing.value?.id,
      libraryId: libraryId.value,
      name: String(values.name).trim(),
      externalCode: String(values.externalCode).trim(),
      mediaRef: photo.value,
      featureStatus: isFace.value
        ? (existing.value?.featureStatus ?? 'PENDING')
        : values.featureStatus,
      status: values.status,
      attributes: {
        ...existing.value?.attributes,
        schemaVersion: '1.0',
        category: String(values.category ?? ''),
        department: String(values.department ?? ''),
        description: String(values.description ?? ''),
        riskLevel: String(values.riskLevel ?? 'NORMAL'),
      },
    };
    modalApi.lock();
    saving.value = true;
    try {
      await (data.id ? updateRecognitionEntry : createRecognitionEntry)(data);
      message.success(
        existing.value
          ? '修改已保存'
          : typeText('人员已添加', '参考条目已录入', '参考条目已录入'),
      );
      await modalApi.close();
      emit('success');
    } finally {
      saving.value = false;
      modalApi.unlock();
    }
  },
  async onOpenChange(open) {
    if (!open) return;
    const data = modalApi.getData<{
      item?: AiVideoRecognitionLibraryApi.Entry;
      libraryId: number;
      libraryType: AiVideoRecognitionLibraryApi.LibraryType;
    }>();
    libraryType.value = data.libraryType;
    libraryId.value = data.libraryId;
    existing.value = data.item;
    photo.value = data.item?.mediaRef ?? '';
    formApi.setState({ schema: fields() });
    await nextTick();
    await formApi.resetForm({
      values: {
        name: data.item?.name ?? '',
        externalCode: data.item?.externalCode ?? '',
        status: data.item?.status ?? 0,
        featureStatus: data.item?.featureStatus ?? 'PENDING',
        category: String(data.item?.attributes.category ?? ''),
        department: String(data.item?.attributes.department ?? ''),
        description: String(data.item?.attributes.description ?? ''),
        riskLevel: String(data.item?.attributes.riskLevel ?? 'NORMAL'),
      },
      errors: {},
      touched: {},
      submitCount: 0,
    });
  },
});
</script>

<template>
  <Modal
    :title="title"
    confirm-text="保存"
    class="w-[760px] max-w-[calc(100vw-32px)]"
  >
    <div class="entry-editor">
      <section
        class="entry-photo"
        :aria-label="isFace ? '人员照片' : '参考图片'"
      >
        <h3>{{ isFace ? '人员照片' : '参考图片' }}</h3>
        <ImageUpload
          v-model="photo"
          :disabled="saving"
          directory="ai-video/recognition-library"
          :accept="isFace ? ['jpg', 'jpeg', 'png'] : undefined"
          :max-number="1"
          :max-size="5"
          :show-description="false"
        />
        <p class="photo-format">
          {{ isFace ? 'JPG / PNG · 5 MB 以内' : '图片大小不超过 5 MB' }}
        </p>
        <p v-if="isFace" class="photo-guidance">使用清晰、完整的单人正面照</p>
        <p
          v-if="isFace && existing && photo !== existing.mediaRef"
          class="photo-change"
        >
          照片变更后需重新提取特征
        </p>
      </section>
      <Form class="min-w-0" />
    </div>
  </Modal>
</template>

<style scoped>
.entry-editor {
  display: grid;
  grid-template-columns: 168px minmax(0, 1fr);
  gap: 28px;
  padding: 8px 8px 4px;
}

.entry-photo h3 {
  margin: 0 0 12px;
  font-size: 14px;
  font-weight: 500;
}

.entry-photo :deep(.ant-upload-select),
.entry-photo :deep(.ant-upload-list-item-container) {
  width: 168px !important;
  height: 190px !important;
  margin: 0 !important;
}

.entry-photo :deep(.ant-upload-select) {
  background: hsl(var(--muted) / 45%);
  border-color: hsl(var(--border));
  border-radius: 12px;
}

.entry-photo :deep(.ant-upload-list-item) {
  border-radius: 12px;
}

.entry-photo :deep(.ant-upload-list-item-thumbnail img) {
  object-fit: contain;
}

.photo-format,
.photo-guidance,
.photo-change {
  margin: 10px 0 0;
  font-size: 12px;
  line-height: 1.6;
  color: hsl(var(--muted-foreground));
}

.photo-guidance {
  margin-top: 4px;
}

.photo-change {
  color: hsl(var(--foreground));
}

@media (width <= 640px) {
  .entry-photo :deep(.ant-upload-select),
  .entry-photo :deep(.ant-upload-list-item-container) {
    width: 128px !important;
    height: 144px !important;
  }

  .entry-editor {
    grid-template-columns: minmax(0, 1fr);
    gap: 20px;
  }

  .entry-photo {
    justify-self: center;
    text-align: center;
  }
}
</style>
