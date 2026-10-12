<script lang="ts" setup>
import type { TableColumnsType } from 'ant-design-vue';

import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoModelApi } from '#/api/ai-video/model';

import { computed, reactive, ref, watch } from 'vue';

import { useAccess } from '@vben/access';
import { Page, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';
import { formatDateTime } from '@vben/utils';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  Drawer,
  Empty,
  Input,
  message,
  Pagination,
  Segmented,
  Select,
  Space,
  Spin,
  Table,
  Tag,
  Textarea,
} from 'ant-design-vue';

import {
  getAlgorithmPage,
  getPipelineVersions,
  publishPipeline,
  savePipeline,
  validatePipeline,
} from '#/api/ai-video/algorithm';
import { getModelPage } from '#/api/ai-video/model';
import { AiPageHeader, AiStatusIndicator } from '#/components/ai-video';

import AlgorithmCatalog from './modules/algorithm-catalog.vue';
import AlgorithmForm from './modules/algorithm-form.vue';
import PackageCatalog from './modules/package-catalog.vue';
const packageView = ref(true);
const algorithmCatalog = ref<InstanceType<typeof AlgorithmCatalog>>();
const [VersionsModal, versionsModal] = useVbenModal({
  title: '算法包管理',
  showConfirmButton: false,
  class: 'w-[1000px]',
});

const { hasAccessByCodes } = useAccess();
const canCreate = computed(() =>
  hasAccessByCodes(['ai-video:algorithm:create']),
);
const canUpdate = computed(() =>
  hasAccessByCodes(['ai-video:algorithm:update']),
);
const canPublish = computed(() =>
  hasAccessByCodes(['ai-video:algorithm:publish']),
);

const loading = ref(false);
const error = ref('');
const algorithms = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const total = ref(0);
const query = reactive({
  category: '' as string | undefined,
  name: '',
  pageNo: 1,
  pageSize: 20,
  status: 0 as number | undefined,
});
const pipelineOpen = ref(false);
const selected = ref<AiVideoAlgorithmApi.Algorithm>();
const versions = ref<AiVideoAlgorithmApi.PipelineVersion[]>([]);
const dagText = ref('');
const editorMode = ref<'JSON' | 'VISUAL'>('VISUAL');
const modelCatalog = ref<AiVideoModelApi.Model[]>([]);
const modelsLoading = ref(false);
const modelsError = ref('');

async function loadModels() {
  modelsLoading.value = true;
  modelsError.value = '';
  try {
    const items: AiVideoModelApi.Model[] = [];
    let pageNo = 1;
    let total = 0;
    do {
      const page = await getModelPage({ pageNo, pageSize: 100 });
      items.push(...page.list);
      total = page.total;
      if (page.list.length === 0) break;
      pageNo += 1;
    } while (items.length < total);
    modelCatalog.value = items;
  } catch {
    modelsError.value = '模型目录加载失败，请确认模型查询权限并重试。';
  } finally {
    modelsLoading.value = false;
  }
}

function modelName(id: unknown) {
  if (id === null || id === undefined) return '未配置';
  return (
    modelCatalog.value.find((model) => model.id === id)?.name ??
    `模型 #${id}（未能读取）`
  );
}

function modelOptions(node: Record<string, unknown>) {
  const required =
    (
      {
        'detector.person': ['person'],
        'ppe.helmet': ['helmet', 'no_helmet'],
        'ppe.reflective-vest': ['vest', 'no_vest'],
      } as Record<string, string[]>
    )[String(node.capabilityKey)] ?? [];
  const options = modelCatalog.value.flatMap((model) => {
    if (model.id === null || model.id === undefined) return [];
    const missing = required.filter(
      (label) => !model.outputLabels?.includes(label),
    );
    let reason = '';
    if (model.status !== 0) reason = '停用';
    else if (missing.length > 0) reason = `缺少类别 ${missing.join('、')}`;
    return [
      {
        disabled: Boolean(reason),
        label: `${model.name} · ${model.artifactFormat ?? '未上传'} · ${model.latestVersion ?? '无版本'}${reason ? `（${reason}）` : ''}`,
        value: model.id,
      },
    ];
  });
  if (
    typeof node.modelId === 'number' &&
    !options.some((option) => option.value === node.modelId)
  ) {
    options.unshift({
      disabled: true,
      label: modelName(node.modelId),
      value: node.modelId,
    });
  }
  return options;
}

