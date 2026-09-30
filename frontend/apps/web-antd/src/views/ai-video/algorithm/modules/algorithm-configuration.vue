<script setup lang="ts">
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { ExecutableModelOption } from '#/api/ai-video/model';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useVbenModal } from '@vben/common-ui';

import { Alert, Button, message, Select, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getAlgorithm, getPipelineVersions } from '#/api/ai-video/algorithm';
import { getCameraPage } from '#/api/ai-video/camera';
import {
  deployModelVersion,
  getExecutableModelOptions,
  getNodeModelDeployments,
} from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { getPublishedRules, getRuleVersions } from '#/api/ai-video/rule';
import { createTask, startTask, updateTask } from '#/api/ai-video/task';
import { modelExecutionLabel } from '#/views/ai-video/model/execution-presentation';
import { gatewayLocation } from '#/views/ai-video/node/presentation';
import {
  confirmationLatencyMessage,
  conflictsWithVisibilityTarget,
  estimateConfirmationLatency,
} from '#/views/ai-video/rule/confirmation-latency';

const emit = defineEmits<{ success: [] }>();
const router = useRouter();
const algorithm = ref<AiVideoAlgorithmApi.Algorithm>();
const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const fixedNode = ref(false);
const models = ref<ExecutableModelOption[]>([]);
const rules = ref<AiVideoRuleApi.Rule[]>([]);
const modelSlots = ref<
  Array<{ id: string; modelId: number; modelIds: number[] }>
