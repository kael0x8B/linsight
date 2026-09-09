<script lang="ts" setup>
import { onMounted, reactive, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Button, Form, FormItem, Input, InputNumber, message, RadioGroup, Select, Space, Table } from 'ant-design-vue';

import { createAlgorithm } from '#/api/ai-video/algorithm';
import { getModelPage } from '#/api/ai-video/model';

interface ParameterRow {
  defaultValue: boolean | number | string;
  key: string;
  label: string;
  max?: number;
  min?: number;
  type: 'boolean' | 'integer' | 'number' | 'string';
}

const emit = defineEmits<{ success: [id: number] }>();
const models = ref<{ label: string; value: number }[]>([]);
const parameterRows = ref<ParameterRow[]>([]);
const form = reactive({
  capabilityKey: '', category: 'CUSTOM', code: '', defaultModelId: undefined as number | undefined,
  description: '', eventType: '', implementationType: 'MODEL_DIRECT', name: '',
  requiredCapabilities: [] as string[], sceneGroup: 'GENERAL', status: 0,
});

const parameterColumns = [
  { dataIndex: 'key', title: '参数键', width: 150 },
  { dataIndex: 'label', title: '页面名称', width: 150 },
  { dataIndex: 'type', title: '类型', width: 120 },
  { dataIndex: 'defaultValue', title: '默认值', width: 130 },
  { dataIndex: 'range', title: '范围', width: 170 },
  { key: 'actions', title: '', width: 52 },
];

const [Modal, modalApi] = useVbenModal({
  async onConfirm() {
    if (!form.name.trim() || !form.code.trim() || !form.capabilityKey.trim()) {
      message.warning('请填写能力名称、稳定编码和能力键');
      return;
    }
    const properties: Record<string, Record<string, unknown>> = {};
    const defaults: Record<string, unknown> = { schemaVersion: '1.0' };
    for (const row of parameterRows.value) {
      if (!row.key.trim() || !row.label.trim()) {
        message.warning('参数键和页面名称不能为空');
        return;
      }
      const property: Record<string, unknown> = { title: row.label, type: row.type };
      if (row.min != null) property.minimum = row.min;
      if (row.max != null) property.maximum = row.max;
      properties[row.key] = property;
      defaults[row.key] = normalizeDefault(row);
    }
    modalApi.lock();
    try {
      const id = await createAlgorithm({
        ...form,
        defaultParameters: defaults,
        eventType: form.eventType || undefined,
        parameterSchema: { properties, schemaVersion: '1.0', type: 'object' },
      } as never);
      message.success('AI 能力已创建，请继续配置并发布 Pipeline');
      await modalApi.close();
      emit('success', id);
    } finally {
      modalApi.unlock();
    }
  },
  onOpenChange(open) {
    if (!open) return;
    Object.assign(form, {
      capabilityKey: '', category: 'CUSTOM', code: '', defaultModelId: undefined,
      description: '', eventType: '', implementationType: 'MODEL_DIRECT', name: '',
      requiredCapabilities: [], sceneGroup: 'GENERAL', status: 0,
    });
    parameterRows.value = [];
  },
});

function normalizeDefault(row: ParameterRow) {
  if (row.type === 'boolean') return row.defaultValue === true || row.defaultValue === 'true';
  if (row.type === 'integer') return Math.trunc(Number(row.defaultValue || 0));
  if (row.type === 'number') return Number(row.defaultValue || 0);
  return String(row.defaultValue ?? '');
}

function addParameter() {
  parameterRows.value.push({ defaultValue: '', key: '', label: '', type: 'number' });
}

onMounted(async () => {
  const result = await getModelPage({ pageNo: 1, pageSize: 100, status: 0 });
  models.value = result.list.filter((item) => item.id).map((item) => ({ label: item.name, value: item.id! }));
});
</script>

<template>
  <Modal class="w-[960px] max-w-[calc(100vw-32px)]" title="新增 AI 能力">
    <Form :model="form" layout="vertical">
      <div class="grid grid-cols-3 gap-x-4">
        <FormItem label="能力名称" required><Input v-model:value="form.name" placeholder="例如：消防通道占用" /></FormItem>
        <FormItem label="稳定编码" required><Input v-model:value="form.code" placeholder="fire-lane-occupied" /></FormItem>
        <FormItem label="能力键" required><Input v-model:value="form.capabilityKey" placeholder="rule.fire-lane-occupied" /></FormItem>
        <FormItem label="场景分组"><Input v-model:value="form.sceneGroup" placeholder="例如 FIRE_SAFETY" /></FormItem>
        <FormItem label="实现方式"><Select v-model:value="form.implementationType" :options="[
          { label: '模型直接识别', value: 'MODEL_DIRECT' }, { label: '模型类别过滤', value: 'MODEL_FILTER' },
          { label: '跟踪与规则', value: 'TRACK_RULE' }, { label: '传统视觉', value: 'CLASSICAL_CV' }, { label: '多能力组合', value: 'COMPOSITE' },
        ]" /></FormItem>
        <FormItem label="默认模型"><Select v-model:value="form.defaultModelId" allow-clear show-search option-filter-prop="label" :options="models" /></FormItem>
        <FormItem label="依赖能力"><Select v-model:value="form.requiredCapabilities" mode="tags" placeholder="输入能力键后回车，可配置多个" /></FormItem>
        <FormItem label="事件类型"><Input v-model:value="form.eventType" placeholder="留空表示只输出识别结果" /></FormItem>
        <FormItem label="状态"><RadioGroup v-model:value="form.status" :options="[{ label: '启用', value: 0 }, { label: '停用', value: 1 }]" /></FormItem>
      </div>
      <FormItem label="能力说明"><Input.TextArea v-model:value="form.description" :maxlength="500" :rows="2" /></FormItem>

      <div class="mb-3 flex items-center justify-between"><strong>页面参数</strong><Button @click="addParameter"><IconifyIcon icon="lucide:plus" />添加参数</Button></div>
      <Table :columns="parameterColumns" :data-source="parameterRows" :pagination="false" row-key="key" size="small">
        <template #bodyCell="{ column, record, index }">
          <Input v-if="column.dataIndex === 'key'" v-model:value="record.key" placeholder="durationSeconds" />
          <Input v-else-if="column.dataIndex === 'label'" v-model:value="record.label" placeholder="持续时间" />
          <Select v-else-if="column.dataIndex === 'type'" v-model:value="record.type" :options="[
            { label: '小数', value: 'number' }, { label: '整数', value: 'integer' }, { label: '文字', value: 'string' }, { label: '开关', value: 'boolean' },
          ]" />
          <Input v-else-if="column.dataIndex === 'defaultValue'" v-model:value="record.defaultValue" />
          <Space v-else-if="column.dataIndex === 'range'"><InputNumber v-model:value="record.min" placeholder="最小" /><InputNumber v-model:value="record.max" placeholder="最大" /></Space>
          <Button v-else-if="column.key === 'actions'" danger type="text" @click="parameterRows.splice(index, 1)"><IconifyIcon icon="lucide:x" /></Button>
        </template>
        <template #emptyText>没有固定参数时可以保持为空，任务页面仍会使用通用推理参数。</template>
      </Table>
    </Form>
  </Modal>
</template>