const nodeCatalog = [
  {
    capabilityKey: 'detector.coco',
    icon: 'lucide:scan-search',
    label: 'Detector',
    type: 'DETECTOR',
  },
  {
    capabilityKey: 'tracker.iou',
    icon: 'lucide:route',
    label: 'Tracker',
    type: 'TRACKER',
  },
  {
    capabilityKey: 'classifier.vehicle-type',
    icon: 'lucide:tags',
    label: 'Classifier',
    type: 'CLASSIFIER',
  },
  {
    capabilityKey: 'ocr.general',
    icon: 'lucide:scan-text',
    label: 'OCR',
    type: 'OCR',
  },
  {
    capabilityKey: 'pose.human',
    icon: 'lucide:person-standing',
    label: 'Pose',
    type: 'POSE',
  },
  {
    capabilityKey: 'segmentation.general',
    icon: 'lucide:spline',
    label: 'Segmenter',
    type: 'SEGMENTER',
  },
  {
    capabilityKey: 'recognition.face',
    icon: 'lucide:scan-face',
    label: 'Recognizer',
    type: 'RECOGNIZER',
  },
  {
    capabilityKey: 'quality.video',
    icon: 'lucide:scan-eye',
    label: 'Quality',
    type: 'QUALITY',
  },
  {
    capabilityKey: 'rule.composition',
    icon: 'lucide:git-branch',
    label: 'Rule',
    type: 'RULE',
  },
];

const visualNodes = computed<Record<string, unknown>[]>(() => {
  try {
    const dag = JSON.parse(dagText.value) as {
      nodes?: Record<string, unknown>[];
    };
    return Array.isArray(dag.nodes) ? dag.nodes : [];
  } catch {
    return [];
  }
});

const [AlgorithmModal, algorithmModalApi] = useVbenModal({
  connectedComponent: AlgorithmForm,
  destroyOnClose: true,
});

const versionColumns: TableColumnsType = [
  { dataIndex: 'version', key: 'version', title: '版本', width: 56 },
  {
    dataIndex: 'validationStatus',
    key: 'validationStatus',
    title: '校验状态',
    width: 88,
  },
  { dataIndex: 'createTime', key: 'createTime', title: '保存时间', width: 122 },
  { fixed: 'right', key: 'actions', title: '操作', width: 58 },
];

async function loadAlgorithms() {
  loading.value = true;
  error.value = '';
  try {
    const result = await getAlgorithmPage({
      category: query.category || undefined,
      name: query.name || undefined,
      pageNo: query.pageNo,
      pageSize: query.pageSize,
      status: query.status,
    });
    algorithms.value = result.list;
    total.value = result.total;
  } catch {
    error.value = '算法中心加载失败，请检查控制面后重试。';
  } finally {
    loading.value = false;
  }
}

function algorithmIcon(item: AiVideoAlgorithmApi.Algorithm) {
  const text = `${item.sceneGroup} ${item.name}`.toLowerCase();
  if (text.includes('person') || text.includes('人员') || text.includes('人脸'))
    return 'lucide:user-round-search';
  if (
    text.includes('vehicle') ||
    text.includes('车辆') ||
    text.includes('车牌')
  )
    return 'lucide:car-front';
  if (text.includes('fire') || text.includes('消防') || text.includes('火'))
    return 'lucide:flame';
  if (text.includes('ocr') || text.includes('文字')) return 'lucide:scan-text';
  if (
    text.includes('ppe') ||
    text.includes('安全帽') ||
    text.includes('反光衣')
  )
    return 'lucide:hard-hat';
  if (text.includes('quality') || text.includes('质量'))
    return 'lucide:scan-eye';
  return 'lucide:brain-circuit';
}

function categoryLabel(value: string) {
  return (
    { CORE: '核心算法', CUSTOM: '自定义', EXTENSION: '扩展能力' }[value] ??
    value
  );
}

function changeCategory(value: number | string | undefined) {
  query.category = value ? String(value) : '';
  query.pageNo = 1;
  void loadAlgorithms();
}

