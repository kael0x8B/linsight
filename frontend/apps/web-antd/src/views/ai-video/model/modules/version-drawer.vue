<script lang="ts" setup>
import type { AiVideoModelApi } from '#/api/ai-video/model';

import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenDrawer } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Button,
  Descriptions,
  DescriptionsItem,
  Empty,
  message,
  Select,
  Space,
  Spin,
  Tabs,
  Tag,
  Timeline,
} from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getModelDeployments,
  getModelTests,
  getModelVersionList,
  publishModelVersion,
} from '#/api/ai-video/model';

import {
  useDeploymentGridColumns,
  useTestGridColumns,
  useVersionGridColumns,
} from '../data';
import {
  deploymentStatusText,
  isDeploymentPending,
} from '../deployment-status';
import VersionUploadDrawer from './version-upload-drawer.vue';

const emit = defineEmits(['success']);

const { hasAccessByCodes } = useAccess();
const canPublish = computed(() => hasAccessByCodes(['ai-video:model:publish']));
const canUpload = computed(() => hasAccessByCodes(['ai-video:model:upload']));

const model = ref<AiVideoModelApi.Model>();
const versions = ref<AiVideoModelApi.ModelVersion[]>([]);
const deployments = ref<AiVideoModelApi.ModelDeployment[]>([]);
const tests = ref<AiVideoModelApi.ModelTest[]>([]);
const selectedVersionId = ref<number>();
const activeTab = ref('versions');
const relationsLoading = ref(false);

const selectedVersion = computed(() =>
  versions.value.find((item) => item.id === selectedVersionId.value),
);
const versionOptions = computed(() =>
  versions.value.map((item) => ({
    label: `${item.version} · ${publishStatusText(item.publishStatus)}`,
    value: item.id,
  })),
);

const [UploadDrawer, uploadDrawerApi] = useVbenDrawer({
  connectedComponent: VersionUploadDrawer,
  destroyOnClose: true,
});

const [VersionGrid, versionGridApi] =
  useVbenVxeGrid<AiVideoModelApi.ModelVersion>({
    gridOptions: {
      cellConfig: { height: 48 },
      columns: useVersionGridColumns(),
      height: 'auto',
      minHeight: 180,
      pagerConfig: { enabled: false },
      rowConfig: { isHover: true, keyField: 'id' },
    },
  });

const [DeploymentGrid, deploymentGridApi] =
  useVbenVxeGrid<AiVideoModelApi.ModelDeployment>({
    gridOptions: {
      columns: useDeploymentGridColumns(),
      height: 320,
      pagerConfig: { enabled: false },
      rowConfig: { keyField: 'id', isHover: true },
    },
  });

const [TestGrid, testGridApi] = useVbenVxeGrid<AiVideoModelApi.ModelTest>({
  gridOptions: {
    columns: useTestGridColumns(),
    height: 320,
    pagerConfig: { enabled: false },
    rowConfig: { keyField: 'id', isHover: true },
  },
});

function publishStatusText(status?: string) {
  return (
    {
      DRAFT: '草稿',
      PUBLISHED: '已发布',
      SUPERSEDED: '已替代',
    }[status ?? ''] ?? '未发布'
  );
}

function publishStatusColor(status?: string) {
  return { DRAFT: 'default', PUBLISHED: 'green', SUPERSEDED: 'orange' }[
    status ?? ''
  ];
}

function executionStatusColor(status?: string) {
  if (isDeploymentPending(status)) return 'processing';
  return (
    {
      DOWNLOADING: 'processing',
      FAILED: 'red',
      LOADING: 'processing',
      QUEUED: 'blue',
      READY: 'green',
      VERIFYING: 'processing',
    }[status ?? ''] ?? 'default'
  );
}

function testStatusColor(status?: string) {
  return (
    {
      FAILED: 'red',
      QUEUED: 'blue',
      RUNNING: 'processing',
      SUCCEEDED: 'green',
    }[status ?? ''] ?? 'default'
  );
}

async function loadVersions() {
  if (!model.value?.id) return;
  versionGridApi.setLoading(true);
  try {
    versions.value = await getModelVersionList(model.value.id);
    versionGridApi.setState({ tableData: versions.value });
    const preferred = versions.value.find(
      (item) => item.id === model.value?.currentVersionId,
    );
    selectedVersionId.value = preferred?.id ?? versions.value[0]?.id;
    await loadVersionRelations();
  } finally {
    versionGridApi.setLoading(false);
  }
}

