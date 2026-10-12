<script setup lang="ts">
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type {
  AlgorithmPackage,
  PackageResolution,
} from '#/api/ai-video/algorithm/package';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, ref, watch } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenModal } from '@vben/common-ui';

import { Alert, Button, message, Select, TabPane, Tabs } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getRunnableAlgorithms } from '#/api/ai-video/algorithm';
import {
  listAlgorithmPackages,
  resolveAlgorithmPackage,
} from '#/api/ai-video/algorithm/package';
import { getCameraPage } from '#/api/ai-video/camera';
import {
  deployModelVersion,
  getNodeModelDeployments,
} from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { gatewayRequestId, platformGateway } from '#/api/ai-video/node/gateway';
import {
  createRule,
  getPublishedRules,
  getRuleVersions,
  publishRuleVersion,
  saveRuleVersion,
  validateRuleVersion,
} from '#/api/ai-video/rule';
import { createTask, startTask, updateTask } from '#/api/ai-video/task';
import { $t } from '#/locales';

import { modelExecutionLabel } from '../../model/execution-presentation';
import GatewayRuleEditor from '../../node/modules/gateway-rule-editor.vue';
import {
  confirmationLatencyMessage,
  conflictsWithVisibilityTarget,
  estimateConfirmationLatency,
} from '../../rule/confirmation-latency';
import {
  packageBindings,
  packageDeploymentSummary,
} from './package-deployment';
import PackageParameters from './package-parameters.vue';