function changeStatus(value: number | string | undefined) {
  query.status =
    value === undefined || value === 'all' ? undefined : Number(value);
  query.pageNo = 1;
  void loadAlgorithms();
}

async function openPipeline(record: Record<string, unknown>) {
  selected.value = record as unknown as AiVideoAlgorithmApi.Algorithm;
  pipelineOpen.value = true;
  void loadModels();
  versions.value = await getPipelineVersions(selected.value.id);
  const current = versions.value.find(
    (item) => item.id === selected.value?.currentPipelineVersionId,
  );
  dagText.value = JSON.stringify(
    current?.dag ?? {
      edges: [],
      nodes: [
        {
          capabilityKey: selected.value.capabilityKey,
          id: 'capability-1',
          input: 'VIDEO_FRAME',
          output: 'DETECTIONS',
          type: 'DETECTOR',
        },
      ],
      schemaVersion: '1.0',
    },
    null,
    2,
  );
}

function addNode(item: (typeof nodeCatalog)[number]) {
  let dag: {
    edges: Record<string, unknown>[];
    nodes: Record<string, unknown>[];
    schemaVersion: string;
  };
  try {
    dag = JSON.parse(dagText.value);
  } catch {
    dag = { edges: [], nodes: [], schemaVersion: '1.0' };
  }
  dag.nodes ??= [];
  dag.edges ??= [];
  const id = `${item.type.toLowerCase()}-${dag.nodes.length + 1}`;
  const previous = dag.nodes.at(-1);
  dag.nodes.push({ capabilityKey: item.capabilityKey, id, type: item.type });
  if (previous?.id) dag.edges.push({ from: previous.id, to: id });
  dagText.value = JSON.stringify(dag, null, 2);
}

function updateVisualNode(index: number, field: string, value: unknown) {
  const dag = JSON.parse(dagText.value) as { nodes: Record<string, unknown>[] };
  dag.nodes[index]![field] = value;
  dagText.value = JSON.stringify(dag, null, 2);
}

function removeVisualNode(index: number) {
  const dag = JSON.parse(dagText.value) as {
    edges: { from: string; to: string }[];
    nodes: Record<string, unknown>[];
  };
  const id = String(dag.nodes[index]?.id ?? '');
  dag.nodes.splice(index, 1);
  dag.edges = (dag.edges ?? []).filter(
    (edge) => edge.from !== id && edge.to !== id,
  );
  dagText.value = JSON.stringify(dag, null, 2);
}

async function saveDraft() {
  if (!selected.value) return;
  try {
    const dag = JSON.parse(dagText.value) as Record<string, unknown>;
    const id = await savePipeline({ algorithmId: selected.value.id, dag });
    const errors = await validatePipeline(id);
    message[errors.length > 0 ? 'warning' : 'success'](
      errors.length > 0
        ? `草稿已保存：${errors.join('；')}`
        : 'Pipeline 校验通过',
    );
    versions.value = await getPipelineVersions(selected.value.id);
  } catch {
    message.error('DAG 必须是合法 JSON，且只能使用受控节点类型');
  }
}

async function publish(record: Record<string, unknown>) {
  const version = record as unknown as AiVideoAlgorithmApi.PipelineVersion;
  await publishPipeline(version.id);
  message.success(`Pipeline v${version.version} 已发布`);
  if (selected.value) {
    versions.value = await getPipelineVersions(selected.value.id);
    await loadAlgorithms();
  }
}

watch(packageView, (main) => {
  if (!main) void loadAlgorithms();
});
</script>