async function loadVersionRelations() {
  if (!selectedVersionId.value) {
    deployments.value = [];
    tests.value = [];
    deploymentGridApi.setState({ tableData: [] });
    testGridApi.setState({ tableData: [] });
    return;
  }
  relationsLoading.value = true;
  deployments.value = [];
  tests.value = [];
  deploymentGridApi.setState({ tableData: [] });
  testGridApi.setState({ tableData: [] });
  deploymentGridApi.setLoading(true);
  testGridApi.setLoading(true);
  try {
    const [deploymentResult, testResult] = await Promise.all([
      getModelDeployments(selectedVersionId.value),
      getModelTests(selectedVersionId.value),
    ]);
    deployments.value = deploymentResult;
    tests.value = testResult;
    deploymentGridApi.setState({ tableData: deploymentResult });
    testGridApi.setState({ tableData: testResult });
  } finally {
    relationsLoading.value = false;
    deploymentGridApi.setLoading(false);
    testGridApi.setLoading(false);
  }
}

function openUpload() {
  if (model.value) uploadDrawerApi.setData(model.value).open();
}

async function handleUploaded() {
  await loadVersions();
  emit('success');
}

async function publish(version: AiVideoModelApi.ModelVersion) {
  await publishModelVersion(version.id);
  message.success(`版本 ${version.version} 已设为目录默认版本`);
  await loadVersions();
  emit('success');
}

async function selectVersion(
  version: AiVideoModelApi.ModelVersion,
  tab = 'metadata',
) {
  selectedVersionId.value = version.id;
  activeTab.value = tab;
  await loadVersionRelations();
}

async function copySha256() {
  if (!selectedVersion.value?.sha256) return;
  await navigator.clipboard.writeText(selectedVersion.value.sha256);
  message.success('SHA256 已复制');
}

const [Drawer, drawerApi] = useVbenDrawer({
  footer: false,
  async onOpenChange(isOpen) {
    if (!isOpen) {
      model.value = undefined;
      versions.value = [];
      deployments.value = [];
      tests.value = [];
      selectedVersionId.value = undefined;
      activeTab.value = 'versions';
      return;
    }
    model.value = drawerApi.getData<AiVideoModelApi.Model>();
    await loadVersions();
    const initial = drawerApi.getData<
      AiVideoModelApi.Model & { initialVersionId?: number }
    >().initialVersionId;
    const version = versions.value.find((item) => item.id === initial);
    if (version) await selectVersion(version, 'metadata');
  },
});
</script>