>([]);
const bindings = ref<Record<string, number>>({});
const ready = ref(false);
const loading = ref(false);
const busy = ref(false);
const error = ref('');
const progress = ref('');
const createdId = ref<number>();
const savedNodeId = ref<number>();
const started = ref(false);
const sampleFps = ref(1);
const selectedStreamType = ref<'MAIN' | 'SUB'>('SUB');
const selectedRuleAst = ref<Record<string, unknown>>();
const latencyEstimate = computed(() =>
  estimateConfirmationLatency(selectedRuleAst.value, sampleFps.value),
);
const latencyConflict = computed(
  () =>
    algorithm.value?.eventType === 'PHONE_CALL' &&
    conflictsWithVisibilityTarget(latencyEstimate.value),
);
let generation = 0;
let configurationCode = '';
const validation = computed(
  () => algorithm.value?.pipelineAcceptanceStatus === 'PENDING',
);
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: '配置名称',
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'nodeId',
      label: '执行网关',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({
        disabled: fixedNode.value,
        showSearch: true,
        optionFilterProp: 'label',
        options: nodes.value.map((n) => ({
          value: n.id,
          label: `${n.name} · ${n.onlineStatus === 1 ? '在线' : '离线'}`,
          disabled: n.status !== 0 || n.onlineStatus !== 1,
        })),
      }),
    },
    {
      fieldName: 'cameraId',
      label: '摄像头',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({
        showSearch: true,
        optionFilterProp: 'label',
        options: cameras.value.map((c) => ({
          value: c.id,
          label: c.name,
          disabled: c.status !== 0,
        })),
      }),
    },
    {
      fieldName: 'streamType',
      label: '识别码流',
      component: 'Select',
      rules: 'required',
      help: '按摄像头已配置的主/子码流地址选取；预览会跟随正在运行的识别任务。',
      componentProps: {
        options: [
          { label: '子码流 · 负载较低', value: 'SUB' },
          { label: '主码流 · 适合远处小目标', value: 'MAIN' },
        ],
        onChange: (value: 'MAIN' | 'SUB') => {
          selectedStreamType.value = value;
        },
      },
    },
    {
      fieldName: 'ruleId',
      label: '告警规则',
      component: 'Select',
      componentProps: () => ({
        allowClear: true,
        onChange: (id?: number) => void selectRule(id),
        options: rules.value
          .filter((r) => r.eventType === algorithm.value?.eventType)
          .map((r) => ({ value: r.id, label: r.name })),
      }),
      help: '选择已发布规则；规则层是连续帧、持续时间、冷却和告警确认的唯一门槛。',
    },
    {
      fieldName: 'sampleFps',
      label: '每秒分析帧数',
      component: 'InputNumber',
      rules: 'required',
      componentProps: {
        min: 0.1,
        max: 30,
        step: 0.5,
        onChange: (value: number) => {
          sampleFps.value = Number(value);
        },
      },
    },
    {
      fieldName: 'confidence',
      label: '置信度阈值',
      component: 'InputNumber',
      rules: 'required',
      componentProps: { min: 0.01, max: 1, step: 0.05 },
    },
  ],
});
async function selectRule(id?: number) {
  selectedRuleAst.value = undefined;
  if (!id) return;
  const rule = rules.value.find((item) => item.id === id);
  const versions = await getRuleVersions(id);
  selectedRuleAst.value = versions.find(
    (item) => item.id === rule?.currentVersionId,
  )?.ast as unknown as Record<string, unknown> | undefined;
}
async function load() {
  const current = ++generation;
  modal.setState({ confirmDisabled: true });
  loading.value = true;
  ready.value = false;
  error.value = '';
  modelSlots.value = [];
  bindings.value = {};
  const data = modal.getData<{
    algorithmId: number;
    cameraId?: number;
    nodeId?: number;
  }>();
  fixedNode.value = !!data.nodeId;
  try {
    const [item, versions, options, gateways, ruleList] = await Promise.all([
      getAlgorithm(data.algorithmId),
      getPipelineVersions(data.algorithmId),
      getExecutableModelOptions(),
      getNodeSimpleList(),
      getPublishedRules(),
    ]);
    const cameraList: AiVideoCameraApi.Camera[] = [];
    for (let pageNo = 1; ; pageNo++) {
      const page = await getCameraPage({ pageNo, pageSize: 100, status: 0 });
      if (current !== generation) return;
      cameraList.push(...page.list);
      if (cameraList.length >= page.total || page.list.length === 0) break;
    }
    if (current !== generation) return;
    algorithm.value = item;
    models.value = options;
    nodes.value = gateways;
    rules.value = ruleList;
    cameras.value = cameraList;
    if (
      item.status !== 0 ||
      !['PASS', 'PENDING'].includes(item.pipelineAcceptanceStatus)
    )
      throw new Error('该算法尚未满足使用条件，请先完成发布或补齐依赖。');
    const pipeline = versions.find(
      (v) =>
        v.id === item.currentPipelineVersionId &&
        v.validationStatus === 'PUBLISHED',
    );
    if (!pipeline || !Array.isArray(pipeline.dag.nodes))
      throw new Error('没有可使用的已发布运行版本。');
    const types = new Set([
      'CLASSIFIER',
      'DETECTOR',
      'OCR',
      'POSE',
      'RECOGNIZER',
      'SEGMENTER',
    ]);
    modelSlots.value = pipeline.dag.nodes
      .filter((n) => types.has(String(n.type)))
      .map((n) => {
        const alternatives = Array.isArray(n.modelIds)
          ? n.modelIds
              .map((id: unknown) => Number(id))
              .filter((id: number) => Number.isSafeInteger(id) && id > 0)
          : [];
        const modelId = Number(
          n.modelId ?? alternatives[0] ?? item.defaultModelId,
        );
        return {
          id: String(n.id),
          modelId,
          modelIds: [...new Set([modelId, ...alternatives])],
        };
      });
    if (modelSlots.value.length === 0)
      throw new Error('该算法尚未配置识别模型。');
    for (const slot of modelSlots.value) {
      const choice = options.filter((o) => slot.modelIds.includes(o.modelId));
      // A target-specific model is never silently chosen for an arbitrary gateway.
      if (choice.length === 1) bindings.value[slot.id] = choice[0]!.id;
    }
    sampleFps.value = Number(item.defaultParameters.sampleFps ?? 1);
    selectedStreamType.value = 'SUB';
    await form.setValues({
      name: `${item.name}${validation.value ? '现场验证' : ''}`,
      nodeId: data.nodeId,
      cameraId: cameraList.find(
        (camera) => camera.id === data.cameraId && camera.status === 0,
      )?.id,
      sampleFps: sampleFps.value,
      streamType: selectedStreamType.value,
      confidence: item.defaultParameters.confidence ?? 0.5,
    });
    ready.value = true;
    modal.setState({
      title: `${item.name} · ${validation.value ? '现场验证' : '配置识别'}`,
      confirmDisabled: false,
      confirmText: validation.value ? '保存并开始验证' : '保存并启动识别',
    });
  } catch (cause) {
    if (current === generation)
      error.value =
        cause instanceof Error ? cause.message : '配置加载失败，请重试。';
  } finally {
    if (current === generation) loading.value = false;
  }
}
const [Modal, modal] = useVbenModal({
  title: '配置识别',
  class: 'w-[760px]',
  async onOpenChange(open) {
    if (!open) {
      generation++;
      return;
    }
    algorithm.value = undefined;
    createdId.value = undefined;
    started.value = false;
    savedNodeId.value = undefined;
    progress.value = '';
    configurationCode = `recognition-${crypto.randomUUID()}`;
    await form.resetForm();
    await load();
  },
  async onConfirm() {
    const formValidation = await form.validate();
    if (
      busy.value ||
      loading.value ||
      !ready.value ||
      !algorithm.value ||
      !formValidation.valid
    )
      return;
    if (started.value) {
      modal.close();
      return;
    }
    if (modelSlots.value.some((s) => !bindings.value[s.id])) {
      message.warning('请选择每项依赖的模型版本');
      return;
    }
    const values = await form.getValues();
    const rule = rules.value.find((r) => r.id === values.ruleId);
    if (algorithm.value.eventType && !rule) {
      message.warning('请选择与当前算法匹配的已发布告警规则');
      return;
    }
    if (latencyConflict.value && latencyEstimate.value) {
      message.warning(
        `${confirmationLatencyMessage(latencyEstimate.value)} 当前配置超过 2 秒目标，不能保存。`,
      );
      return;
    }
    busy.value = true;
    modal.lock();
    error.value = '';
    try {
      const nodeId = Number(values.nodeId);
      const ids = [...new Set(Object.values(bindings.value))];
      progress.value = '检查网关模型';
      const deployed = await getNodeModelDeployments(nodeId);
      for (const id of ids) {
        const latest = deployed
          .filter((d) => d.modelVersionId === id)
          .toSorted((a, b) => b.configVersion - a.configVersion)[0];
        if (latest?.actualStatus !== 'READY') {
          progress.value = '正在部署所需模型';
          await deployModelVersion(id, nodeId);
        }
      }
      for (let attempt = 0; ; attempt++) {
        const states = await getNodeModelDeployments(nodeId);
        const latest = ids.map(
          (id) =>
            states
              .filter((d) => d.modelVersionId === id)
              .toSorted((a, b) => b.configVersion - a.configVersion)[0],
        );
        if (latest.every((d) => d?.actualStatus === 'READY')) break;
        const failed = latest.find((d) => d?.actualStatus === 'FAILED');
        if (failed)
          throw new Error(
            failed.errorMessage || '模型部署失败，请检查网关模型状态',
          );
        if (attempt >= 90)
          throw new Error('模型仍在准备，请稍后重试；已部署模型会复用。');
        progress.value = '等待网关确认模型就绪';
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      progress.value = '保存配置';
      const payload: AiVideoTaskApi.TaskSave = {
        algorithmId: algorithm.value.id,
        pipelineVersionId: algorithm.value.currentPipelineVersionId,
        cameraId: Number(values.cameraId),
        nodeId,
        name: String(values.name),
        code: configurationCode,
        modelBindings: { ...bindings.value },
        modelVersionId: ids[0]!,
        ruleId: rule?.id,
        ruleVersionId: rule?.currentVersionId,
        parameters: {
          ...algorithm.value.defaultParameters,
          schemaVersion: '1.0',
          sampleFps: values.sampleFps,
          streamType: values.streamType,
          confidence: values.confidence,
          validationOnly: validation.value,
        },
      };
      if (createdId.value)
        await updateTask({ ...payload, id: createdId.value });
      else createdId.value = await createTask(payload);
      savedNodeId.value = nodeId;
      progress.value = '等待网关执行';
      await startTask(createdId.value);
      started.value = true;
      progress.value = '启动请求已提交，可到网关查看实际运行状态和画面。';
      modal.setState({ confirmText: '完成' });
      emit('success');
    } catch (cause) {
      error.value =
        cause instanceof Error ? cause.message : '配置失败，请检查后重试。';
    } finally {
      busy.value = false;
      modal.unlock();
    }
  },
});
function inspectGateway() {
  modal.close();
  void router.push(gatewayLocation(savedNodeId.value!, 'algorithms'));
}
</script>
<template>
  <Modal>
    <div class="space-y-4 p-2">
      <Alert
        v-if="validation"
        type="info"
        show-icon
        message="现场验证会在所选摄像头上运行识别，结果标记为现场验证；不会自动改为正式运行。"
      />
      <Alert
        v-if="loading"
        type="info"
        show-icon
        message="正在读取该算法的模型和配置选项…"
      />
      <Alert v-if="error" type="error" show-icon :message="error">
        <template #action>
          <Button v-if="!busy" @click="ready ? (error = '') : load()">
            重试
          </Button>
        </template>
      </Alert>
      <div v-show="!loading && algorithm && !started" :inert="busy">
        <Form />
        <Alert
          v-if="selectedStreamType === 'MAIN'"
          class="mb-4"
          type="warning"
          show-icon
          message="主码流会增加网关解码负载；同源实时预览要求主码流为 H.264。当前若为 H.265，识别可运行，但预览暂不可用。"
        />
        <Alert
          v-if="latencyEstimate"
          class="mb-4"
          show-icon
          :type="latencyConflict ? 'error' : 'info'"
          :message="confirmationLatencyMessage(latencyEstimate)"
          :description="
            latencyConflict
              ? '当前组合明显超过 2 秒目标，请提高分析帧率或降低规则连续帧/持续时间。'
              : '规则层是唯一告警确认门槛。'
          "
        />
        <div class="space-y-3 rounded-lg border p-4">
          <h4 class="font-medium">识别模型</h4>
          <div v-for="(slot, index) in modelSlots" :key="slot.id">
            <p class="mb-1 text-sm">模型 {{ index + 1 }}</p>
            <Select
              v-model:value="bindings[slot.id]"
              class="w-full"
              :disabled="busy"
              :options="
                models
                  .filter((m) => slot.modelIds.includes(m.modelId))
                  .map((m) => ({
                    value: m.id,
                    label: `${m.name} · ${modelExecutionLabel(m)} · ${m.version}`,
                  }))
              "
              placeholder="选择适用于目标网关的模型版本"
            />
            <Tag
              v-if="!models.some((m) => slot.modelIds.includes(m.modelId))"
              color="orange"
            >
              缺少已发布且可执行的模型，请先到模型中心完成测试和发布
            </Tag>
          </div>
        </div>
      </div>
      <Alert
        v-if="progress"
        :type="started ? 'success' : 'info'"
        :message="progress"
        show-icon
      />
      <Button v-if="savedNodeId && !busy" @click="inspectGateway">
        查看网关运行状态与画面
      </Button>
    </div>
  </Modal>
</template>
