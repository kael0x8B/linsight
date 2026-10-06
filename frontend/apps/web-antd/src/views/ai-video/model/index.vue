<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { AiVideoModelApi } from '#/api/ai-video/model';

import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Popover, Tag, Tooltip } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getModel, getModelPage } from '#/api/ai-video/model';
import { AiPageHeader, AiStatusIndicator } from '#/components/ai-video';

import { useModelGridColumns, useModelGridFormSchema } from './data';
import DeployableCatalog from './modules/deployable-catalog.vue';
import ModelForm from './modules/model-form.vue';
import VersionDrawer from './modules/version-drawer.vue';
const deployableView = ref(false);
async function openDeployable(modelId: number, versionId: number) {
  const model = await getModel(modelId);
  modelVersionDrawerApi
    .setData({ ...model, initialVersionId: versionId })
    .open();
}

const { hasAccessByCodes } = useAccess();
const canCreate = computed(() => hasAccessByCodes(['ai-video:model:create']));
const loadError = ref('');

const [FormModal, formModalApi] = useVbenModal({
  connectedComponent: ModelForm,
  destroyOnClose: true,
});

const [ModelVersionDrawer, modelVersionDrawerApi] = useVbenDrawer({
  connectedComponent: VersionDrawer,
  destroyOnClose: true,
});

const [Grid, gridApi] = useVbenVxeGrid<AiVideoModelApi.Model>({
  formOptions: {
    schema: useModelGridFormSchema(),
  },
  gridOptions: {
    cellConfig: { height: 58 },
    columns: useModelGridColumns(),
    keepSource: true,
    proxyConfig: {
      ajax: {
        query: async ({ page }, formValues) => {
          loadError.value = '';
          try {
            return await getModelPage({
              pageNo: page.currentPage,
              pageSize: page.pageSize,
              ...formValues,
            });
          } catch (error) {
            loadError.value = '模型资产加载失败，请检查服务状态后重试。';
            throw error;
          }
        },
      },
    },
    rowConfig: { isHover: true, keyField: 'id' },
    toolbarConfig: { refresh: true, search: true },
  } as VxeTableGridOptions<AiVideoModelApi.Model>,
});

function createModel() {
  formModalApi.open();
}

function openVersions(row: AiVideoModelApi.Model) {
  modelVersionDrawerApi.setData(row).open();
}

function refresh() {
  gridApi.query();
}

function sourceText(sourceType: string) {
  return sourceType === 'PRESET' ? '预置' : '自定义';
}

function capabilitySummary(capabilities: AiVideoModelApi.ModelCapability[]) {
  return capabilities
    .slice(0, 2)
    .map((item) => item.name)
    .join('、');
}

function acceptedCapabilityCount(
  capabilities: AiVideoModelApi.ModelCapability[],
) {
  return capabilities.filter((item) => item.acceptanceStatus === 'PASS').length;
}

function publishStatusText(status?: string) {
  return (
    {
      DRAFT: '草稿',
      PUBLISHED: '已发布',
      SUPERSEDED: '已替代',
    }[status ?? ''] ?? '未上传'
  );
}

function publishStatusColor(status?: string) {
  return { DRAFT: 'default', PUBLISHED: 'green', SUPERSEDED: 'orange' }[
    status ?? ''
  ];
}
</script>