const emit = defineEmits<{
  selectPipeline: [algorithmId: number, nodeId?: number, cameraId?: number];
  success: [];
}>();
const { hasAccessByCodes: can } = useAccess();
const rules = ref<AiVideoRuleApi.Rule[]>([]);
const packages = ref<AlgorithmPackage[]>([]);
const pipelines = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const cameras = ref<AiVideoCameraApi.Camera[]>([]);
const gateways = ref<AiVideoNodeSimple[]>([]);
const fixedNode = ref(false);
const nodeId = ref(0);
const nodeName = ref('');
const selected = ref<AlgorithmPackage>();
const runtimeSupported = ref(false);
const resolution = ref<PackageResolution>();
const bindings = ref<Record<string, number>>({});
const cameraId = ref<number>();
const phase = ref('');
const failure = ref('');
const busy = ref(false);
const catalogLoaded = ref(false);
const existing = ref<AiVideoTaskApi.Task>();
const createdId = ref<number>();
const parameters = ref<InstanceType<typeof PackageParameters>>();
let generation = 0;
let configurationCode = '';
const summary = computed(() =>
  selected.value && resolution.value
    ? packageDeploymentSummary(
        selected.value.manifest,
        resolution.value,
        bindings.value,
      )
    : undefined,
);
const permissionBlocked = computed(
  () =>
    !can(['ai-video:task:start']) ||
    !can([
      existing.value || createdId.value
        ? 'ai-video:task:update'
        : 'ai-video:task:create',
    ]) ||
    (!!summary.value?.toInstall && !can(['ai-video:model:deploy'])),
);
const camera = computed(() =>
  cameras.value.find((c) => c.id === cameraId.value),
);
const ruleCamera = computed(() =>
  camera.value?.id ? { ...camera.value, id: camera.value.id } : undefined,
);
const ruleText = ref('');
const ownedRuleId = ref<number>();
const ownedRuleVersionId = ref<number>();
const savedRuleText = ref('');
const activeTab = ref('basic');
const ruleEditor = ref<InstanceType<typeof GatewayRuleEditor>>();
const sampleFps = ref(2);
const selectedStreamType = ref<'MAIN' | 'SUB'>('SUB');
const parsedRule = computed<Record<string, unknown> | undefined>(() => {
  try {
    return ruleText.value ? JSON.parse(ruleText.value) : undefined;
  } catch {
    return undefined;
  }
});
const latencyEstimate = computed(() =>
  estimateConfirmationLatency(parsedRule.value, sampleFps.value),
);
const latencyConflict = computed(
  () =>
    selected.value?.manifest.eventType === 'PHONE_CALL' &&
    conflictsWithVisibilityTarget(latencyEstimate.value),
);
const latencyBlocked = computed(
  () =>
    latencyConflict.value &&
    (!existing.value ||
      sampleFps.value !== Number(existing.value.parameters.sampleFps) ||
      ruleText.value !== savedRuleText.value),
);
async function loadRule(id?: number) {
  if (!id) {
    ruleText.value = '';
    return;
  }
  const versions = await getRuleVersions(id);
  const published = versions.find(
    (v) =>
      v.id ===
      (existing.value?.ruleId === id
        ? existing.value.ruleVersionId
        : rules.value.find((r) => r.id === id)?.currentVersionId),
  );
  if (published) ruleText.value = JSON.stringify(published.ast, null, 2);
}
const initial = computed(
  () =>
    existing.value?.parameters.algorithm as Record<string, unknown> | undefined,
);
const statisticsOnly = computed(
  () => selected.value?.manifest.outputMode === 'STATISTICS',
);
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'nodeId',
      label: '执行网关',
      component: 'Select',
      rules: 'required',
      dependencies: { triggerFields: [''], show: () => !fixedNode.value },
      componentProps: () => ({
        disabled: fixedNode.value,
        options: gateways.value.map((n) => ({
          value: n.id,
          label: `${n.name} · ${n.onlineStatus === 1 ? '在线' : '离线'}`,
          disabled: n.status !== 0 || n.onlineStatus !== 1,
        })),
        onChange: (id: number) => {
          nodeId.value = id;
          nodeName.value = gateways.value.find((n) => n.id === id)?.name ?? '';
          if (selected.value)
            void selectPackage(selected.value.pipelineVersionId);
        },
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
          label: c.name,
          value: c.id,
          disabled: c.status !== 0,
        })),
        onChange: (id: number) => {
          cameraId.value = id;
        },
      }),
    },
    {
      fieldName: 'packageId',
      label: '识别算法',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({
        showSearch: true,
        optionFilterProp: 'searchText',
        options: [
          ...pipelines.value.map((algorithm) => ({
            label: `${algorithm.name} · 内置编排`,
            searchText: `${algorithm.name} ${algorithm.eventType === 'VEHICLE_PLATE_RECOGNIZED' ? '车牌 车号' : ''}`,
            value: -algorithm.id,
          })),
          ...packages.value
            .filter(
              (p) =>
                p.status === 'PUBLISHED' &&
                (existing.value
                  ? p.algorithmId === existing.value.algorithmId
                  : p.current),
            )
            .map((p) => ({
              label: existing.value
                ? `${p.manifest.name} · v${p.manifest.version}${p.current ? ' · 最新' : ''}`
                : p.manifest.name,
              searchText: p.manifest.name,
              value: p.pipelineVersionId,
            })),
        ],
        onChange: (id: number) => {
          if (id > 0) {
            void selectPackage(id);
            return;
          }
          const algorithm = pipelines.value.find((item) => item.id === -id);
          if (!algorithm) return;
          modal.close();
          emit(
            'selectPipeline',
            algorithm.id,
            nodeId.value || undefined,
            cameraId.value,
          );
        },
      }),
    },
  ],
});
const [AdvancedForm, advancedForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'name',
      label: '配置名称',
      component: 'Input',
      rules: 'required',
    },
    {
      fieldName: 'sampleFps',
      label: '分析帧率',
      component: 'InputNumber',
      rules: 'required',
      componentProps: {
        min: 0.1,
        max: 10,
        step: 0.5,
        onChange: (value: number) => {
          sampleFps.value = Number(value);
        },
      },
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
      fieldName: 'confidence',
      label: '模型置信度',
      component: 'InputNumber',
      rules: 'required',
      help: '模型输出的最低置信度，算法专用阈值在识别参数中设置。',
      componentProps: { min: 0.01, max: 1, step: 0.05 },
    },
  ],
});
const [TemplateForm, templateForm] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'ruleId',
      label: '复制告警模板',
      component: 'Select',
      help: '可选。复制后在“告警条件”调整，只影响本次配置。',
      componentProps: () => ({
        allowClear: true,
        onChange: (id?: number) => void loadRule(id),
        options: rules.value
          .filter(
            (r) =>
              r.eventType ===
              (selected.value?.manifest.eventType ?? 'ALGORITHM_EVENT'),
          )
          .map((r) => ({ label: r.name, value: r.id })),
      }),
    },
  ],
});
async function selectPackage(id: number) {
  const current = ++generation;
  failure.value = '';
  resolution.value = undefined;
  bindings.value = {};
  phase.value = '';
  runtimeSupported.value = false;
  const changed = selected.value?.pipelineVersionId !== id;
  selected.value = packages.value.find((p) => p.pipelineVersionId === id);
  if (selected.value && changed && !existing.value) {
    ruleText.value = selected.value.manifest.defaultRule
      ? JSON.stringify(selected.value.manifest.defaultRule, null, 2)
      : '';
    await advancedForm.setFieldValue('name', selected.value.manifest.name);
    await templateForm.setFieldValue('ruleId', undefined);
  }
  if (!selected.value || !nodeId.value) return;
  const gateway = gateways.value.find((item) => item.id === nodeId.value);
  if (!gateway || gateway.status !== 0 || gateway.onlineStatus !== 1) {
    failure.value = $t('algorithm-deployment.offline');
    return;
  }
  phase.value = '正在匹配当前网关的模型';
  try {
    const value = await resolveAlgorithmPackage(id, nodeId.value);
    if (generation !== current) return;
    const requirements = value.manifest.runtimeRequirements ?? [];
    if (requirements.length > 0) {
      const snapshot = await platformGateway<{ capabilities?: string[] }>(
        nodeId.value,
        'snapshot',
      );
      if (generation !== current) return;
      runtimeSupported.value = requirements.every((item) =>
        snapshot.capabilities?.includes(item),
      );
      if (!runtimeSupported.value)
        failure.value =
          '当前网关需在线升级后才能运行此版本；暂时无法确认身份时，新版会暂停判定。';
    } else runtimeSupported.value = true;
    resolution.value = value;
    bindings.value = packageBindings(value, existing.value?.modelBindings);
  } catch {
    if (current === generation)
      failure.value = '模型依赖匹配失败，请重选算法或检查网关状态。';
  } finally {
    if (current === generation) phase.value = '';
  }
}
const [Modal, modal] = useVbenModal({
  title: '配置识别',
  confirmText: $t('algorithm-deployment.deploy'),
  class: 'w-[800px]',
  async onOpenChange(open) {
    if (!open) {
      generation++;
      selected.value = undefined;
      resolution.value = undefined;
      return;
    }
    const data = modal.getData<{
      nodeId?: number;
      nodeName?: string;
      pipelineVersionId?: number;
      task?: AiVideoTaskApi.Task;
    }>();
    const current = ++generation;
    fixedNode.value = !!data.nodeId;
    nodeId.value = data.nodeId ?? 0;
    nodeName.value = data.nodeName ?? '';
    existing.value = data.task;
    createdId.value = data.task?.id;
    configurationCode = data.task?.code ?? `pkg-${gatewayRequestId()}`;
    failure.value = '';
    catalogLoaded.value = false;
    packages.value = [];
    pipelines.value = [];
    phase.value = '';
    activeTab.value = 'basic';
    ruleText.value = '';
    ownedRuleId.value = undefined;
    ownedRuleVersionId.value = undefined;
    savedRuleText.value = '';
    await form.resetForm();
    await advancedForm.resetForm();
    await templateForm.resetForm();
    try {
      phase.value = '正在加载配置选项';
      const [ruleList, packageList, nodeList, runnable] = await Promise.all([
        getPublishedRules(),
        listAlgorithmPackages(),
        getNodeSimpleList(),
        getRunnableAlgorithms(),
      ]);
      if (current !== generation) return;
      rules.value = ruleList;
      packages.value = packageList.filter(
        (p) =>
          p.algorithmId === data.task?.algorithmId ||
          runnable.some((a) => a.id === p.algorithmId),
      );
      pipelines.value = data.task
        ? []
        : runnable.filter(
            (algorithm) =>
              algorithm.status === 0 &&
              !!algorithm.currentPipelineVersionId &&
              ['PASS', 'PENDING'].includes(
                algorithm.pipelineAcceptanceStatus,
              ) &&
              !algorithm.capabilityKey?.startsWith('package.'),
          );
      gateways.value = nodeList;
      cameras.value = [];
      for (let pageNo = 1; ; pageNo++) {
        const page = await getCameraPage({ pageNo, pageSize: 100 });
        if (current !== generation) return;
        cameras.value.push(...page.list);
        if (cameras.value.length >= page.total || page.list.length === 0) break;
      }
      if (current !== generation) return;
      catalogLoaded.value = true;
      const enabledCameras = cameras.value.filter((item) => item.status === 0);
      cameraId.value =
        data.task?.cameraId ??
        (enabledCameras.length === 1 ? enabledCameras[0]?.id : undefined);
      const pipelineId = data.task?.pipelineVersionId ?? data.pipelineVersionId;
      const preset = packages.value.find(
        (p) => p.pipelineVersionId === pipelineId,
      );
      sampleFps.value = Number(data.task?.parameters.sampleFps ?? 2);
      selectedStreamType.value =
        data.task?.parameters.streamType === 'MAIN' ? 'MAIN' : 'SUB';
      await form.setValues({
        nodeId: data.nodeId,
        cameraId: cameraId.value,
        packageId: pipelineId,
      });
      await advancedForm.setValues({
        sampleFps: sampleFps.value,
        streamType: selectedStreamType.value,
        confidence: data.task?.parameters.confidence ?? 0.5,
        name: data.task?.name ?? preset?.manifest.name,
      });
      await templateForm.setFieldValue('ruleId', data.task?.ruleId);
      if (pipelineId) await selectPackage(pipelineId);
      if (data.task?.ruleId) {
        await loadRule(data.task.ruleId);
        savedRuleText.value = ruleText.value;
      }
      phase.value = '';
    } catch {
      if (current === generation) {
        phase.value = '';
        failure.value = '配置目录加载失败，请关闭后重试。';
      }
    }
  },
  async onConfirm() {
    const validation = await form.validate();
    if (busy.value || !validation.valid) return;
    if (permissionBlocked.value) {
      message.warning($t('algorithm-deployment.noPermission'));
      return;
    }
    const advancedValidation = await advancedForm.validate();
    if (!advancedValidation.valid) {
      activeTab.value = 'advanced';
      return;
    }
    if (!selected.value || !resolution.value) {
      message.warning('请先选择网关和算法，等待模型匹配完成');
      return;
    }
    if (existing.value?.actualStatus === 'RUNNING') {
      message.warning('请先停止该配置，再修改算法参数');
      return;
    }
    if (!runtimeSupported.value) {
      message.warning('请先在线升级当前网关，再选择此算法版本');
      return;
    }
    if (!resolution.value.supported) {
      message.warning('请先在线升级当前网关，以支持算法包');
      return;
    }
    if (statisticsOnly.value) ruleText.value = '';
    if (ruleEditor.value && !ruleEditor.value.validate()) {
      activeTab.value = 'rule';
      return;
    }
    const basic = {
      ...(await form.getValues()),
      ...(await advancedForm.getValues()),
    };
    if (latencyBlocked.value && latencyEstimate.value) {
      message.warning(
        `${confirmationLatencyMessage(latencyEstimate.value)} 当前配置超过 2 秒目标，不能保存。`,
      );
      activeTab.value = 'advanced';
      return;
    }
    const config = await parameters.value?.values();
    if (!config) {
      activeTab.value = 'advanced';
      message.warning($t('algorithm-deployment.parametersRequired'));
      return;
    }
    if (summary.value?.missing.length) {
      message.warning($t('algorithm-deployment.resourcesMissing'));
      return;
    }
    busy.value = true;
    modal.lock();
    failure.value = '';
    try {
      const ids = [...new Set(Object.values(bindings.value))];
      const installed = await getNodeModelDeployments(nodeId.value);
      for (const id of ids) {
        const latest = installed
          .filter((d) => d.modelVersionId === id)
          .toSorted((a, b) => b.configVersion - a.configVersion)[0];
        if (latest?.actualStatus !== 'READY') {
          phase.value = '正在安装识别所需模型';
          await deployModelVersion(id, nodeId.value);
        }
      }
      for (let attempt = 0; ; attempt++) {
        const deployments = await getNodeModelDeployments(nodeId.value);
        const latest = ids.map(
          (id) =>
            deployments
              .filter((d) => d.modelVersionId === id)
              .toSorted((a, b) => b.configVersion - a.configVersion)[0],
        );
        if (latest.every((d) => d?.actualStatus === 'READY')) break;
        const failed = latest.find((d) => d?.actualStatus === 'FAILED');
        if (failed)
          throw new Error(
            failed.errorMessage || '模型安装失败，请查看网关模型管理',
          );
        if (attempt >= 90)
          throw new Error('模型仍在安装，可稍后重试，已完成的安装会复用');
        phase.value = '等待网关确认模型就绪';
        await new Promise((resolve) => setTimeout(resolve, 2000));
      }
      phase.value = '正在保存并下发算法包';
      // Copy a template into an immutable rule version owned by this configuration.
      // Retain IDs on retry so a delayed model/task command cannot duplicate rules.
      if (ruleText.value && savedRuleText.value !== ruleText.value) {
        if (!ownedRuleId.value)
          ownedRuleId.value = await createRule({
            name: `${String(basic.name)} · 告警条件`,
            code: `task-rule-${gatewayRequestId()}`,
            eventType: selected.value.manifest.eventType ?? 'ALGORITHM_EVENT',
            status: 0,
            description: '网关识别配置的告警条件；其他配置不随本次修改变化。',
          });
        ownedRuleVersionId.value = await saveRuleVersion(
          ownedRuleId.value,
          JSON.parse(ruleText.value),
        );
        const errors = await validateRuleVersion(ownedRuleVersionId.value);
        if (errors.length > 0) throw new Error(errors.join('；'));
        await publishRuleVersion(ownedRuleVersionId.value);
        savedRuleText.value = ruleText.value;
      }
      const payload: AiVideoTaskApi.TaskSave = {
        ...existing.value,
        name: String(basic.name),
        code: configurationCode,
        cameraId: Number(basic.cameraId),
        nodeId: nodeId.value,
        algorithmId: selected.value.algorithmId,
        pipelineVersionId: selected.value.pipelineVersionId,
        modelVersionId: ids[0]!,
        modelBindings: bindings.value,
        ruleId: ruleText.value
          ? (ownedRuleId.value ?? existing.value?.ruleId)
          : undefined,
        ruleVersionId: ruleText.value
          ? (ownedRuleVersionId.value ?? existing.value?.ruleVersionId)
          : undefined,
        parameters: {
          schemaVersion: '1.0',
          inputWidth: 640,
          inputHeight: 640,
          nmsThreshold: 0.5,
          ...existing.value?.parameters,
          sampleFps: Number(basic.sampleFps),
          streamType: basic.streamType,
          confidence: Number(basic.confidence),
          algorithm: config,
        },
      };
      if (createdId.value)
        await updateTask({ ...payload, id: createdId.value });
      else createdId.value = await createTask(payload);
      await startTask(createdId.value);
      await modal.close();
      emit('success');
      message.success('配置已保存，等待网关确认识别状态');
    } catch (error) {
      failure.value =
        error instanceof Error
          ? error.message
          : '配置未完成，请检查依赖状态后重试';
    } finally {
      phase.value = '';
      busy.value = false;
      modal.unlock();
    }
  },
});
watch(
  () => [
    phase.value,
    busy.value,
    resolution.value,
    runtimeSupported.value,
    summary.value?.missing.length,
    permissionBlocked.value,
  ],
  () =>
    modal.setState({
      confirmDisabled:
        !!phase.value ||
        busy.value ||
        !resolution.value?.supported ||
        !runtimeSupported.value ||
        !!summary.value?.missing.length ||
        permissionBlocked.value,
    }),
  { immediate: true },
);
</script>
<template>
  <Modal
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
    class="ai-dialog w-[800px]"
  >
    <div class="ai-workflow">
      <Alert v-if="phase" :message="phase" type="info" show-icon /><Alert
        v-if="failure"
        :message="failure"
        type="error"
        show-icon
      />
      <Alert
        v-if="permissionBlocked"
        :message="$t('algorithm-deployment.noPermission')"
        type="warning"
        show-icon
      />
      <Alert
        v-if="resolution && !resolution.supported"
        message="当前网关需先在线升级，才能安装算法包。"
        type="warning"
        show-icon
      />
      <p v-if="statisticsOnly" class="ai-form-note">
        统计区域内当前人数，在实时画面显示结果；无需人员库，不生成离岗告警。各摄像头分别统计。
      </p>
      <Alert
        v-if="latencyEstimate && latencyConflict"
        :type="latencyBlocked ? 'error' : 'info'"
        show-icon
        :message="confirmationLatencyMessage(latencyEstimate)"
        :description="
          latencyBlocked
            ? '接打电话配置明显超过 2 秒目标，请提高分析帧率或降低规则连续帧/持续时间。'
            : latencyConflict
              ? '这是保持兼容的历史配置；可继续运行和修改无关参数，变更规则或帧率时必须满足 2 秒目标。'
              : '规则层是唯一告警确认门槛。'
        "
      />
      <p v-else-if="latencyEstimate" class="ai-form-note">
        {{ confirmationLatencyMessage(latencyEstimate) }}
      </p>
      <Tabs v-model:active-key="activeTab">
        <TabPane
          key="basic"
          :tab="$t('algorithm-deployment.basic')"
          force-render
        >
          <p class="mb-4 text-sm text-muted-foreground">
            {{ $t('algorithm-deployment.intro') }}
          </p>
          <p v-if="fixedNode" class="mb-4 font-medium">{{ nodeName }}</p>
          <Form />
          <Alert
            v-if="
              catalogLoaded &&
              !gateways.some(
                (item) => item.status === 0 && item.onlineStatus === 1,
              )
            "
            class="mb-3"
            type="warning"
            show-icon
            :message="$t('algorithm-deployment.offline')"
          />
          <Alert
            v-if="catalogLoaded && !cameras.some((item) => item.status === 0)"
            class="mb-3"
            type="warning"
            show-icon
            :message="$t('algorithm-deployment.noCamera')"
          />
          <Alert
            v-if="
              catalogLoaded &&
              !pipelines.length &&
              !packages.some(
                (item) => item.status === 'PUBLISHED' && item.current,
              )
            "
            class="mb-3"
            type="warning"
            show-icon
            :message="$t('algorithm-deployment.noAlgorithm')"
          />
          <template v-if="summary && resolution">
            <Alert
              v-for="role in summary.missing"
              :key="role.slot"
              type="warning"
              show-icon
              class="mb-3"
              :message="`${role.name || role.slot}：${resolution.blockers?.[role.slot] || $t('algorithm-deployment.resourcesMissing')}`"
            />
            <Alert
              v-if="!summary.missing.length"
              type="success"
              show-icon
              :message="$t('algorithm-deployment.matched')"
              :description="
                $t('algorithm-deployment.summary', {
                  installed: summary.installed,
                  pending: summary.toInstall,
                })
              "
            />
            <p class="mt-3 text-sm text-muted-foreground">
              {{
                ruleText
                  ? $t('algorithm-deployment.withRule')
                  : $t('algorithm-deployment.withoutRule')
              }}
            </p>
          </template>
          <Button
            v-if="selected"
            type="link"
            class="mt-3 !px-0"
            @click="activeTab = 'advanced'"
            >{{ $t('algorithm-deployment.customize') }}</Button
          >
        </TabPane>
        <TabPane
          key="advanced"
          :tab="$t('algorithm-deployment.advanced')"
          force-render
        >
          <AdvancedForm />
          <Alert
            v-if="selectedStreamType === 'MAIN'"
            class="mb-4"
            type="warning"
            show-icon
            message="主码流会增加网关解码负载，请确认使用 H.264 编码。"
          />
          <div
            v-if="selected && resolution"
            class="space-y-4 rounded-lg border p-4"
          >
            <h4 class="font-semibold">匹配的识别模型</h4>
            <div v-for="role in selected.manifest.models" :key="role.slot">
              <p class="mb-2">{{ role.name || role.slot }}</p>
              <Select
                v-model:value="bindings[role.slot]"
                class="w-full"
                :options="
                  (resolution.roles[role.slot] ?? []).map((m) => ({
                    value: m.id,
                    label: `${m.name} · ${modelExecutionLabel(m)} · ${m.installed ? '已安装' : '需要安装'} · ${m.version}`,
                    disabled: m.deployable === false,
                    title: m.reason,
                  }))
                "
              />
            </div>
          </div>
          <PackageParameters
            v-if="selected"
            ref="parameters"
            :manifest="selected.manifest"
            :initial="initial"
            :camera="camera"
            :node-id="nodeId"
            class="mt-4"
          />
          <p v-else class="py-4 text-muted-foreground">先选择识别算法</p>
        </TabPane>
        <TabPane v-if="!statisticsOnly" key="rule" tab="告警条件" force-render>
          <div
            v-show="
              rules.some((r) => r.eventType === selected?.manifest.eventType)
            "
          >
            <TemplateForm />
          </div>
          <GatewayRuleEditor
            v-if="selected"
            :key="selected.pipelineVersionId"
            ref="ruleEditor"
            v-model="ruleText"
            :camera="ruleCamera"
            :node-id="nodeId"
            :event-type="selected.manifest.eventType"
            :default-rule="selected.manifest.defaultRule"
          />
        </TabPane>
      </Tabs>
    </div>
  </Modal>
</template>