<template>
  <Page auto-content-height>
    <AlgorithmModal @success="loadAlgorithms" />
    <div v-if="packageView" class="ai-page ai-page-stack overflow-auto">
      <AiPageHeader
        title="算法中心"
        description="选择算法，配置摄像头和网关。"
        icon="lucide:brain-circuit"
      >
        <template #extra>
          <Space>
            <Button @click="packageView = false">高级管理</Button
            ><Button @click="versionsModal.open()"> 上传 / 下载算法包 </Button>
          </Space>
        </template>
      </AiPageHeader>
      <AlgorithmCatalog
        ref="algorithmCatalog"
        @inspect="
          (item) => {
            packageView = false;
            openPipeline({ ...item });
          }
        "
      />
      <VersionsModal
        content-class="ai-dialog-content"
        footer-class="ai-dialog-footer"
        class="ai-dialog w-[1000px]"
      >
        <PackageCatalog
          @change="
            algorithmCatalog?.refresh();
            loadAlgorithms();
          "
        />
      </VersionsModal>
    </div>
    <div v-else class="ai-page ai-page-stack h-full">
      <Button class="self-start" @click="packageView = true">
        返回可部署算法
      </Button>
      <AiPageHeader
        title="算法中心"
        description="管理算法与任务编排。"
        icon="lucide:brain-circuit"
      >
        <template #extra>
          <Space>
            <Button @click="loadAlgorithms">
              <IconifyIcon icon="lucide:refresh-cw" />刷新目录 </Button
            ><Button
              v-if="canCreate"
              type="primary"
              @click="algorithmModalApi.open()"
            >
              <IconifyIcon icon="lucide:plus" />新增 AI 能力
            </Button>
          </Space>
        </template>
      </AiPageHeader>
      <Alert v-if="error" :message="error" show-icon type="error">
        <template #action>
          <Button @click="loadAlgorithms">重试</Button>
        </template>
      </Alert>
      <div class="algorithm-filter ai-surface">
        <Input
          v-model:value="query.name"
          allow-clear
          placeholder="搜索算法名称、编码或能力"
          @press-enter="loadAlgorithms"
        >
          <template #prefix><IconifyIcon icon="lucide:search" /></template>
        </Input>
        <Segmented
          :value="query.category"
          :options="[
            { label: '全部', value: '' },
            { label: '核心', value: 'CORE' },
            { label: '扩展', value: 'EXTENSION' },
            { label: '自定义', value: 'CUSTOM' },
          ]"
          @change="changeCategory"
        />
        <Segmented
          :value="query.status ?? 'all'"
          :options="[
            { label: '全部状态', value: 'all' },
            { label: '已启用', value: 0 },
            { label: '未启用', value: 1 },
          ]"
          @change="changeStatus"
        />
        <Select
          v-model:value="query.pageSize"
          class="algorithm-page-size"
          :options="[
            { label: '20 / 页', value: 20 },
            { label: '40 / 页', value: 40 },
          ]"
          @change="loadAlgorithms"
        />
      </div>

      <div class="algorithm-results-meta">
        <span>共 {{ total }} 个算法能力</span
        ><span>Pipeline 仅允许受控节点，版本发布后不可变</span>
      </div>
      <Spin :spinning="loading" class="min-h-0 flex-1 overflow-auto">
        <div v-if="algorithms.length" class="algorithm-grid">
          <article
            v-for="item in algorithms"
            :key="item.id"
            class="algorithm-card ai-surface"
          >
            <div class="algorithm-card__top">
              <span class="algorithm-card__icon"
                ><IconifyIcon :icon="algorithmIcon(item)"
              /></span>
              <AiStatusIndicator
                :label="item.status === 0 ? '已启用' : '未启用'"
                :status="item.status === 0 ? 'ENABLED' : 'DISABLED'"
                size="sm"
              />
            </div>
            <div class="algorithm-card__title">
              <h3>{{ item.name }}</h3>
              <Tag
                :color="
                  item.category === 'CORE'
                    ? 'blue'
                    : item.category === 'EXTENSION'
                      ? 'purple'
                      : 'default'
                "
              >
                {{ categoryLabel(item.category) }}
              </Tag>
            </div>
            <p class="ai-truncate-2">
              {{ item.description || '暂无算法说明' }}
            </p>
            <div class="algorithm-card__tags">
              <Tag>{{ item.sceneGroup || '其他' }}</Tag
              ><Tag>{{ item.implementationType }}</Tag>
            </div>
            <dl>
              <div>
                <dt>默认模型</dt>
                <dd :title="modelName(item.defaultModelId)">
                  {{ modelName(item.defaultModelId) }}
                </dd>
              </div>
              <div>
                <dt>Pipeline</dt>
                <dd>
                  <AiStatusIndicator
                    :label="
                      item.currentPipelineVersionId
                        ? `#${item.currentPipelineVersionId}`
                        : '待适配'
                    "
                    :status="
                      item.currentPipelineVersionId
                        ? item.pipelineAcceptanceStatus
                        : 'WARNING'
                    "
                    size="sm"
                  />
                </dd>
              </div>
              <div>
                <dt>能力键</dt>
                <dd class="ai-mono">{{ item.capabilityKey }}</dd>
              </div>
            </dl>
            <Button block @click="openPipeline(item)">
              <IconifyIcon icon="lucide:workflow" />查看 Pipeline
            </Button>
          </article>
        </div>
        <Empty v-else-if="!loading" description="没有符合当前筛选条件的算法" />
      </Spin>
      <Pagination
        v-if="total > query.pageSize"
        v-model:current="query.pageNo"
        class="algorithm-pagination"
        :page-size="query.pageSize"
        :total="total"
        show-less-items
        @change="loadAlgorithms"
      />
    </div>

    <Drawer
      v-model:open="pipelineOpen"
      class="pipeline-drawer"
      placement="right"
      width="min(1480px, calc(100vw - 24px))"
    >
      <template #title>{{ selected?.name }} · Pipeline 工作区</template>
      <div class="pipeline-workspace">
        <header class="pipeline-context">
          <div class="pipeline-context__identity">
            <span class="pipeline-context__icon">
              <IconifyIcon icon="lucide:workflow" />
            </span>
            <div>
              <strong>{{ selected?.name }}</strong>
              <span class="ai-mono">{{ selected?.capabilityKey }}</span>
            </div>
          </div>
          <div class="pipeline-context__facts">
            <div>
              <span>节点约束</span>
              <strong>{{ nodeCatalog.length }} 类受控节点</strong>
            </div>
            <div>
              <span>不可变版本</span>
              <strong>{{ versions.length }}</strong>
            </div>
            <div>
              <span>默认模型</span>
              <strong>{{ modelName(selected?.defaultModelId) }}</strong>
            </div>
          </div>
          <Button v-if="canUpdate" type="primary" @click="saveDraft">
            <IconifyIcon icon="lucide:badge-check" />
            校验并保存
          </Button>
        </header>

        <div class="pipeline-main">
          <aside class="pipeline-panel pipeline-node-library">
            <div class="pipeline-panel__heading">
              <div>
                <strong>受控节点库</strong>
                <span>节点类型受控，能力键动态配置</span>
              </div>
              <Tag>{{ nodeCatalog.length }}</Tag>
            </div>
            <div class="pipeline-node-list">
              <button
                v-for="item in nodeCatalog"
                :key="item.type"
                class="pipeline-node"
                type="button"
                :disabled="!canUpdate"
                @click="addNode(item)"
              >
                <IconifyIcon :icon="item.icon" />
                <div>
                  <strong>{{ item.label }}</strong
                  ><span>{{ item.capabilityKey }}</span>
                </div>
                <IconifyIcon icon="lucide:plus" class="ml-auto" />
              </button>
            </div>
          </aside>

          <section class="pipeline-panel pipeline-editor">
            <div class="pipeline-panel__heading">
              <div>
                <strong>Pipeline 编排</strong>
                <span>受控节点、能力键及执行顺序</span>
              </div>
              <Space :size="6">
                <Segmented
                  v-model:value="editorMode"
                  :options="['VISUAL', 'JSON']"
                  size="small"
                /><Tag>schema v1.0</Tag>
              </Space>
            </div>
            <Textarea
              v-if="editorMode === 'JSON'"
              v-model:value="dagText"
              class="pipeline-editor__input"
              :disabled="!canUpdate"
              spellcheck="false"
            />
            <div v-else class="pipeline-visual">
              <Empty
                v-if="!visualNodes.length"
                description="从左侧添加第一个受控节点"
              />
              <template
                v-for="(node, index) in visualNodes"
                :key="String(node.id)"
              >
                <article class="pipeline-visual-node">
                  <header>
                    <Tag color="blue">{{ node.type }}</Tag
                    ><Button
                      danger
                      size="small"
                      type="text"
                      @click="removeVisualNode(index)"
                    >
                      <IconifyIcon icon="lucide:x" />
                    </Button>
                  </header>
                  <label
                    >节点 ID<Input
                      :value="String(node.id ?? '')"
                      @change="
                        updateVisualNode(index, 'id', $event.target.value)
                      "
                  /></label>
                  <label
                    >能力键<Input
                      :value="String(node.capabilityKey ?? '')"
                      @change="
                        updateVisualNode(
                          index,
                          'capabilityKey',
                          $event.target.value,
                        )
                      "
                  /></label>
                  <label
                    v-if="
                      [
                        'DETECTOR',
                        'CLASSIFIER',
                        'OCR',
                        'POSE',
                        'SEGMENTER',
                        'RECOGNIZER',
                      ].includes(String(node.type))
                    "
                  >
                    模型（可选）
                    <Select
                      :value="
                        typeof node.modelId === 'number'
                          ? node.modelId
                          : undefined
                      "
                      :options="modelOptions(node)"
                      :loading="modelsLoading"
                      :disabled="!canUpdate || !!modelsError"
                      allow-clear
                      show-search
                      option-filter-prop="label"
                      :placeholder="`默认：${modelName(selected?.defaultModelId)}`"
                      @change="updateVisualNode(index, 'modelId', $event)"
                    />
                    <span class="text-xs text-slate-400"
                      >按名称搜索；具体文件版本在任务中选择。</span
                    >
                  </label>
                </article>
                <IconifyIcon
                  v-if="index < visualNodes.length - 1"
                  icon="lucide:arrow-right"
                  class="pipeline-visual-arrow"
                />
              </template>
            </div>
            <footer class="pipeline-editor__footer">
              <span
                ><IconifyIcon
                  icon="lucide:shield-check"
                />服务端执行拓扑、能力键格式与输入输出校验</span
              >
              <span>{{ dagText.length }} 字符</span>
            </footer>
          </section>

          <aside class="pipeline-side">
            <Alert
              v-if="modelsError"
              :message="modelsError"
              type="error"
              show-icon
            >
              <template #action>
                <Button size="small" @click="loadModels"> 重试 </Button>
              </template>
            </Alert>
            <section class="pipeline-panel">
              <div class="pipeline-panel__heading">
                <div><strong>属性摘要</strong><span>当前算法上下文</span></div>
              </div>
              <Descriptions :column="1" size="small">
                <DescriptionsItem label="能力键">
                  <span class="ai-mono">{{ selected?.capabilityKey }}</span>
                </DescriptionsItem>
                <DescriptionsItem label="默认模型">
                  {{ modelName(selected?.defaultModelId) }}
                </DescriptionsItem>
                <DescriptionsItem label="事件类型">
                  {{ selected?.eventType || '基础能力，无事件' }}
                </DescriptionsItem>
              </Descriptions>
            </section>
            <section class="pipeline-panel pipeline-versions">
              <div class="pipeline-panel__heading">
                <div>
                  <strong>不可变版本</strong><span>校验通过后方可发布</span>
                </div>
                <Tag>{{ versions.length }}</Tag>
              </div>
              <Table
                v-if="versions.length"
                :columns="versionColumns"
                :data-source="versions"
                :pagination="false"
                row-key="id"
                size="small"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.key === 'validationStatus'">
                    <Tag
                      :color="
                        record.validationStatus === 'PUBLISHED'
                          ? 'green'
                          : record.validationStatus === 'VALID'
                            ? 'blue'
                            : 'orange'
                      "
                    >
                      {{ record.validationStatus }}
                    </Tag>
                  </template>
                  <template v-else-if="column.key === 'actions'">
                    <Button
                      v-if="
                        canPublish && record.validationStatus !== 'PUBLISHED'
                      "
                      size="small"
                      type="link"
                      @click="publish(record)"
                    >
                      发布
                    </Button>
                  </template>
                  <template v-else-if="column.key === 'createTime'">
                    <span class="pipeline-version-time">{{
                      formatDateTime(record.createTime)
                    }}</span>
                  </template>
                </template>
              </Table>
              <Empty v-else description="尚无 Pipeline 版本" />
            </section>
          </aside>
        </div>
      </div>
    </Drawer>
  </Page>