<template>
  <Page>
    <FormModal @success="refresh" />
    <ModelVersionDrawer @success="refresh" />

    <div v-if="deployableView" class="ai-page ai-page-stack">
      <AiPageHeader
        title="模型中心"
        description="管理可部署模型。"
        icon="lucide:box"
      >
        <template #extra>
          <Button @click="deployableView = false"> 模型资产与历史版本 </Button>
        </template>
      </AiPageHeader>
      <DeployableCatalog @detail="openDeployable" />
    </div>
    <div v-else class="ai-page ai-page-stack">
      <Button class="self-start" @click="deployableView = true">
        查看可部署模型
      </Button>
      <AiPageHeader
        title="模型中心"
        description="管理模型文件与历史版本。"
        icon="lucide:box"
      >
        <template #extra>
          <Button v-if="canCreate" type="primary" @click="createModel">
            <IconifyIcon icon="lucide:plus" />新增模型
          </Button>
        </template>
      </AiPageHeader>

      <Alert v-if="loadError" :message="loadError" show-icon type="error">
        <template #action>
          <Button size="small" @click="refresh">重试</Button>
        </template>
      </Alert>

      <div>
        <Grid table-title="模型列表">
          <template #name="{ row }">
            <div class="model-name-cell text-left">
              <Tooltip :title="row.name">
                <div class="model-name-cell__title">{{ row.name }}</div>
              </Tooltip>
              <div class="model-name-cell__code" :title="row.code">
                {{ row.code }} · {{ row.versionCount ?? 0 }} 个版本
              </div>
            </div>
          </template>
          <template #sourceType="{ row }">
            <Tag :color="row.sourceType === 'PRESET' ? 'blue' : 'default'">
              {{ sourceText(row.sourceType) }}
            </Tag>
          </template>
          <template #latestVersion="{ row }">
            <div v-if="row.latestVersion" class="model-version-cell">
              <Tooltip :title="row.latestVersion">
                <span class="model-version-cell__value">{{
                  row.latestVersion
                }}</span>
              </Tooltip>
              <Tag
                v-if="row.latestVersionId === row.currentVersionId"
                class="model-version-cell__default"
                color="blue"
              >
                默认
              </Tag>
            </div>
            <span v-else class="text-muted-foreground">未上传</span>
          </template>
          <template #outputLabels="{ row }">
            <Tooltip
              v-if="row.outputLabels?.length"
              :title="row.outputLabels.join('、')"
            >
              <div class="model-capability-cell__summary">
                {{ row.outputLabels.slice(0, 3).join('、') }}
              </div>
              <div class="model-capability-cell__meta">
                共 {{ row.outputLabels.length }} 类
              </div>
            </Tooltip>
            <span v-else class="text-muted-foreground">{{
              row.latestVersionId ? '未声明识别类别' : '上传版本后显示'
            }}</span>
          </template>
          <template #capabilities="{ row }">
            <Popover v-if="row.capabilities?.length" placement="bottomLeft">
              <template #content>
                <div class="model-capability-popover">
                  <div class="model-capability-popover__header">
                    {{ row.name }} · {{ row.capabilities.length }} 项关联算法
                  </div>
                  <div class="model-capability-popover__list">
                    <div
                      v-for="capability in row.capabilities"
                      :key="capability.algorithmId"
                      class="model-capability-popover__item"
                    >
                      <div class="min-w-0">
                        <div class="model-capability-popover__name">
                          {{ capability.name }}
                        </div>
                        <div class="model-capability-popover__code">
                          {{ capability.code }}
                        </div>
                      </div>
                      <Tag
                        :color="
                          capability.acceptanceStatus === 'PASS'
                            ? 'green'
                            : 'orange'
                        "
                      >
                        {{
                          capability.acceptanceStatus === 'PASS'
                            ? '已验收'
                            : '待验收'
                        }}
                      </Tag>
                    </div>
                  </div>
                </div>
              </template>
              <div class="model-capability-cell">
                <div class="model-capability-cell__summary">
                  {{ capabilitySummary(row.capabilities) }}
                </div>
                <div class="model-capability-cell__meta">
                  共 {{ row.capabilities.length }} 项 ·
                  {{ acceptedCapabilityCount(row.capabilities) }} 项算法已验收
                </div>
              </div>
            </Popover>
            <span v-else class="text-muted-foreground">尚无当前算法关联</span>
          </template>
          <template #publishStatus="{ row }">
            <Tag :color="publishStatusColor(row.publishStatus)">
              {{ publishStatusText(row.publishStatus) }}
            </Tag>
          </template>
          <template #deployments="{ row }">
            <span v-if="row.latestVersionId">
              {{ row.readyNodeCount ?? 0 }}/{{ row.deployedNodeCount ?? 0 }}
              ready
            </span>
            <span v-else class="text-muted-foreground">—</span>
          </template>
          <template #status="{ row }">
            <AiStatusIndicator
              :label="row.status === 0 ? '启用' : '停用'"
              :status="row.status === 0 ? 'ENABLED' : 'DISABLED'"
              size="sm"
            />
          </template>
          <template #actions="{ row }">
            <TableAction
              :actions="[
                {
                  label: '版本与部署',
                  type: 'link',
                  onClick: () => openVersions(row),
                },
              ]"
            />
          </template>
        </Grid>
      </div>
    </div>
  </Page>
</template>

<style scoped>
.model-name-cell {
  display: grid;
  gap: 3px;
  min-width: 0;
  padding-block: 5px;
  line-height: 1.25;
}

.model-name-cell__title,
.model-name-cell__code {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.model-name-cell__title {
  font-size: 13px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.model-name-cell__code {
  font-family: var(--font-family-mono, ui-monospace, monospace);
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.model-version-cell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.model-version-cell__value {
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-family-mono, ui-monospace, monospace);
  font-size: 12px;
  white-space: nowrap;
}

.model-version-cell__default {
  flex: 0 0 auto;
}

.model-capability-cell {
  min-width: 0;
  line-height: 1.35;
  text-align: left;
  cursor: help;
}

.model-capability-cell__summary {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--foreground));
  white-space: nowrap;
}

.model-capability-cell__meta {
  margin-top: 3px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
}

.model-capability-popover {
  width: 420px;
}

.model-capability-popover__header {
  margin-bottom: 8px;
  font-size: 13px;
  font-weight: 600;
}

.model-capability-popover__list {
  display: grid;
  gap: 6px;
  max-height: 320px;
  overflow-y: auto;
}

.model-capability-popover__item {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
  padding: 7px 8px;
  background: hsl(var(--muted) / 42%);
  border-radius: 6px;
}

.model-capability-popover__name {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}

.model-capability-popover__code {
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--font-family-mono, ui-monospace, monospace);
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}
</style>