<template>
  <Drawer
    class="w-[1280px] max-w-[calc(100vw-24px)]"
    :title="`${model?.name ?? ''} · 版本与部署`"
  >
    <UploadDrawer @success="handleUploaded" />
    <div class="model-version-content">
      <div class="model-version-summary">
        <div class="model-summary-item model-summary-item--wide">
          <span class="model-summary-item__icon"
            ><IconifyIcon icon="lucide:fingerprint"
          /></span>
          <div>
            <span>稳定编码</span
            ><strong class="model-summary-code" :title="model?.code">{{
              model?.code
            }}</strong>
          </div>
        </div>
        <div class="model-summary-item">
          <span class="model-summary-item__icon"
            ><IconifyIcon icon="lucide:package-open"
          /></span>
          <div>
            <span>模型来源</span
            ><strong>{{
              model?.sourceType === 'PRESET' ? '预置资产' : '自定义'
            }}</strong>
          </div>
        </div>
        <div class="model-summary-item">
          <span class="model-summary-item__icon"
            ><IconifyIcon icon="lucide:git-commit-horizontal"
          /></span>
          <div>
            <span>目录默认版本</span
            ><strong>{{
              model?.currentVersionId ? `#${model.currentVersionId}` : '未发布'
            }}</strong>
          </div>
        </div>
        <div class="model-summary-item">
          <span class="model-summary-item__icon"
            ><IconifyIcon icon="lucide:server-cog"
          /></span>
          <div>
            <span>节点就绪</span
            ><strong
              >{{ model?.readyNodeCount ?? 0 }} /
              {{ model?.deployedNodeCount ?? 0 }}</strong
            >
          </div>
        </div>
      </div>

      <Tabs v-model:active-key="activeTab" class="model-version-tabs">
        <Tabs.TabPane key="versions" tab="版本">
          <VersionGrid table-title="不可变版本">
            <template #toolbar-tools>
              <Button v-if="canUpload" type="primary" @click="openUpload">
                上传新版本
              </Button>
            </template>
            <template #version="{ row }">
              <Space :size="4">
                <span class="font-medium">{{ row.version }}</span>
                <Tag v-if="row.id === model?.currentVersionId" color="blue">
                  目录默认
                </Tag>
              </Space>
            </template>
            <template #validationStatus="{ row }">
              <Tag
                :color="row.validationStatus === 'VERIFIED' ? 'green' : 'red'"
              >
                {{ row.validationStatus === 'VERIFIED' ? '已验证' : '未通过' }}
              </Tag>
            </template>
            <template #publishStatus="{ row }">
              <Tag :color="publishStatusColor(row.publishStatus)">
                {{ publishStatusText(row.publishStatus) }}
              </Tag>
            </template>
            <template #sha256="{ row }">
              <span class="model-version-sha" :title="row.sha256">{{
                row.sha256
              }}</span>
            </template>
            <template #actions="{ row }">
              <TableAction
                :actions="[
                  {
                    label: '详情',
                    type: 'link',
                    onClick: () => selectVersion(row),
                  },
                  {
                    label: '设为默认',
                    type: 'link',
                    auth: ['ai-video:model:publish'],
                    disabled:
                      !canPublish ||
                      row.publishStatus === 'PUBLISHED' ||
                      row.validationStatus !== 'VERIFIED',
                    onClick: () => publish(row),
                  },
                ]"
              />
            </template>
          </VersionGrid>
        </Tabs.TabPane>

        <Tabs.TabPane key="deployments" tab="节点部署">
          <div class="mb-3 flex items-center justify-between">
            <span class="text-muted-foreground text-sm"
              >按版本查看节点部署结果</span
            >
            <Select
              v-model:value="selectedVersionId"
              class="w-64"
              :options="versionOptions"
              placeholder="请选择版本"
              @change="loadVersionRelations"
            />
          </div>
          <Spin :spinning="relationsLoading">
            <div v-show="deployments.length">
              <DeploymentGrid>
                <template #actualStatus="{ row }">
                  <Tag :color="executionStatusColor(row.actualStatus)">
                    {{ deploymentStatusText(row.actualStatus) }}
                  </Tag>
                </template>
              </DeploymentGrid>
            </div>
            <div v-if="!deployments.length" class="model-relation-empty">
              <Empty description="当前版本尚未部署到边缘节点" />
              <p>部署记录将在节点接收并执行模型命令后显示。</p>
            </div>
          </Spin>
        </Tabs.TabPane>

        <Tabs.TabPane key="metadata" tab="标签与输入">
          <template v-if="selectedVersion">
            <div class="mb-3 flex justify-end">
              <Select
                v-model:value="selectedVersionId"
                class="w-64"
                :options="versionOptions"
                @change="loadVersionRelations"
              />
            </div>
            <Descriptions bordered :column="2" size="small">
              <DescriptionsItem label="版本">
                {{ selectedVersion.version }}
              </DescriptionsItem>
              <DescriptionsItem label="格式">
                {{ selectedVersion.artifactFormat }}
              </DescriptionsItem>
              <DescriptionsItem label="制品名称">
                {{ selectedVersion.artifactName }}
              </DescriptionsItem>
              <DescriptionsItem label="许可证">
                {{ selectedVersion.licenseSpdx }}
              </DescriptionsItem>
              <DescriptionsItem label="来源仓库">
                {{ selectedVersion.sourceRepository || '—' }}
              </DescriptionsItem>
              <DescriptionsItem label="固定 revision">
                {{ selectedVersion.sourceRevision || '—' }}
              </DescriptionsItem>
              <DescriptionsItem label="SHA256" :span="2">
                <Space>
                  <span class="font-mono text-xs">{{
                    selectedVersion.sha256
                  }}</span>
                  <Button size="small" @click="copySha256">复制</Button>
                </Space>
              </DescriptionsItem>
              <DescriptionsItem label="标签 Schema" :span="2">
                {{
                  selectedVersion.runtimeManifest || '尚未登记 Runtime Manifest'
                }}
              </DescriptionsItem>
              <DescriptionsItem label="输入规格" :span="2">
                以 Runtime Manifest 的 preprocess
                为准；单图测试参数仅作为动态输入回退值。
              </DescriptionsItem>
            </Descriptions>
          </template>
          <Empty v-else description="请先上传并选择模型版本" />
        </Tabs.TabPane>

        <Tabs.TabPane key="tests" tab="测试记录">
          <div class="mb-3 flex justify-end">
            <Select
              v-model:value="selectedVersionId"
              class="w-64"
              :options="versionOptions"
              placeholder="请选择版本"
              @change="loadVersionRelations"
            />
          </div>
          <Spin :spinning="relationsLoading">
            <div v-show="tests.length">
              <TestGrid>
                <template #testStatus="{ row }">
                  <Tag :color="testStatusColor(row.status)">
                    {{ row.status }}
                  </Tag>
                </template>
              </TestGrid>
            </div>
            <div v-if="!tests.length" class="model-relation-empty">
              <Empty description="当前版本尚无单图测试记录" />
              <p>完成单图测试后可在此查看推理后端、耗时与诊断信息。</p>
            </div>
          </Spin>
        </Tabs.TabPane>

        <Tabs.TabPane key="audit" tab="变更记录">
          <template v-if="selectedVersion">
            <div class="mb-4 flex justify-end">
              <Select
                v-model:value="selectedVersionId"
                class="w-64"
                :options="versionOptions"
                @change="loadVersionRelations"
              />
            </div>
            <Timeline>
              <Timeline.Item color="blue">
                版本创建：{{ selectedVersion.createTime || '时间未知' }}
              </Timeline.Item>
              <Timeline.Item
                v-if="selectedVersion.validationStatus === 'VERIFIED'"
                color="green"
              >
                SHA256 与制品格式校验通过
              </Timeline.Item>
              <Timeline.Item v-if="selectedVersion.publishedTime" color="green">
                目录发布：{{ selectedVersion.publishedTime }}
              </Timeline.Item>
              <Timeline.Item
                v-if="selectedVersion.executionReadyTime"
                color="green"
              >
                首次执行就绪：{{ selectedVersion.executionReadyTime }}
              </Timeline.Item>
            </Timeline>
          </template>
          <Empty v-else description="请先上传并选择模型版本" />
        </Tabs.TabPane>
      </Tabs>
    </div>
  </Drawer>
