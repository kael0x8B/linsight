<script lang="ts" setup>
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type { TaskEvaluation } from '#/api/ai-video/task/evaluation';

import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';
import { Page, useVbenDrawer } from '@vben/common-ui';

import { Alert, Button, Empty, Tag } from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { getTaskEvaluationPage } from '#/api/ai-video/task/evaluation';
import { AiPageHeader } from '#/components/ai-video';

import EvaluationDetail from './modules/evaluation-detail.vue';
import EvaluationForm from './modules/evaluation-form.vue';

const { hasAccessByCodes } = useAccess();
const canQuery = computed(() => hasAccessByCodes(['ai-video:task:query']));
const canRecord = computed(
  () => canQuery.value && hasAccessByCodes(['ai-video:task:update']),
);
const error = ref('');
const [FormDrawer, formDrawerApi] = useVbenDrawer({
  connectedComponent: EvaluationForm,
  destroyOnClose: true,
});
const [DetailDrawer, detailDrawerApi] = useVbenDrawer({
  connectedComponent: EvaluationDetail,
  destroyOnClose: true,
});
const [Quickstart, quickstartApi] = useVbenDrawer({
  showConfirmButton: false,
  showCancelButton: false,
});
const [Grid, gridApi] = useVbenVxeGrid({
  formOptions: {
    submitOnChange: true,
    schema: [
      {
        component: 'InputNumber',
        fieldName: 'taskId',
        label: '任务编号',
        componentProps: { min: 1, precision: 0 },
      },
      {
        component: 'Select',
        fieldName: 'status',
        label: '评测结果',
        componentProps: {
          allowClear: true,
          options: [
            { label: '指标达标', value: 'PASS' },
            { label: '指标未达标', value: 'FAIL' },
          ],
        },
      },
    ],
  },
  gridOptions: {
    height: 'auto',
    minHeight: 320,
    columns: [
      { field: 'id', title: '记录编号', width: 100, fixed: 'left' },
      { field: 'taskName', title: '任务', minWidth: 180 },
      { field: 'configVersion', title: '配置版本', width: 100 },
      { field: 'datasetVersion', title: '测试集', minWidth: 180 },
      {
        field: 'status',
        title: '结果',
        width: 120,
        slots: { default: 'status' },
      },
      {
        field: 'source',
        title: '来源',
        width: 130,
        formatter: () => '人工视频实测',
      },
      {
        field: 'measuredAtMillis',
        title: '测试时间',
        minWidth: 225,
        formatter: ({ cellValue }) =>
          new Date(cellValue).toLocaleString('zh-CN', {
            timeZoneName: 'short',
          }),
      },
      {
        field: 'actions',
        title: '操作',
        width: 100,
        fixed: 'right',
        slots: { default: 'actions' },
      },
    ],
    proxyConfig: {
      ajax: {
        query: async ({ page }, values) => {
          if (!canQuery.value) return { list: [], total: 0 };
          error.value = '';
          try {
            return await getTaskEvaluationPage({
              pageNo: page.currentPage,
              pageSize: page.pageSize,
              ...values,
            });
          } catch (cause) {
            error.value = '评测历史加载失败，请检查连接后重试。';
            throw cause;
          }
        },
      },
    },
    rowConfig: { keyField: 'id', isHover: true },
    toolbarConfig: { refresh: true },
  } as VxeTableGridOptions<TaskEvaluation>,
});
function saved(id: number) {
  void gridApi.query();
  detailDrawerApi.setData({ id }).open();
}
</script>

<template>
  <Page auto-content-height>
    <FormDrawer @success="saved" />
    <DetailDrawer />
    <Quickstart
      title="SDK 快速入门"
      class="ai-dialog w-[780px] max-w-[calc(100vw-24px)]"
      :footer="false"
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
    >
      <p class="mb-4">
        在项目 runtime 目录使用 Python 3.12 或 3.13。首次安装执行 pip install -e
        '.[test]'。
      </p>
      <pre class="overflow-auto rounded border p-4 text-sm">
python -m ai_runtime.sdk init /tmp/hello-person
python -m ai_runtime.sdk check /tmp/hello-person
python -m ai_runtime.sdk run /tmp/hello-person \
  --fixture /tmp/hello-person/fixtures/frame.json \
  --expect /tmp/hello-person/fixtures/expected.json \
  --output /tmp/sdk-result.json
python -m ai_runtime.sdk pack /tmp/hello-person \
  --output /tmp/hello-person.zip</pre
      >
      <p class="mt-4">
        示例使用合成检测输入，适合验证包契约和处理逻辑。编辑 processor.py
        后重新运行，错误报告会包含阶段、文件行号和诊断 ID。
      </p>
      <p class="mt-4">
        真实视频评测：在算法中心上传
        ZIP，绑定模型版本与规则，在网关运行测试任务，再来此记录实测指标和证据。完整说明见项目
        docs/algorithm-packages/QUICKSTART.md。
      </p>
    </Quickstart>
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="视频评测记录"
        description="留存测试指标、证据与配置版本。"
        icon="lucide:clipboard-check"
      >
        <template #extra>
          <Button @click="quickstartApi.open()">SDK 快速入门</Button>
          <Button v-if="canRecord" type="primary" @click="formDrawerApi.open()"
            >记录评测</Button
          >
        </template>
      </AiPageHeader>
      <Alert
        v-if="!canQuery"
        type="warning"
        message="需要任务查询权限才能查看评测记录。"
        show-icon
      />
      <Alert v-if="error" :message="error" type="error" show-icon>
        <template #action
          ><Button @click="gridApi.query()">重试</Button></template
        >
      </Alert>
      <Grid v-if="canQuery" class="min-h-0 flex-1" table-title="评测历史">
        <template #empty
          ><Empty
            :description="
              error
                ? '评测历史暂不可用，请重试。'
                : '暂无评测记录；完成视频测试后可记录指标与证据。'
            "
        /></template>
        <template #status="{ row }"
          ><Tag :color="row.status === 'PASS' ? 'green' : 'orange'">{{
            row.status === 'PASS' ? '指标达标' : '指标未达标'
          }}</Tag></template
        >
        <template #actions="{ row }"
          ><TableAction
            :actions="[
              {
                label: '查看',
                type: 'link',
                onClick: () => detailDrawerApi.setData({ id: row.id }).open(),
              },
            ]"
        /></template>
      </Grid>
    </div>
  </Page>
</template>