</template>

<style scoped>
.algorithm-filter {
  display: flex;
  gap: 10px;
  align-items: center;
  padding: 12px;
}

.algorithm-filter :deep(.ant-input-affix-wrapper) {
  width: min(360px, 32vw);
}

.algorithm-page-size {
  width: 110px;
  margin-left: auto;
}

.algorithm-results-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.algorithm-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(240px, 1fr));
  gap: 14px;
  padding: 1px;
}

.algorithm-card {
  display: flex;
  flex-direction: column;
  min-height: 310px;
  padding: 16px;
  transition:
    transform 150ms ease,
    box-shadow 150ms ease;
}

.algorithm-card:hover {
  box-shadow: var(--ai-shadow-md);
  transform: translateY(-1px);
}

.algorithm-card__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.algorithm-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 40px;
  height: 40px;
  font-size: 20px;
  color: #2563eb;
  background: rgb(37 99 235 / 9%);
  border: 1px solid rgb(37 99 235 / 14%);
  border-radius: 10px;
}

.algorithm-card__title {
  display: flex;
  gap: 8px;
  align-items: center;
  justify-content: space-between;
  margin-top: 14px;
}

.algorithm-card__title h3 {
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 15px;
  font-weight: 650;
  letter-spacing: -0.02em;
  white-space: nowrap;
}

