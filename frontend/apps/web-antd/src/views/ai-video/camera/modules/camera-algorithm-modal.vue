<script lang="ts" setup>

import { gatewayLocation } from '#/views/ai-video/node/presentation';
const emit = defineEmits(['success']);
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, ref } from 'vue';

import { useAccess } from '@vben/access';
import { useVbenModal } from '@vben/common-ui';

import { Alert, Button, Checkbox, Descriptions, DescriptionsItem, Space, Spin, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getRunnableAlgorithms } from '#/api/ai-video/algorithm';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { getPublishedRules, getRuleVersions } from '#/api/ai-video/rule';
import { batchCreateTasks, getTaskPage } from '#/api/ai-video/task';
import { hasCustomRegions } from '#/components/ai-video/rule-regions';
import { $t } from '#/locales';
import { router } from '#/router';

import FaceConfig from './camera-face-config.vue';

const { hasAccessByCodes } = useAccess();
const t = (key: string) => $t(`page.aiVideo.cameraAlgorithms.${key}`);
const cameras = ref<Array<Pick<AiVideoCameraApi.Camera, 'id' | 'name'>>> ([]);
const algorithms = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const rules = ref<AiVideoRuleApi.Rule[]>([]);
const configs = ref<AiVideoTaskApi.Task[]>([]);
const algorithmId = ref<'ENTRY_FACE' | number>();
const faceIndex=ref(0);
const isFace=computed(()=>algorithmId.value==='ENTRY_FACE');
const canConfigureFace=computed(()=>hasAccessByCodes(['ai-video:task:update'])&&hasAccessByCodes(['ai-video:library:query']));
const source = ref<AiVideoTaskApi.Task>();
const ruleVersion = ref<AiVideoRuleApi.RuleVersion>();
const loading = ref(false);
const configLoading = ref(false);
const ruleLoading = ref(false);
const failed = ref(false);
const saving = ref(false);

const confirmedRegions = ref(false);
const results = ref<Array<AiVideoTaskApi.BatchResult & { startError?: string }>>([]);
let requestId = '';
let savedPayload: AiVideoTaskApi.BatchCreate | undefined;
let generation = 0;
let configGeneration = 0;
let ruleGeneration = 0;
const configPage = ref(1);
const configTotal = ref(0);
const node = computed(() => nodes.value.find((item) => item.id === source.value?.nodeId));
const rule = computed(() => rules.value.find((item) => item.id === source.value?.ruleId));
const hasRegions = computed(() => hasCustomRegions(ruleVersion.value?.ast.regions));
const canSave = computed(() => !!source.value && !loading.value && !failed.value && !configLoading.value && !ruleLoading.value && (!source.value.ruleId || !!ruleVersion.value) && (!hasRegions.value || confirmedRegions.value));
const startable = computed(() => results.value.filter((item) => item.status === 'CREATED' && ['DRAFT', 'FAILED', 'STOPPED'].includes(item.actualStatus ?? '')));

