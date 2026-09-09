<script lang="ts" setup>
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';

import { computed, reactive, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Alert, Form, FormItem, Input, message, RadioGroup, Select } from 'ant-design-vue';

import {
  createRecognitionEntry,
  updateRecognitionEntry,
} from '#/api/ai-video/recognition-library';
import { ImageUpload } from '#/components/upload';

const emit = defineEmits(['success']);
const libraryType = ref<AiVideoRecognitionLibraryApi.LibraryType>('FACE');
const form = reactive<Partial<AiVideoRecognitionLibraryApi.EntrySave>>({});
const attribute = reactive({ category: '', department: '', description: '', riskLevel: 'NORMAL' });

const titleLabel = computed(() => libraryType.value === 'FACE' ? '人员姓名' : libraryType.value === 'PLATE' ? '车辆名称' : '姿态名称');
const codeLabel = computed(() => libraryType.value === 'FACE' ? '工号/人员编号' : libraryType.value === 'PLATE' ? '车牌号码' : '姿态编码');

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    if (!form.name?.trim() || !form.externalCode?.trim()) {
      message.warning(`请填写${titleLabel.value}和${codeLabel.value}`);
      return;
    }
    form.attributes = { schemaVersion: '1.0', ...attribute };
    modalApi.lock();
    try {
      if (form.id) await updateRecognitionEntry(form as AiVideoRecognitionLibraryApi.EntrySave);
      else await createRecognitionEntry(form as AiVideoRecognitionLibraryApi.EntrySave);
      message.success(form.id ? '参考条目已更新' : '参考条目已录入');
      await modalApi.close();
      emit('success');
    } finally {
      modalApi.unlock();
    }
  },
  onOpenChange(open) {
    if (!open) return;
    const data = modalApi.getData<{
      item?: AiVideoRecognitionLibraryApi.Entry;
      libraryId: number;
      libraryType: AiVideoRecognitionLibraryApi.LibraryType;
    }>();
    libraryType.value = data.libraryType;
    const attrs = data.item?.attributes ?? {};
    Object.assign(attribute, {
      category: String(attrs.category ?? ''),
      department: String(attrs.department ?? ''),
      description: String(attrs.description ?? ''),
      riskLevel: String(attrs.riskLevel ?? 'NORMAL'),
    });
    Object.assign(form, data.item ?? {
      attributes: { schemaVersion: '1.0' },
      externalCode: '',
      featureStatus: 'PENDING',
      libraryId: data.libraryId,
      mediaRef: '',
      name: '',
      status: 0,
    });
  },
});
</script>

<template>
  <Modal :title="form.id ? '编辑参考条目' : '录入参考条目'" class="w-[680px] max-w-[calc(100vw-32px)]">
    <Alert v-if="libraryType==='FACE'" message="保存照片后，在人员卡片点击“提取特征”。只有网关校验通过，才能在摄像头中选用；更换照片后需要重新提取。" type="info" show-icon class="mb-4" />
    <Form :model="form" layout="vertical">
      <div class="grid grid-cols-[160px_1fr] gap-6">
        <FormItem label="参考图片">
          <ImageUpload v-model="form.mediaRef" directory="ai-video/recognition-library" :max-number="1" :max-size="5" />
        </FormItem>
        <div class="grid grid-cols-2 gap-x-4">
          <FormItem :label="titleLabel" required><Input v-model:value="form.name" /></FormItem>
          <FormItem :label="codeLabel" required><Input v-model:value="form.externalCode" /></FormItem>
          <FormItem v-if="libraryType === 'FACE'" label="部门/人员分组"><Input v-model:value="attribute.department" /></FormItem>
          <FormItem v-else label="业务分类"><Input v-model:value="attribute.category" :placeholder="libraryType === 'PLATE' ? '内部车/访客车/重点车辆' : '跌倒/攀爬/睡岗等'" /></FormItem>
          <FormItem label="风险等级">
            <Select v-model:value="attribute.riskLevel" :options="[
              { label: '普通', value: 'NORMAL' }, { label: '关注', value: 'WATCH' }, { label: '高风险', value: 'HIGH' },
            ]" />
          </FormItem>
          <FormItem v-if="libraryType !== 'FACE'" label="特征状态">
            <Select v-model:value="form.featureStatus" :options="[
              { label: '待提取', value: 'PENDING' }, { label: '已就绪', value: 'READY' }, { label: '失败', value: 'FAILED' },
            ]" />
          </FormItem>
        </div>
      </div>
      <FormItem label="说明"><Input.TextArea v-model:value="attribute.description" :maxlength="500" :rows="3" /></FormItem>
      <FormItem label="状态"><RadioGroup v-model:value="form.status" :options="[{ label: '启用', value: 0 }, { label: '停用', value: 1 }]" /></FormItem>
    </Form>
  </Modal>
</template>