.algorithm-card > p {
  min-height: 40px;
  margin: 7px 0 12px;
  font-size: 12px;
  line-height: 1.65;
  color: hsl(var(--muted-foreground));
}

.algorithm-card__tags {
  display: flex;
  gap: 6px;
  min-height: 24px;
  overflow: hidden;
}

.algorithm-card dl {
  display: grid;
  gap: 8px;
  padding: 12px 0;
  margin: 15px 0;
  border-top: 1px solid hsl(var(--border) / 58%);
  border-bottom: 1px solid hsl(var(--border) / 58%);
}

.algorithm-card dl div {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
  min-width: 0;
  font-size: 11px;
}

.algorithm-card dt {
  color: hsl(var(--muted-foreground));
}

.algorithm-card dd {
  min-width: 0;
  margin: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.algorithm-card > :deep(.ant-btn) {
  margin-top: auto;
}

.algorithm-pagination {
  display: flex;
  justify-content: flex-end;
}

.pipeline-workspace {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  height: 100%;
  min-height: 0;
}

.pipeline-context {
  display: flex;
  gap: 20px;
  align-items: center;
  min-width: 0;
  padding: 12px 14px;
  background: hsl(var(--muted) / 28%);
  border: 1px solid hsl(var(--border) / 72%);
  border-radius: 10px;
}

.pipeline-context__identity {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 220px;
}

.pipeline-context__identity > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.pipeline-context__identity strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 13px;
  white-space: nowrap;
}

