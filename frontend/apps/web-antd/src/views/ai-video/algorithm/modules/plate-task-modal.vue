<script setup lang="ts">
import type {
  GatewayCapacityPreflight,
  GatewaySnapshot,
  GatewayTask,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';

import { computed, ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Alert, message, TabPane, Tabs } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { gatewayRequestId } from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';

import { gatewayCapacitySummary } from '../../node/gateway-capacity';
import GatewayRuleEditor from '../../node/modules/gateway-rule-editor.vue';

const props = defineProps<{
  snapshot: GatewaySnapshot;
  transport: GatewayTransport;
}>();
const emit = defineEmits<{ saved: [] }>();
const t = (key: string) => $t(`ai-video-delivery.${key}`);
const error = ref('');
const activeTab = ref('basic');
const ruleText = ref('');
const ruleEditor = ref<InstanceType<typeof GatewayRuleEditor>>();
const modelOptions = (role: string) =>
  props.snapshot.models
    .filter((model) => {
      const decoder = model.runtimeManifest?.decoder;
      return (
        role === 'plate'
          ? ['YOLO_PLATE', 'LPD_YUNET']
          : ['CHINESE_PLATE_CTC', 'LPRNET']
      ).includes(String(decoder?.type));
    })
    .sort((a, b) => {
      const preferred = role === 'plate' ? 'YOLO_PLATE' : 'CHINESE_PLATE_CTC';
      return (
        Number(b.runtimeManifest?.decoder?.type === preferred) -
          Number(a.runtimeManifest?.decoder?.type === preferred) ||
        Number(b.device === 'RKNPU') - Number(a.device === 'RKNPU')
      );
    })
    .map((model) => ({
      value: model.modelVersionId,
      label: `${model.displayName || model.modelVersionId} · ${model.version || model.artifactFormat}`,
    }));
const cameraOptions = computed(() => {
  const cameras = new Map<number, { label: string; value: number }>();
  for (const task of props.snapshot.tasks)
    cameras.set(task.config.cameraId, {
      value: task.config.cameraId,
      label:
        props.snapshot.names?.cameras[String(task.config.cameraId)] ||
        task.displayNames?.camera ||
        `${task.config.cameraId}`,
    });
  return [...cameras.values()];
});
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'name',
      label: t('taskName'),
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'cameraId',
      label: t('existingCamera'),
      component: 'Select',
      componentProps: () => ({
        allowClear: true,
        options: cameraOptions.value,
        placeholder: t('newCameraHint'),
      }),
    },
    {
      fieldName: 'cameraName',
      label: t('cameraName'),
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'sourceUrl',
      label: t('sourceUrl'),
      component: 'InputPassword',
      componentProps: {
        autocomplete: 'new-password',
        placeholder: t('sourceHint'),
      },
    },
    {
      fieldName: 'plateModel',
      label: t('plateModel'),
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: modelOptions('plate') }),
    },
    {
      fieldName: 'ocrModel',
      label: t('ocrModel'),
      component: 'Select',
      rules: 'required',
      componentProps: () => ({ options: modelOptions('ocr') }),
    },
    {
      fieldName: 'sampleFps',
      label: t('sampleFps'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 0.1, max: 10, step: 0.5 },
    },
    {
      fieldName: 'ocrMinConfidence',
      label: t('ocrMinConfidence'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 0.01, max: 1, step: 0.05 },
    },
    {
      fieldName: 'ocrMinVotes',
      label: t('ocrMinVotes'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 2, max: 30 },
    },
    {
      fieldName: 'ocrVoteFrames',
      label: t('ocrVoteFrames'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 2, max: 30 },
    },
    {
      fieldName: 'recoverySeconds',
      label: t('recoverySeconds'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 1, max: 300 },
    },
  ],
});
function defaultRule() {
  return {
    schemaVersion: '1.0',
    eventType: 'VEHICLE_PLATE_RECOGNIZED',
    severity: 'INFO',
    regions: [
      {
        id: 'plate-area',
        name: t('recognitionArea'),
        type: 'POLYGON',
        sourceWidth: 1920,
        sourceHeight: 1080,
        pointMode: 'CENTROID',
        overlapThreshold: 0,
        points: [
          { x: 0, y: 0 },
          { x: 1, y: 0 },
          { x: 1, y: 1 },
          { x: 0, y: 1 },
        ],
      },
    ],
    schedule: {
      timezone: 'Asia/Shanghai',
      weekly: [{ days: [1, 2, 3, 4, 5, 6, 7], start: '00:00', end: '23:59' }],
    },
    condition: {
      type: 'AND',
      children: [
        {
          type: 'ROI_ENTER',
          regionId: 'plate-area',
          objectClasses: ['license_plate'],
        },
        { type: 'N_OF_M', n: 1, m: 1 },
        { type: 'DURATION', seconds: 0 },
      ],
    },
    cooldownSeconds: 0,
    recoverySeconds: 5,
    dedup: { scope: 'TRACK', windowSeconds: 60 },
  };
}
const [Modal, modal] = useVbenModal({
  title: t('createPlateTask'),
  class: 'w-[900px]',
  async onOpenChange(open) {
    if (!open) return;
    error.value = '';
    activeTab.value = 'basic';
    ruleText.value = JSON.stringify(defaultRule());
    await form.resetForm();
    await form.setValues({
      name: t('plateTaskDefault'),
      cameraName: '',
      sampleFps:
        props.snapshot.models.find(
          (model) => model.modelVersionId === modelOptions('plate')[0]?.value,
        )?.device === 'RKNPU'
          ? 4
          : 2,
      ocrMinConfidence: 0.75,
      ocrMinVotes: 3,
      ocrVoteFrames: 5,
      recoverySeconds: 5,
      plateModel: modelOptions('plate')[0]?.value,
      ocrModel: modelOptions('ocr')[0]?.value,
    });
  },
  async onConfirm() {
    if (!(await form.validate()).valid) {
      activeTab.value = 'basic';
      return;
    }
    if (ruleEditor.value && !ruleEditor.value.validate()) {
      activeTab.value = 'region';
      return;
    }
    modal.lock();
    try {
      const values = await form.getValues();
      if (!values.cameraId && !values.sourceUrl)
        throw new Error(t('sourceRequired'));
      if (Number(values.ocrMinVotes) > Number(values.ocrVoteFrames))
        throw new Error(t('votesInvalid'));
      const id = Date.now();
      const configuration = {
        taskId: id,
        runId: gatewayRequestId(),
        cameraId: Number(values.cameraId || id),
        algorithmId: id,
        pipelineVersionId: id,
        configVersion: 1,
        sourceUrl: values.sourceUrl || undefined,
        modelVersionId: Number(values.plateModel),
        displayNames: {
          task: values.name,
          camera: values.cameraName,
          algorithm: t('plateTaskDefault'),
        },
        modelBindings: {
          plate: Number(values.plateModel),
          ocr: Number(values.ocrModel),
        },
        pipeline: {
          schemaVersion: '1.0',
          acceptance: { status: 'PENDING' },
          nodes: [
            {
              id: 'plate',
              type: 'DETECTOR',
              capabilityKey: 'detector.license-plate',
            },
            { id: 'ocr', type: 'OCR', capabilityKey: 'ocr.license-plate' },
            { id: 'tracker', type: 'TRACKER', capabilityKey: 'tracker.iou' },
          ],
          edges: [
            { from: 'plate', to: 'ocr' },
            { from: 'ocr', to: 'tracker' },
          ],
        },
        parameters: {
          schemaVersion: '1.0',
          validationOnly: true,
          confidence: 0.5,
          sampleFps: Number(values.sampleFps),
          ocrMinConfidence: Number(values.ocrMinConfidence),
          ocrMinVotes: Number(values.ocrMinVotes),
          ocrVoteFrames: Number(values.ocrVoteFrames),
          ocrVoteMaxAgeSeconds: 10,
          plateUseRuleRoi: true,
          plateMaxCandidates: 10,
        },
        ruleId: id,
        ruleVersionId: id,
        rule: {
          ...JSON.parse(ruleText.value),
          recoverySeconds: Number(values.recoverySeconds),
        },
      };
      const capacity = await props.transport<GatewayCapacityPreflight>(
        'task.capacity.preflight',
        {
          taskId: id,
          modelVersionIds: Object.values(configuration.modelBindings),
        },
      );
      await props.transport<GatewayTask>('task.save', {
        taskId: id,
        expectedRevision: 0,
        requestId: gatewayRequestId(),
        name: values.name,
        enabled: false,
        configuration,
      });
      modal.close();
      emit('saved');
      if (!capacity.allowed) message.warning(capacity.message);
      else
        message.success(
          `${t('taskSaved')} ${gatewayCapacitySummary(capacity)}`,
        );
    } catch (cause) {
      error.value = cause instanceof Error ? cause.message : t('saveFailed');
    } finally {
      modal.unlock();
    }
  },
});
</script>
<template>
  <Modal>
    <Alert v-if="error" class="mb-3" type="error" show-icon :message="error" />
    <Alert
      v-if="
        !modelOptions('plate').length ||
        !modelOptions('ocr').length
      "
      class="mb-3"
      type="warning"
      show-icon
      :message="t('modelsMissing')"
    />
    <Tabs v-model:active-key="activeTab">
      <TabPane key="basic" :tab="t('recognitionSettings')"><Form /></TabPane>
      <TabPane key="region" :tab="t('recognitionArea')"
        ><GatewayRuleEditor ref="ruleEditor" v-model="ruleText"
      /></TabPane>
    </Tabs>
  </Modal>
</template>