const [Form, formApi] = useVbenForm({
  commonConfig: { componentProps: { class: 'w-full' } },
  layout: 'vertical',
  showDefaultActions: false,
  schema: [
    { fieldName: 'algorithmId', label: t('algorithm'), component: 'Select', rules: 'required', componentProps: { showSearch: true, optionFilterProp: 'label', onChange: chooseAlgorithm } },
    { fieldName: 'sourceTaskId', label: t('configuration'), component: 'Select', rules: 'required', dependencies:{triggerFields:['algorithmId'],show:(values)=>values.algorithmId!=='ENTRY_FACE'}, componentProps: { showSearch: true, optionFilterProp: 'label', onChange: chooseSource } },
  ],
});
async function load() {
  const current = ++generation;
  loading.value = true;
  failed.value = false;
  try {
    const data = await Promise.all([getRunnableAlgorithms(), getNodeSimpleList(), getPublishedRules()]);
    if (current !== generation) return;
    [algorithms.value, nodes.value, rules.value] = data;
    formApi.updateSchema([{ fieldName: 'algorithmId', componentProps: { options: [...algorithms.value.map((item) => ({ label: item.name, value: item.id })),{label:$t('camera-face.algorithm'),value:'ENTRY_FACE'}] } }]);
    if (algorithmId.value && !isFace.value) {
      const sourceId = source.value?.id;
      await loadConfigs(false);
      if (sourceId) await chooseSource(sourceId);
    }
  } catch { if (current === generation) failed.value = true; }
  finally { if (current === generation) loading.value = false; }
}
async function chooseAlgorithm(id: 'ENTRY_FACE' | number) {
  algorithmId.value = id;configGeneration+=1;configLoading.value=false;
  configs.value = [];
  source.value = undefined;
  ruleVersion.value = undefined;
  ruleGeneration += 1;
  ruleLoading.value = false;
  confirmedRegions.value = false;
  configPage.value = 1;
  configTotal.value = 0;
  await formApi.setFieldValue('sourceTaskId', undefined, false);
  formApi.updateSchema([{ fieldName: 'sourceTaskId', componentProps: { options: [] } }]);
  if(id!=='ENTRY_FACE')await loadConfigs(false);
}
async function loadConfigs(more: boolean) {
  const current = ++configGeneration;
  configLoading.value = true;
  failed.value = false;
  try {
    const page = more ? configPage.value + 1 : 1;
    const data = await getTaskPage({ algorithmId: typeof algorithmId.value==='number'?algorithmId.value:undefined, pageNo: page, pageSize: 100 });
    if (current !== configGeneration) return;
    configs.value = more ? [...configs.value, ...data.list] : data.list;
    configPage.value = page;
    configTotal.value = data.total;
    formApi.updateSchema([{ fieldName: 'sourceTaskId', componentProps: {
      options: configs.value.map((item) => ({ label: `${item.name} · ${nodes.value.find((n) => n.id === item.nodeId)?.name ?? t('unknownNode')}`, value: item.id })),
    } }]);
    if (!more && data.list.length === 1) {
      await formApi.setFieldValue('sourceTaskId', data.list[0]!.id, false);
      await chooseSource(data.list[0]!.id);
    }
  } catch { if (current === configGeneration) failed.value = true; }
  finally { if (current === configGeneration) configLoading.value = false; }
}
async function chooseSource(id: number) {
  source.value = configs.value.find((item) => item.id === id);
  ruleVersion.value = undefined;
  confirmedRegions.value = false;
  const current = ++ruleGeneration;
  failed.value = false;
  ruleLoading.value = false;
  if (!source.value?.ruleId) return;
  const selected = source.value;
  ruleLoading.value = true;
  try {
    const versions = await getRuleVersions(selected.ruleId!);
    if (current !== ruleGeneration) return;
    ruleVersion.value = versions.find((item) => item.id === selected.ruleVersionId);
    if (!ruleVersion.value) failed.value = true;
  } catch { if (current === ruleGeneration) failed.value = true; }
  finally { if (current === ruleGeneration) ruleLoading.value = false; }
}
async function configureNew() {
  const ids = cameras.value.map((item) => item.id).join(',');
  await modalApi.close();
  await router.push({ path: '/ai-video/task', query: { create: '1', cameraIds: ids, algorithmId: algorithmId.value?.toString() } });
}
async function save() {
  if (!savedPayload) {
    const { valid } = await formApi.validate();
    if (!valid || !canSave.value || !source.value) return;
    const { algorithmId, pipelineVersionId, modelVersionId, modelBindings, nodeId, parameters, ruleId, ruleVersionId } = source.value;
    savedPayload = JSON.parse(JSON.stringify({ algorithmId, pipelineVersionId, modelVersionId, modelBindings, nodeId, parameters, ruleId, ruleVersionId,
      cameraIds: cameras.value.map((item) => item.id!), confirmSharedRegions: confirmedRegions.value, requestId,
    })) as AiVideoTaskApi.BatchCreate;
  }
  saving.value = true;
  failed.value = false;
  modalApi.lock();
  try {
    results.value = await batchCreateTasks(savedPayload);
    emit('success');
  } catch { failed.value = true; }
  finally { saving.value = false; modalApi.unlock(); }
}
async function refreshNodes() {
  loading.value = true;
  try { nodes.value = await getNodeSimpleList(); }
  finally { loading.value = false; }
}
function manageSaved() { if (node.value) { modalApi.close(); void router.push(gatewayLocation(node.value.id)); } }
const [Modal, modalApi] = useVbenModal({
  showConfirmButton: false,
  showCancelButton: false,
  async onOpenChange(open) {
    if (!open) { generation += 1; configGeneration += 1; ruleGeneration += 1; return; }
    const data = modalApi.getData<{ cameras: AiVideoCameraApi.Camera[] }>();
    cameras.value = (data?.cameras ?? []).map(({ id, name }) => ({ id, name }));
    results.value = [];
    source.value = undefined;
    savedPayload = undefined;
    requestId = crypto.randomUUID();
    algorithmId.value = undefined;faceIndex.value=0;
    configs.value = [];
    confirmedRegions.value = false;
    await formApi.resetForm();
    await load();
  },
});
</script>
<template>
  <Modal :title="t('add')" class="w-[700px]">
    <div class="space-y-4 p-1">
      <div class="rounded-lg bg-muted p-3">
        <strong>{{ $t('page.aiVideo.cameraAlgorithms.targets', { count: cameras.length }) }}</strong>
        <div class="mt-2 max-h-28 overflow-auto"><Tag v-for="camera in cameras" :key="camera.id" class="mb-1">{{ camera.name }}</Tag></div>
      </div>
      <Alert v-if="failed" type="error" show-icon :message="t('loadOrSaveFailed')" />
      <template v-if="!results.length">
        <Spin :spinning="loading || configLoading || ruleLoading">
          <fieldset :disabled="!!savedPayload" :class="{ 'pointer-events-none opacity-70': savedPayload }">
            <Form />
            <template v-if="isFace">
              <Alert v-if="!canConfigureFace" type="warning" :message="$t('camera-face.noPermission')" />
              <template v-else>
                <div v-if="cameras.length > 1" class="mb-4 space-y-2"><p>{{ $t('camera-face.multiHint') }}</p><Space><Button :disabled="faceIndex === 0" @click="faceIndex--">{{ $t('camera-face.previous') }}</Button><span>{{ faceIndex + 1 }} / {{ cameras.length }} · {{ cameras[faceIndex]?.name }}</span><Button :disabled="faceIndex === cameras.length - 1" @click="faceIndex++">{{ $t('camera-face.next') }}</Button></Space></div>
                <FaceConfig v-if="cameras[faceIndex]?.id" :key="cameras[faceIndex]?.id" :camera-id="cameras[faceIndex]!.id!" @success="emit('success')" />
              </template>
            </template>
            <template v-else>
            <p class="mb-3 text-xs text-muted-foreground">{{ t('configurationHint') }}</p>
            <Button v-if="configs.length < configTotal" size="small" class="mb-3" @click="loadConfigs(true)">{{ t('moreConfigurations') }}</Button>
            <Alert v-if="algorithmId && !configs.length && !configLoading && !failed" type="info" show-icon :message="t('firstConfiguration')" />
            <Descriptions v-if="source" bordered :column="2" size="small" class="my-4">
              <DescriptionsItem :label="t('node')" :span="2">{{ node?.name ?? t('unknownNode') }} <Tag :color="node?.onlineStatus === 1 ? 'green' : 'orange'">{{ t(node?.onlineStatus === 1 ? 'online' : 'offline') }}</Tag></DescriptionsItem>
              <DescriptionsItem :label="t('sampleRate')">{{ source.parameters.sampleFps ?? '—' }} FPS</DescriptionsItem>
              <DescriptionsItem :label="t('mode')">{{ t(source.parameters.validationOnly === true ? 'validation' : 'production') }}</DescriptionsItem>
              <DescriptionsItem :label="t('rule')" :span="2">{{ rule?.name ?? t('noRule') }}</DescriptionsItem>
              <DescriptionsItem :label="t('region')" :span="2">{{ hasRegions ? ruleVersion?.ast.regions.map((item) => item.name).join('、') : t('fullFrame') }}</DescriptionsItem>
            </Descriptions>
            <Alert v-if="source && node?.onlineStatus !== 1" class="mb-3" type="warning" show-icon :message="t('offlineSaveHint')" />
            <Alert v-if="hasRegions" class="mb-3" type="warning" show-icon :message="t('regionsHint')" />
            <Checkbox v-if="hasRegions" v-model:checked="confirmedRegions" class="mb-3">{{ t('confirmRegions') }}</Checkbox>
            </template>
          </fieldset>
        </Spin>
        <Button v-if="!savedPayload && !isFace" type="link" class="!px-0" @click="configureNew">{{ t('newConfiguration') }}</Button>
        <Alert v-if="!isFace" type="info" show-icon :message="t('saveHint')" />
        <p v-if="cameras.length > 1 && source" class="text-xs text-muted-foreground">{{ t('capacityHint') }}</p>
      </template>
      <template v-else>
        <div class="max-h-80 space-y-2 overflow-auto" aria-live="polite">
          <article v-for="item in results" :key="item.cameraId" class="rounded-lg border p-3">
            <div class="flex justify-between gap-2"><strong>{{ cameras.find((c) => c.id === item.cameraId)?.name }}</strong><Tag :color="item.status === 'FAILED' || item.startError ? 'red' : item.status === 'CREATED' ? 'green' : 'default'">{{ t(item.actualStatus === 'STARTING' && item.status === 'CREATED' ? 'queued' : item.status) }}</Tag></div>
            <p class="mt-1 text-xs text-muted-foreground">{{ item.startError || (item.actualStatus === 'STARTING' && item.status === 'CREATED' ? t('startSuccess') : item.message) }}</p>
          </article>
        </div>
        <p class="text-xs text-muted-foreground">{{ t('resultHint') }}</p>
        <Alert v-if="startable.length && node?.onlineStatus !== 1" type="warning" show-icon :message="t('offlineSaveHint')">
          <template #action><Button size="small" :loading="loading" @click="refreshNodes">{{ t('refreshNode') }}</Button></template>
        </Alert>
      </template>
    </div>
    <template #footer>
      <Space wrap>
        <Button :disabled="saving" @click="modalApi.close()">{{ t(results.length ? 'done' : 'cancel') }}</Button>
        <Button v-if="failed && !savedPayload" @click="load">{{ t('reload') }}</Button>
        <Button v-if="!isFace && (!results.length || results.some((item) => item.status === 'FAILED'))" type="primary" :loading="saving" :disabled="!savedPayload && !canSave" @click="save">{{ t(savedPayload ? 'retrySave' : 'save') }}</Button>
        <Button v-if="results.length && node" type="primary" @click="manageSaved">前往网关管理启停</Button>
      </Space>
    </template>
  </Modal>
</template>