.pipeline-context__identity span:not(.pipeline-context__icon) {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.pipeline-context__icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  color: #60a5fa;
  background: rgb(37 99 235 / 14%);
  border: 1px solid rgb(59 130 246 / 24%);
  border-radius: 8px;
}

.pipeline-context__facts {
  display: flex;
  flex: 1;
  gap: 28px;
  min-width: 0;
}

.pipeline-context__facts > div {
  display: grid;
  gap: 2px;
  min-width: 92px;
}

.pipeline-context__facts span {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.pipeline-context__facts strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.pipeline-main {
  display: grid;
  grid-template-columns: 210px minmax(460px, 1fr) 360px;
  gap: 12px;
  min-height: 0;
}

.pipeline-panel {
  min-width: 0;
  padding: 12px;
  overflow: hidden;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 75%);
  border-radius: 10px;
}

.pipeline-panel__heading {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  justify-content: space-between;
  min-height: 36px;
  margin-bottom: 10px;
}

.pipeline-panel__heading > div {
  display: grid;
  gap: 2px;
}

.pipeline-panel__heading strong {
  font-size: 12px;
  font-weight: 650;
}

.pipeline-panel__heading span {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.pipeline-node-library {
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.pipeline-node-list {
  display: grid;
  gap: 7px;
}

.pipeline-node {
  display: flex;
  gap: 9px;
  align-items: center;
  width: 100%;
  padding: 9px;
  color: #94a3b8;
  text-align: left;
  cursor: pointer;
  background: hsl(var(--muted) / 35%);
  border: 1px solid hsl(var(--border) / 64%);
  border-radius: 8px;
}

.pipeline-node:hover {
  background: rgb(37 99 235 / 8%);
  border-color: #60a5fa;
}

.pipeline-node:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.pipeline-node > svg {
  flex: 0 0 auto;
  width: 16px;
  height: 16px;
}

.pipeline-node > div {
  display: grid;
  gap: 1px;
}

.pipeline-node strong {
  font-size: 11px;
  color: hsl(var(--foreground));
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.pipeline-node span {
  font-size: 9px;
  color: hsl(var(--muted-foreground));
}

.pipeline-node--blue > svg {
  color: #3b82f6;
}

.pipeline-node--cyan > svg {
  color: #06b6d4;
}

.pipeline-node--purple > svg {
  color: #a855f7;
}

.pipeline-node--indigo > svg {
  color: #6366f1;
}

.pipeline-node--orange > svg {
  color: #f59e0b;
}

.pipeline-editor {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  min-height: 0;
  padding-bottom: 8px;
  background: #11151b;
  border-color: #2d3745;
}

.pipeline-editor :deep(.pipeline-panel__heading strong) {
  color: #f1f5f9;
}

.pipeline-editor__input {
  height: 100% !important;
  min-height: 360px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  line-height: 1.65;
  color: #dbeafe !important;
  resize: none;
  background: #0b0f14 !important;
  border-color: #334155 !important;
}

.pipeline-visual {
  display: flex;
  gap: 12px;
  align-items: center;
  min-height: 360px;
  padding: 20px;
  overflow: auto;
  background: #0b0f14;
  border: 1px solid #334155;
  border-radius: 6px;
}

.pipeline-visual-node {
  flex: 0 0 auto;
  width: 230px;
  padding: 14px;
  color: #cbd5e1;
  background: #151c27;
  border: 1px solid #334155;
  border-radius: 10px;
  box-shadow: 0 10px 22px rgb(0 0 0 / 18%);
}

.pipeline-visual-node header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.pipeline-visual-node label {
  display: grid;
  gap: 4px;
  min-width: 0;
  margin-top: 9px;
  font-size: 10px;
  color: #94a3b8;
}

.pipeline-visual-node :deep(.ant-select) {
  width: 100%;
  min-width: 0;
}

.pipeline-visual-node :deep(.ant-select-selector) {
  min-width: 0;
}

.pipeline-visual-node :deep(.ant-input) {
  color: #dbeafe;
  background: #0f172a;
  border-color: #334155;
}

.pipeline-visual-arrow {
  flex: 0 0 auto;
  font-size: 24px;
  color: #60a5fa;
}

.pipeline-editor__footer {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  padding-top: 8px;
  font-size: 9px;
  color: #64748b;
}

.pipeline-editor__footer span {
  display: inline-flex;
  gap: 5px;
  align-items: center;
}

.pipeline-side {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.pipeline-versions {
  min-height: 0;
  overflow: auto;
}

.pipeline-versions :deep(.ant-table) {
  font-size: 11px;
}

.pipeline-version-time {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

@media (width <= 1200px) {
  .pipeline-main {
    grid-template-columns: 190px minmax(420px, 1fr) 320px;
  }

  .pipeline-context__facts {
    gap: 14px;
  }
}

@media (width <= 900px) {
  .pipeline-workspace {
    height: auto;
    overflow: auto;
  }

  .pipeline-main {
    grid-template-columns: 1fr;
  }

  .pipeline-side {
    overflow: visible;
  }

  .pipeline-context__facts {
    display: none;
  }
}

@media (width <= 1500px) {
  .algorithm-grid {
    grid-template-columns: repeat(3, minmax(240px, 1fr));
  }
}

@media (width <= 1180px) {
  .algorithm-grid {
    grid-template-columns: repeat(2, minmax(240px, 1fr));
  }
}

@media (width <= 820px) {
  .algorithm-grid {
    grid-template-columns: 1fr;
  }

  .algorithm-filter {
    flex-direction: column;
    align-items: stretch;
  }

  .algorithm-filter :deep(.ant-input-affix-wrapper) {
    width: 100%;
  }

  .algorithm-page-size {
    margin-left: 0;
  }
}
</style>
