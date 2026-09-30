<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Tag } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getRulePage } from '#/api/ai-video/rule';
import { AiPageHeader } from '#/components/ai-video';
import { $t } from '#/locales';

import RuleEditor from './modules/rule-editor.vue';
import RuleForm from './modules/rule-form.vue';
const { hasAccessByCodes } = useAccess();
const canCreate = computed(() => hasAccessByCodes(['ai-video:rule:create']));
const error = ref('');
const [CreateModal, createApi] = useVbenModal({
  connectedComponent: RuleForm,
  destroyOnClose: true,
});
const [EditorDrawer, editorApi] = useVbenDrawer({
  connectedComponent: RuleEditor,
  destroyOnClose: true,
});
const [Grid, gridApi] = useVbenVxeGrid<AiVideoRuleApi.Rule>({
  formOptions: {
    schema: [
      { fieldName: 'name', label: '规则名称', component: 'Input' },
      { fieldName: 'eventType', label: '事件类型', component: 'Input' },
    ],
  },
  gridOptions: {
    columns: [
      { field: 'name', title: '规则名称', minWidth: 180, fixed: 'left' },
      {
        field: 'code',
        title: '用途',
        width: 140,
        formatter: ({ cellValue }: { cellValue: string }) =>
          cellValue?.startsWith('task-rule-') ? '独立识别配置' : '可复用模板',
      },
      { field: 'eventType', title: '事件类型', minWidth: 150 },
      {
        field: 'currentVersionId',
        title: '发布状态',
        width: 120,
        slots: { default: 'version' },
      },
      { field: 'description', title: '说明', minWidth: 200 },
      {
        field: 'status',
        title: '状态',
        width: 90,
        slots: { default: 'status' },
      },
      {
        field: 'actions',
        title: '操作',
        width: 120,
        fixed: 'right',
        slots: { default: 'actions' },
      },
    ],
    rowConfig: { keyField: 'id', isHover: true },
    toolbarConfig: { refresh: true, search: true },
    proxyConfig: {
      ajax: {
        query: async (
          { page }: { page: { currentPage: number; pageSize: number } },
          values: Record<string, unknown>,
        ) => {
          error.value = '';
          try {
            return await getRulePage({
              ...values,
              pageNo: page.currentPage,
              pageSize: page.pageSize,
            });
          } catch (cause) {
            error.value = '规则加载失败，请重试。';
            throw cause;
          }
        },
      },
    },
  },
});
function refresh() {
  void gridApi.query();
}
</script>
<template>
  <Page auto-content-height>
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="告警规则模板"
        :description="$t('rule-canvas.templateScope')"
        icon="lucide:pentagon"
      >
        <template #extra>
          <Button v-if="canCreate" type="primary" @click="createApi.open()">
            新建模板
          </Button>
        </template>
      </AiPageHeader>

      <Alert v-if="error" :message="error" type="error" show-icon>
        <template #action><Button @click="refresh">重试</Button></template>
      </Alert>
      <Grid class="min-h-0 flex-1" table-title="模板与配置规则">
        <template #version="{ row }">
          <Tag :color="row.currentVersionId ? 'green' : 'orange'">
            {{ row.currentVersionId ? '已发布' : '未发布' }}
          </Tag>
        </template>
        <template #status="{ row }">
          {{ row.status === 0 ? '启用' : '停用' }}
        </template>
        <template #actions="{ row }">
          <TableAction
            :actions="[
              {
                label: '编辑规则',
                onClick: () => editorApi.setData(row).open(),
              },
            ]"
          />
        </template>
      </Grid>
    </div>
    <CreateModal @success="refresh" /><EditorDrawer @success="refresh" />
  </Page>
</template>
