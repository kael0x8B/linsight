<script setup lang="ts">
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, nextTick, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Empty, Spin, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  getPipelineVersions,
  getRunnableAlgorithms,
} from '#/api/ai-video/algorithm';
import { getTaskPage } from '#/api/ai-video/task';

import AlgorithmConfiguration from './algorithm-configuration.vue';
import PackageConfiguration from './package-task-modal.vue';

const emit = defineEmits<{
  inspect: [algorithm: AiVideoAlgorithmApi.Algorithm];
}>();
const { hasAccessByCodes: can } = useAccess();
const items = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const tasks = ref<AiVideoTaskApi.Task[]>([]);
const taskStateAvailable = ref(false);
const loading = ref(false);
const error = ref('');
const search = ref('');
const category = ref('');
const selected = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const versions = ref<AiVideoAlgorithmApi.PipelineVersion[]>([]);
const detailLoading = ref(false);
const detailError = ref('');
const [Details, details] = useVbenModal({
  title: '算法详情',
  showConfirmButton: false,
  class: 'w-[760px]',
});
const [Configuration, configuration] = useVbenModal({
  connectedComponent: AlgorithmConfiguration,
  destroyOnClose: true,
});
const [PackConfiguration, packConfiguration] = useVbenModal({
  connectedComponent: PackageConfiguration,
  destroyOnClose: true,
});
const [Filters] = useVbenForm({
  showDefaultActions: false,
  wrapperClass: 'grid-cols-1 sm:grid-cols-2 max-w-[720px]',
  commonConfig: { hideLabel: true },
  schema: [
    {
      fieldName: 'search',
      label: '搜索算法',
      component: 'Input',
      componentProps: {
        placeholder: '搜索算法名称或用途',
        allowClear: true,
        onChange: (e: Event) => {
          search.value = (e.target as HTMLInputElement).value;
        },
      },
    },
    {
      fieldName: 'category',
      label: '配置方式',
      component: 'Select',
      componentProps: {
        placeholder: '全部配置方式',
        allowClear: true,
        options: [
          { value: 'package', label: '可上传算法包' },
          { value: 'builtin', label: '内置编排' },
        ],
        onChange: (v?: string) => {
          category.value = v ?? '';
        },
      },
    },
  ],
});
function isPack(item: AiVideoAlgorithmApi.Algorithm) {
  return !!item.capabilityKey?.startsWith('package.');
}
// One entry per named capability; older configurations keep their pinned implementation.
const groups = computed(() => {
  const names = new Map<string, AiVideoAlgorithmApi.Algorithm[]>();
  for (const item of items.value)
    names.set(item.name, [...(names.get(item.name) ?? []), item]);
  return [...names.values()].map((members) => {
    const item = members.find((member) => isPack(member)) ?? members[0]!;
    const configured = tasks.value.filter((task) =>
      members.some((a) => a.id === task.algorithmId),
    );
    return {
      item,
      members,
      count: configured.length,
      running: configured.filter((t) => t.actualStatus === 'RUNNING').length,
    };
  });
});
const visible = computed(() =>
  groups.value.filter(
    ({ item }) =>
      (!category.value || (category.value === 'package') === isPack(item)) &&
      `${item.name} ${item.description ?? ''}`
        .toLowerCase()
        .includes(search.value.trim().toLowerCase()),
  ),
);
function state(item: AiVideoAlgorithmApi.Algorithm) {
  if (!item.currentPipelineVersionId)
    return { label: '待发布', color: 'default', runnable: false };
  if (isPack(item) || item.pipelineAcceptanceStatus === 'PASS')
    return { label: '可配置', color: 'blue', runnable: true };
  if (item.pipelineAcceptanceStatus === 'PENDING')
    return { label: '可试运行', color: 'orange', runnable: true };
  return {
    label:
      item.pipelineAcceptanceStatus === 'BLOCKED_EXTERNAL_ASSETS'
        ? '缺少模型或素材'
        : '尚未就绪',
    color: 'orange',
    runnable: false,
  };
}
function icon(item: AiVideoAlgorithmApi.Algorithm) {
  if (item.sceneGroup === 'PPE') return 'lucide:hard-hat';
  if (item.sceneGroup === 'FIRE_SMOKE') return 'lucide:flame';
  if (item.sceneGroup === 'IDENTITY') return 'lucide:scan-face';
  if (item.sceneGroup === 'BEHAVIOR') return 'lucide:activity';
  if (item.eventType === 'VEHICLE_STATIONARY') return 'lucide:car';
  return 'lucide:scan-search';
}
function configure(item: AiVideoAlgorithmApi.Algorithm) {
  if (isPack(item))
    packConfiguration
      .setData({ pipelineVersionId: item.currentPipelineVersionId })
      .open();
  else configuration.setData({ algorithmId: item.id }).open();
}
async function configurePipelineFromSelector(
  algorithmId: number,
  nodeId?: number,
  cameraId?: number,
) {
  await nextTick();
  configuration.setData({ algorithmId, nodeId, cameraId }).open();
}
function acceptance(item: AiVideoAlgorithmApi.Algorithm) {
  const pipeline = versions.value.find(
    (v) => v.id === item.currentPipelineVersionId,
  );
  if (!pipeline) return { label: '验证记录未加载', note: '' };
  const record = pipeline.dag.acceptance as Record<string, unknown> | undefined;
  if (!record)
    return {
      label: '尚无现场验收记录',
      note: '发布和结构校验通过表示可以配置运行，不代表现场准确率已经验收。',
    };
  if (record.status === 'PENDING')
    return {
      label: '现场效果待确认',
      note: String(
        record.note ??
          '运行时间不会自动转为验收结果，需要正反样本、误报漏报和性能记录。',
      ),
    };
  return {
    label: record.status === 'PASS' ? '已有验证记录' : '验证条件未满足',
    note: String(
      record.note ?? record.source ?? '请查看编排中的验证记录及证据。',
    ),
  };
}
async function show(members: AiVideoAlgorithmApi.Algorithm[]) {
  selected.value = members;
  versions.value = [];
  detailError.value = '';
  details.open();
  detailLoading.value = true;
  try {
    const memberVersions = await Promise.all(
      members.map((item) => getPipelineVersions(item.id)),
    );
    versions.value = memberVersions.flat();
  } catch {
    detailError.value = '版本记录加载失败，请关闭后重试。';
  } finally {
    detailLoading.value = false;
  }
}
async function refresh() {
  if (loading.value) return;
  loading.value = true;
  error.value = '';
  taskStateAvailable.value = false;
  try {
    items.value = await getRunnableAlgorithms();
    tasks.value = [];
    if (can(['ai-video:task:query'])) {
      try {
        for (let pageNo = 1; ; pageNo++) {
          const page = await getTaskPage({ pageNo, pageSize: 100 });
          tasks.value.push(...page.list);
          if (tasks.value.length >= page.total || page.list.length === 0) break;
        }
        taskStateAvailable.value = true;
      } catch {
        /* Availability remains explicit; never claim zero running tasks. */
      }
    }
  } catch {
    error.value = '算法目录加载失败，请重试。';
  } finally {
    loading.value = false;
  }
}
defineExpose({ refresh });
onMounted(refresh);
</script>
<template>
  <section class="space-y-4">
    <Configuration @success="refresh" /><PackConfiguration
      @success="refresh"
      @select-pipeline="configurePipelineFromSelector"
    />
    <div
      class="flex flex-wrap items-start justify-between gap-3 rounded-xl border bg-card p-4"
    >
      <Filters class="flex-1" /><Button :loading="loading" @click="refresh">
        刷新目录
      </Button>
    </div>
    <Alert v-if="error" type="error" show-icon :message="error" />
    <div
      class="flex items-center justify-between text-sm text-muted-foreground"
    >
      <span>共 {{ visible.length }} 个算法</span>
    </div>
    <Spin :spinning="loading">
      <div class="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <article
          v-for="group in visible"
          :key="group.item.id"
          class="flex min-h-[250px] flex-col rounded-xl border bg-card p-4"
        >
          <div class="mb-4 flex items-center justify-between">
            <div class="rounded-xl bg-primary/10 p-2 text-primary">
              <IconifyIcon :icon="icon(group.item)" class="size-6" />
            </div>
            <Tag :color="state(group.item).color">
              {{ state(group.item).label }}
            </Tag>
          </div>
          <h3 class="text-base font-semibold">{{ group.item.name }}</h3>
          <p class="text-muted-foreground my-3 line-clamp-2 text-sm leading-6">
            {{ group.item.description || '选择摄像头和网关配置识别。' }}
          </p>
          <div
            class="mt-auto mb-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground"
          >
            <span>{{ isPack(group.item) ? '算法包' : '内置编排' }}</span
            ><span>·</span
            ><span v-if="taskStateAvailable">{{ group.count }} 个配置</span
            ><span v-else>运行情况暂不可用</span
            ><Tag v-if="taskStateAvailable && group.running" color="green">
              {{ group.running }} 个运行中
            </Tag>
          </div>
          <div class="flex items-center gap-2 border-t pt-3">
            <Button
              v-if="state(group.item).runnable && can(['ai-video:task:create'])"
              class="flex-1"
              type="primary"
              :disabled="!!error"
              @click="configure(group.item)"
            >
              配置识别
            </Button>
            <Button @click="show(group.members)">详情</Button>
          </div>
        </article>
      </div>
      <Empty
        v-if="!loading && !visible.length"
        description="暂无符合条件的算法，可清除筛选或到高级管理查看。"
      />
    </Spin>
    <Details
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
      class="ai-dialog w-[760px]"
    >
      <Spin :spinning="detailLoading">
        <div class="space-y-4 p-2">
          <Alert v-if="detailError" type="error" :message="detailError" />
          <h3 class="text-lg font-semibold">{{ selected[0]?.name }}</h3>
          <div
            v-for="item in selected"
            :key="item.id"
            class="rounded-lg border p-4"
          >
            <div class="flex items-center justify-between">
              <strong>{{ isPack(item) ? '算法包' : '内置编排' }}</strong
              ><Tag :color="state(item).color">{{ state(item).label }}</Tag>
            </div>
            <p class="mt-3 font-medium">{{ acceptance(item).label }}</p>
            <p class="mt-1 text-sm leading-6 text-muted-foreground">
              {{ acceptance(item).note }}
            </p>
            <div class="mt-4 flex gap-2">
              <Button
                v-if="state(item).runnable && can(['ai-video:task:create'])"
                @click="configure(item)"
              >
                使用此方式配置 </Button
              ><Button
                v-if="!isPack(item)"
                @click="
                  details.close();
                  emit('inspect', item);
                "
              >
                编排与验证记录
              </Button>
            </div>
          </div>
        </div>
      </Spin>
    </Details>
  </section>
</template>
