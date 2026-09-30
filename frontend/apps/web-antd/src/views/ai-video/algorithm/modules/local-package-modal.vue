<script setup lang="ts">
import type { AlgorithmManifest } from '#/api/ai-video/algorithm/package';
import type {
  GatewaySnapshot,
  GatewayTask,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';
import type { PreviewTransport } from '#/components/ai-video/preview-transport';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Alert, message, Select } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { gatewayRequestId } from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';

import GatewayRuleEditor from '../../node/modules/gateway-rule-editor.vue';
import PackageParameters from './package-parameters.vue';

const props = defineProps<{ transport: GatewayTransport }>();
const emit = defineEmits<{
  configurePipeline: [template: string];
  success: [];
}>();
type Installed = {
  manifest: AlgorithmManifest;
  sha256: string;
  status: string;
};
const packages = ref<Installed[]>([]);
const selected = ref<Installed>();
const snapshot = ref<GatewaySnapshot>({
  tasks: [],
  models: [],
  historyDays: 7,
});
const existing = ref<GatewayTask>();
const configForm = ref<InstanceType<typeof PackageParameters>>();
const ruleText = ref('');
const ruleEditor = ref<InstanceType<typeof GatewayRuleEditor>>();
const statisticsOnly = computed(
  () => selected.value?.manifest.outputMode === 'STATISTICS',
);
const camera = computed(() =>
  existing.value
    ? {
        id: existing.value.config.cameraId,
        code: `camera-${existing.value.config.cameraId}`,
        name: '当前摄像头',
        status: 0,
      }
    : undefined,
);
const previewTransport = computed<PreviewTransport>(() => {
  const taskId = existing.value?.config.taskId;
  return {
    create: (offer) => props.transport('preview.open', { taskId, ...offer }),
    get: (sessionId) =>
      props.transport('preview.status', { taskId, sessionId }),
    release: (sessionId) =>
      props.transport('preview.close', { taskId, sessionId }),
  };
});
const bindings = ref<Record<string, number>>({});
const error = ref('');
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'name',
      label: '配置名称',
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'sha256',
      label: '识别算法',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({
        disabled: !!existing.value,
        showSearch: true,
        optionFilterProp: 'label',
        placeholder: '请选择识别算法',
        options: [
          ...packages.value
            .filter((p) => p.status === 'READY')
            .map((p) => ({
              label: `${p.manifest.name} · v${p.manifest.version}`,
              value: p.sha256,
            })),
          ...(!existing.value &&
          snapshot.value.capabilities?.includes('vehicle.plate.front.v1')
            ? [
                {
                  label: $t('ai-video-delivery.plateTaskDefault'),
                  value: 'builtin:license-plate',
                },
              ]
            : []),
        ],
        onChange: choose,
      }),
    },
    {
      fieldName: 'cameraId',
      label: '已有摄像头',
      component: 'Select',
      componentProps: () => ({
        disabled: !!existing.value,
        allowClear: true,
        showSearch: true,
        optionFilterProp: 'label',
        placeholder: '选择已有摄像头，或填写下方视频流地址',
        options: [
          ...new Map(
            snapshot.value.tasks.map((t) => [
              t.config.cameraId,
              {
                label:
                  snapshot.value.names?.cameras[t.config.cameraId] ||
                  `摄像头 #${t.config.cameraId}`,
                value: t.config.cameraId,
              },
            ]),
          ).values(),
        ],
      }),
    },
    {
      fieldName: 'sourceUrl',
      label: '视频流地址',
      component: 'InputPassword',
      help: '新摄像头填写 RTSP 地址；已有摄像头留空以复用。',
      componentProps: { autocomplete: 'new-password' },
    },
  ],
});
function options(role: AlgorithmManifest['models'][number]) {
  return snapshot.value.models
    .filter(
      (m) =>
        (!role.formats?.length || role.formats.includes(m.artifactFormat)) &&
        (!role.taskType || role.taskType === m.runtimeManifest?.taskType) &&
        (role.labels ?? []).every((label) =>
          m.runtimeManifest?.decoder?.labels?.includes(label),
        ),
    )
    .map((m) => ({
      value: m.modelVersionId,
      label: `${snapshot.value.names?.models[m.modelVersionId]?.name || '模型'} #${m.modelVersionId} · ${m.device}`,
    }));
}
function choose(digest: string) {
  if (digest === 'builtin:license-plate') {
    modal.close();
    emit('configurePipeline', 'license-plate');
    return;
  }
  selected.value = packages.value.find((p) => p.sha256 === digest);
  const rule =
    existing.value?.config.rule ?? selected.value?.manifest.defaultRule;
  ruleText.value = rule ? JSON.stringify(rule, null, 2) : '';
  bindings.value = existing.value
    ? { ...existing.value.config.modelBindings }
    : Object.fromEntries(
        (selected.value?.manifest.models ?? []).map((role) => [
          role.slot,
          options(role)[0]?.value ?? 0,
        ]),
      );
}
const [Modal, modal] = useVbenModal({
  title: '配置本机算法',
  class: 'w-[800px]',
  confirmText: '保存并启动',
  async onOpenChange(open) {
    if (!open) return;
    error.value = '';
    selected.value = undefined;
    existing.value = modal.getData<{ task?: GatewayTask }>()?.task;
    try {
      snapshot.value = await props.transport<GatewaySnapshot>('snapshot');
      packages.value = await props.transport<Installed[]>('algorithm.list');
      await form.resetForm();
      const digest = (
        existing.value?.config.pipeline.algorithmPackage as
          | Installed
          | undefined
      )?.sha256;
      await form.setValues({
        name: existing.value?.name,
        cameraId: existing.value?.config.cameraId,
        sha256: digest,
      });
      if (digest) choose(digest);
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '加载失败';
    }
  },
  async onConfirm() {
    const validation = await form.validate();
    if (!validation.valid || !selected.value) return;
    if (statisticsOnly.value) ruleText.value = '';
    if (ruleEditor.value && !ruleEditor.value.validate()) return;
    const parameters = await configForm.value?.values();
    if (!parameters) return;
    if (
      selected.value.manifest.models.some((role) => !bindings.value[role.slot])
    ) {
      message.warning('请先安装所有依赖模型');
      return;
    }
    const values = await form.getValues();
    const id = existing.value?.config.taskId ?? Date.now();
    if (!values.cameraId && !values.sourceUrl) {
      message.warning('请选择摄像头或填写视频流地址');
      return;
    }
    modal.lock();
    error.value = '';
    try {
      const result = await props.transport<GatewayTask>('task.save', {
        taskId: id,
        expectedRevision: existing.value?.revision ?? 0,
        requestId: gatewayRequestId(),
        name: values.name,
        enabled: true,
        configuration: {
          ...existing.value?.config,
          taskId: id,
          cameraId: Number(values.cameraId || id),
          algorithmId: existing.value?.config.algorithmId ?? id,
          pipelineVersionId: existing.value?.config.pipelineVersionId ?? id,
          runId: existing.value?.config.runId ?? gatewayRequestId(),
          configVersion: existing.value?.config.configVersion ?? 1,
          sourceUrl: values.sourceUrl || undefined,
          displayNames: {
            algorithm: selected.value.manifest.name,
            camera:
              existing.value?.displayNames?.camera ||
              existing.value?.config.displayNames?.camera ||
              snapshot.value.names?.cameras[Number(values.cameraId)] ||
              (values.cameraId ? `摄像头 #${values.cameraId}` : '本地摄像头'),
            task: values.name,
          },
          modelVersionId: Object.values(bindings.value)[0],
          modelBindings: bindings.value,
          pipeline: {
            schemaVersion: '1.0',
            nodes: selected.value.manifest.models.map((m) => ({
              id: m.slot,
              type: 'DETECTOR',
              capabilityKey: `model.${m.slot}`,
            })),
            edges: [],
            algorithmPackage: {
              sha256: selected.value.sha256,
              manifest: selected.value.manifest,
            },
          },
          parameters: {
            schemaVersion: '1.0',
            confidence: 0.5,
            sampleFps: 1,
            ...existing.value?.config.parameters,
            algorithm: parameters,
          },
          rule: ruleText.value ? JSON.parse(ruleText.value) : null,
          ruleId: ruleText.value ? (existing.value?.config.ruleId ?? id) : null,
          ruleVersionId: ruleText.value
            ? (existing.value?.config.ruleVersionId ?? id)
            : null,
        },
      });
      if (result.appliedRevision !== result.revision)
        throw new Error(
          result.status.errorMessage || '配置已保存，等待运行恢复',
        );
      message.success('识别配置已应用');
      modal.close();
      emit('success');
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : '保存失败';
    } finally {
      modal.unlock();
    }
  },
});
</script>
<template>
  <Modal>
    <div class="space-y-4">
      <Alert v-if="error" :message="error" type="error" show-icon /><Form />
      <template v-if="selected">
        <div v-for="role in selected.manifest.models" :key="role.slot">
          <p>{{ role.name || role.slot }}</p>
          <Select
            v-model:value="bindings[role.slot]"
            class="w-full"
            :options="options(role)"
            placeholder="请先在本机安装兼容模型"
          />
        </div>
        <Alert
          v-if="selected.manifest.resources?.length"
          type="info"
          message="使用已同步到本机的人员库。可修改参与比对人员和识别阈值。"
        />
        <Alert
          v-if="statisticsOnly"
          type="info"
          message="统计区域内当前人数，在实时画面显示结果；无需人员库，不生成离岗告警。各摄像头分别统计。"
        />
        <PackageParameters
          ref="configForm"
          :manifest="selected.manifest"
          :initial="
            existing?.config.parameters.algorithm as Record<string, unknown>
          "
          :options="existing?.resourceOptions"
          local
        />
        <div v-if="!statisticsOnly" class="border-t pt-4">
          <GatewayRuleEditor
            :key="selected.sha256"
            ref="ruleEditor"
            v-model="ruleText"
            local
            :camera="camera"
            :task-id="existing?.config.taskId"
            :preview-transport="previewTransport"
            :event-type="selected.manifest.eventType"
            :default-rule="selected.manifest.defaultRule"
          />
        </div>
      </template>
    </div>
  </Modal>
</template>
