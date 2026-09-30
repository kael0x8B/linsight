<script setup lang="ts">
import type { ExecutableModelOption } from '#/api/ai-video/model';

import { computed, onMounted, ref } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Empty, Spin, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getExecutableModelOptions } from '#/api/ai-video/model';

import { modelExecutionDescription } from '../execution-presentation';
const emit = defineEmits<{ detail: [modelId: number, versionId: number] }>();
const items = ref<ExecutableModelOption[]>([]);
const search = ref('');
const format = ref<string>();
const loading = ref(false);
const error = ref('');
const [Filters] = useVbenForm({
  showDefaultActions: false,
  wrapperClass: 'grid-cols-1 sm:grid-cols-2 max-w-[640px]',
  commonConfig: { hideLabel: true },
  schema: [
    {
      fieldName: 'search',
      label: '搜索模型用途或版本',
      component: 'Input',
      componentProps: {
        placeholder: '搜索模型用途或版本',
        allowClear: true,
        onChange: (event: Event) => {
          search.value = (event.target as HTMLInputElement).value;
        },
      },
    },
    {
      fieldName: 'format',
      label: '运行格式',
      component: 'Select',
      componentProps: () => ({
        placeholder: '全部运行格式',
        allowClear: true,
        options: [...new Set(items.value.map((m) => m.format))].map(
          (value) => ({ value, label: value }),
        ),
        onChange: (value?: string) => {
          format.value = value;
        },
      }),
    },
  ],
});
const visible = computed(() =>
  items.value.filter(
    (m) =>
      (!format.value || m.format === format.value) &&
      `${m.name} ${m.version}`
        .toLowerCase()
        .includes(search.value.toLowerCase().trim()),
  ),
);
async function refresh() {
  loading.value = true;
  error.value = '';
  try {
    items.value = await getExecutableModelOptions();
  } catch {
    error.value = '可部署模型加载失败，请重试';
  } finally {
    loading.value = false;
  }
}
onMounted(refresh);
</script>
<template>
  <section class="space-y-4">
    <div class="flex items-start justify-between gap-3">
      <Filters class="flex-1" /><Button @click="refresh">刷新</Button>
    </div>
    <Alert v-if="error" :message="error" type="error" show-icon /><Spin
      :spinning="loading"
    >
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="item in visible"
          :key="item.id"
          class="bg-card flex flex-col rounded-xl border p-5"
        >
          <div class="mb-4 flex items-center justify-between">
            <IconifyIcon
              :icon="
                item.manifest?.taskType === 'FACE_VERIFICATION'
                  ? 'lucide:scan-face'
                  : 'lucide:scan-search'
              "
              class="text-primary size-8"
            /><Tag color="green">已验证可部署</Tag>
          </div>
          <h3 class="text-base font-semibold">{{ item.name }}</h3>
          <p class="text-muted-foreground mt-2">
            {{ modelExecutionDescription(item) }}
            · {{ item.format }}
          </p>
          <p class="mt-3 break-all text-sm">当前发布版本：{{ item.version }}</p>
          <p class="text-muted-foreground my-3 line-clamp-2 min-h-10 text-sm">
            {{
              item.manifest?.taskType === 'FACE_VERIFICATION'
                ? '人脸检测与特征提取，供人员库比对算法使用'
                : `输出类别：${item.manifest?.decoder?.labels?.slice(0, 8).join('、') || '详见模型说明'}${(item.manifest?.decoder?.labels?.length ?? 0) > 8 ? '等' : ''}`
            }}
          </p>
          <Button
            block
            class="mt-auto"
            @click="emit('detail', item.modelId, item.id)"
          >
            查看此版本与部署
          </Button>
        </article>
      </div>
      <Empty
        v-if="!loading && !visible.length"
        description="暂无符合条件的可部署模型，可到模型资产与历史版本上传、测试和发布"
      />
    </Spin>
  </section>
</template>