</template>

<style scoped>
.model-version-content {
  display: grid;
  gap: 14px;
  padding: 2px 4px 16px;
}

.model-version-summary {
  display: grid;
  grid-template-columns: minmax(260px, 1.45fr) repeat(3, minmax(150px, 1fr));
  gap: 10px;
}

.model-summary-item {
  display: flex;
  gap: 10px;
  align-items: center;
  min-width: 0;
  padding: 11px 12px;
  background: hsl(var(--muted) / 28%);
  border: 1px solid hsl(var(--border) / 68%);
  border-radius: 9px;
}

.model-summary-item__icon {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 30px;
  height: 30px;
  color: #3b82f6;
  background: rgb(37 99 235 / 11%);
  border-radius: 7px;
}

.model-summary-item > div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.model-summary-item span:not(.model-summary-item__icon) {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.model-summary-item strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.model-summary-code,
.model-version-sha {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.model-relation-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 260px;
  background: hsl(var(--muted) / 16%);
  border: 1px dashed hsl(var(--border) / 72%);
  border-radius: 8px;
}

.model-relation-empty :deep(.ant-empty) {
  margin-block: 0 4px;
}

.model-relation-empty p {
  margin: 0;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.model-version-tabs {
  min-height: 280px;
  padding: 0 10px 10px;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 72%);
  border-radius: 10px;
}

.model-version-sha {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

@media (width <= 900px) {
  .model-version-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .model-summary-item--wide {
    grid-column: 1 / -1;
  }
}
</style>
