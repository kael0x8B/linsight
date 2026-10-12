<script setup lang="ts">
import type { AlgorithmPackage } from '#/api/ai-video/algorithm/package';

import { computed, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { downloadFileFromBlobPart } from '@vben/utils';

import {
  Alert,
  Button,
  Empty,
  message,
  Spin,
  Tag,
  Upload,
} from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { publishPipeline } from '#/api/ai-video/algorithm';
import {
  algorithmCategoryLabels,
  getAlgorithmPackageDownloadUrl,
  listAlgorithmPackages,
  uploadAlgorithmPackage,
} from '#/api/ai-video/algorithm/package';

const emit = defineEmits(['change']);
const { hasAccessByCodes: can } = useAccess();
const packages = ref<AlgorithmPackage[]>([]);
const loading = ref(false);
const error = ref('');
const search = ref('');
const category = ref<string>();
const [Filters] = useVbenForm({
  showDefaultActions: false,
  wrapperClass: 'grid-cols-1 sm:grid-cols-2 max-w-[640px]',
  commonConfig: { hideLabel: true },
  schema: [
    {
      fieldName: 'search',
      label: '搜索算法名称或用途',
      component: 'Input',
      componentProps: {
        placeholder: '搜索算法名称或用途',
        allowClear: true,
        onChange: (event: Event) => {
          search.value = (event.target as HTMLInputElement).value;
        },
      },
    },
    {
      fieldName: 'category',
      label: '算法类型',
      component: 'Select',
      componentProps: {
        placeholder: '全部算法类型',
        allowClear: true,
        options: Object.entries(algorithmCategoryLabels).map(
          ([value, label]) => ({ value, label }),
        ),
        onChange: (value?: string) => {
          category.value = value;
        },
      },
    },
  ],
});
const selected = ref<AlgorithmPackage>();
const uploading = ref(false);
const downloading = ref<number>();
const [Guide, guide] = useVbenModal({
  title: '如何制作和上传算法包',
  showConfirmButton: false,
  class: 'w-[720px]',
});
const [Detail, detailApi] = useVbenModal({
  title: '算法包详情',
  showConfirmButton: false,
});
const current = computed(() =>
  packages.value.filter(
    (item) =>
      item.current ||
      (!packages.value.some(
        (other) => other.algorithmId === item.algorithmId && other.current,
      ) &&
        !packages.value.some(
          (other) =>
            other.algorithmId === item.algorithmId &&
            other.pipelineVersionId > item.pipelineVersionId,
        )),
  ),
);
const visible = computed(() =>
  current.value.filter(
    (item) =>
      (!category.value || item.manifest.category === category.value) &&
      `${item.manifest.name} ${item.manifest.description ?? ''}`.includes(
        search.value.trim(),
      ),
  ),
);
async function refresh() {
  loading.value = true;
  error.value = '';
  try {
    packages.value = await listAlgorithmPackages();
  } catch {
    error.value = '算法包加载失败，请重试。';
  } finally {
    loading.value = false;
  }
}
async function upload(file: File) {
  if (!file.name.toLowerCase().endsWith('.zip')) {
    message.warning('请选择算法 ZIP 文件');
    return false;
  }
  if (file.size > 8 * 1024 * 1024) {
    message.warning('算法包最大 8 MB，模型请单独上传');
    return false;
  }
  uploading.value = true;
  try {
    selected.value = await uploadAlgorithmPackage(file);
    await refresh();
    detailApi.open();
    emit('change');
  } catch {
    message.error('上传未完成，请检查包结构和版本号后重试');
  } finally {
    uploading.value = false;
  }
  return false;
}
async function publish(item: AlgorithmPackage) {
  loading.value = true;
  try {
    await publishPipeline(item.pipelineVersionId);
    await refresh();
    selected.value = packages.value.find(
      (p) => p.pipelineVersionId === item.pipelineVersionId,
    );
    emit('change');
    message.success('已设为当前版本，新建配置可使用；运行中的任务保持原版本');
  } finally {
    loading.value = false;
  }
}
async function download(item: AlgorithmPackage) {
  downloading.value = item.pipelineVersionId;
  try {
    const url = await getAlgorithmPackageDownloadUrl(item.pipelineVersionId);
    const response = await fetch(url, { credentials: 'omit' });
    if (!response.ok) throw new Error('download failed');
    const data = await response.arrayBuffer();
    if (crypto.subtle) {
      const digest = [
        ...new Uint8Array(await crypto.subtle.digest('SHA-256', data)),
      ]
        .map((b) => b.toString(16).padStart(2, '0'))
        .join('');
      if (digest !== item.sha256) throw new Error('hash mismatch');
    }
    downloadFileFromBlobPart({
      fileName: `${item.manifest.code}-${item.manifest.version}.zip`,
      source: new Blob([data], { type: 'application/zip' }),
    });
  } catch {
    message.error('下载失败或文件校验不通过，请重试');
  } finally {
    downloading.value = undefined;
  }
}
function show(item: AlgorithmPackage) {
  selected.value = item;
  detailApi.open();
}
onMounted(refresh);
</script>

<template>
  <section class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h3 class="text-base font-semibold">算法包</h3>
        <p class="text-muted-foreground mt-1">
          按算法管理版本；下载的 ZIP 可直接安装到其他网关。
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button @click="guide.open()">包内容与制作说明</Button
        ><Button @click="refresh">刷新</Button
        ><Upload
          v-if="can(['ai-video:algorithm:create', 'ai-video:algorithm:update'])"
          :before-upload="upload"
          :show-upload-list="false"
          accept=".zip"
        >
          <Button type="primary" :loading="uploading">
            <IconifyIcon icon="lucide:package-plus" />上传算法包
          </Button>
        </Upload>
      </div>
    </div>
    <Filters />
    <Alert v-if="error" :message="error" type="error" show-icon>
      <template #action>
        <Button @click="refresh">重试</Button>
      </template>
    </Alert>
    <Spin :spinning="loading">
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
        <article
          v-for="item in visible"
          :key="item.pipelineVersionId"
          class="bg-card flex flex-col rounded-xl border p-5"
        >
          <div class="mb-3 flex items-center justify-between">
            <IconifyIcon
              icon="lucide:package"
              class="text-primary size-7"
            /><Tag :color="item.current ? 'green' : 'orange'">
              {{ item.current ? '可使用' : '待发布' }}
            </Tag>
          </div>
          <h3 class="text-base font-semibold">{{ item.manifest.name }}</h3>
          <p class="text-muted-foreground my-3 min-h-10">
            {{ item.manifest.description || '暂无用途说明' }}
          </p>
          <div class="mb-4 flex flex-wrap gap-2">
            <Tag>
              {{
                algorithmCategoryLabels[item.manifest.category ?? 'GENERAL'] ??
                item.manifest.category
              }} </Tag
            ><Tag>v{{ item.manifest.version }}</Tag
            ><Tag>{{ item.manifest.models.length }} 项模型依赖</Tag>
          </div>
          <div class="mt-auto flex gap-2">
            <Button class="flex-1" @click="show(item)">详情与版本</Button
            ><Button
              :loading="downloading === item.pipelineVersionId"
              @click="download(item)"
            >
              下载 ZIP
            </Button>
          </div>
        </article>
      </div>
      <Empty
        v-if="!loading && !visible.length"
        description="暂无符合条件的算法包；上传算法包后可发布使用"
      />
    </Spin>

    <Guide
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
      class="ai-dialog w-[720px]"
    >
      <div class="space-y-5 p-2 text-sm leading-6">
        <p>
          算法包定义“如何识别和输出候选结果”；模型文件提供推理能力，在模型中心单独管理。
        </p>
        <div class="rounded-lg bg-muted p-4 font-mono text-xs leading-7">
          my-algorithm.zip<br />├─ algorithm.json
          算法说明、模型依赖、配置项与默认告警规则<br />├─ processor.py
          识别处理入口<br />└─ README.md 使用说明（可选）
        </div>
        <ol class="list-decimal space-y-3 pl-5">
          <li>
            下载下方现有算法包作为示例，解压后修改处理逻辑和 algorithm.json。
          </li>
          <li>
            新算法修改 code 和 name；更新已有算法必须提高
            version，同一版本不能覆盖。
          </li>
          <li>
            将这些文件直接压在 ZIP
            根目录，上传后检查模型依赖，再点击“发布此版本”。
          </li>
          <li>进入网关添加识别算法，选择摄像头，确认模型和告警条件后启动。</li>
        </ol>
        <p class="text-muted-foreground">
          支持 SDK 1.0。ZIP 最大 8 MB，包含 Python、JSON、TXT 或 Markdown
          文件；ONNX / RKNN 权重请上传到模型中心。跌倒、车辆违停示例包附带 SDK
          说明。
        </p>
        <div class="space-y-2">
          <strong>下载可用示例</strong>
          <div
            v-for="item in current"
            :key="item.pipelineVersionId"
            class="flex items-center justify-between border-b py-2"
          >
            <span>{{ item.manifest.name }} · v{{ item.manifest.version }}</span
            ><Button
              size="small"
              :loading="downloading === item.pipelineVersionId"
              @click="download(item)"
            >
              下载 ZIP
            </Button>
          </div>
        </div>
      </div>
    </Guide>
    <Detail
      class="ai-dialog w-[720px]"
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
    >
      <div v-if="selected" class="space-y-4 p-2">
        <h3 class="text-lg font-semibold">{{ selected.manifest.name }}</h3>
        <p>{{ selected.manifest.description }}</p>
        <div>
          <strong>模型依赖</strong>
          <div
            v-for="role in selected.manifest.models"
            :key="role.slot"
            class="mt-2 rounded border p-3"
          >
            {{ role.name || role.slot }} ·
            {{ role.formats?.join(' / ') || '按模型契约匹配' }}
            <p class="text-muted-foreground">{{ role.labels?.join('、') }}</p>
          </div>
        </div>
        <div>
          <strong>配置项</strong>
          <p class="mt-2">
            {{
              Object.entries(selected.manifest.parameterSchema.properties)
                .map(([key, value]) => value.title || key)
                .join('、') || '使用算法默认配置'
            }}
          </p>
        </div>
        <div>
          <strong>版本记录</strong>
          <div
            v-for="version in packages.filter(
              (item) => item.algorithmId === selected?.algorithmId,
            )"
            :key="version.pipelineVersionId"
            class="mt-2 flex items-center justify-between rounded border p-3"
          >
            <span
              >v{{ version.manifest.version }}
              <Tag v-if="version.current" color="green">当前版本</Tag></span
            >
            <div class="flex gap-2">
              <Button
                :loading="downloading === version.pipelineVersionId"
                @click="download(version)"
              >
                下载 ZIP </Button
              ><Button
                v-if="!version.current && can(['ai-video:algorithm:publish'])"
                :loading="loading"
                @click="publish(version)"
              >
                {{
                  version.status === 'PUBLISHED' ? '切换到此版本' : '发布此版本'
                }}
              </Button>
            </div>
          </div>
        </div>
      </div>
    </Detail>
  </section>
</template>
