<script setup lang="ts">
import type { AiVideoModelApi } from '#/api/ai-video/model';
import type { AiVideoNode } from '#/api/ai-video/node';
import type { GatewaySnapshot } from '#/api/ai-video/node/gateway';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Empty, message, Select, Tag } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  deployModelVersion,
  getModelPage,
  getModelVersionList,
  getNodeModelDeployments,
  uninstallModelVersion,
} from '#/api/ai-video/model';
import { platformGateway } from '#/api/ai-video/node/gateway';

import { visibleModelVersionIds } from './model-inventory';

const props = defineProps<{ node: AiVideoNode }>();
const { hasAccessByCodes: can } = useAccess();
const busy = ref<number>();
const deployments = ref<AiVideoModelApi.ModelDeployment[]>([]);
const error = ref('');
const loading = ref(false);
const snapshot = ref<GatewaySnapshot>();
const liveSnapshotAvailable = ref(false);
const modelId = ref<number>();
const models = ref<AiVideoModelApi.Model[]>([]);
const versions = ref<AiVideoModelApi.ModelVersion[]>([]);
const installError = ref('');
const installing = ref(false);
let disposed = false;
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let versionGeneration = 0;
const names = computed(() => ({
  ...Object.fromEntries(
    deployments.value
      .filter((d) => d.modelName)
      .map((d) => [
        d.modelVersionId,
        { name: d.modelName!, version: d.modelVersion || '' },
      ]),
  ),
  ...snapshot.value?.names?.models,
}));
const installed = computed(() => snapshot.value?.models || []);
const latestDeployments = computed(() => [
  ...new Map(
    [...deployments.value]
      .toSorted((a, b) => a.configVersion - b.configVersion)
      .map((d) => [d.modelVersionId, d]),
  ).values(),
]);
const modelIds = computed(() =>
  visibleModelVersionIds(
    installed.value.map((model) => model.modelVersionId),
    latestDeployments.value,
    liveSnapshotAvailable.value,
  ),
);
const statusLabels: Record<string, string> = {
  QUEUED: '等待安装',
  DOWNLOADING: '下载中',
  VERIFYING: '校验中',
  LOADING: '加载中',
  RUNNING: '处理中',
  READY: '已安装',
  REMOVING: '卸载中',
  REMOVED: '已卸载',
  FAILED: '操作失败',
};
function deployment(id: number) {
  return latestDeployments.value.find((d) => d.modelVersionId === id);
}
function isInstalled(id: number) {
  return installed.value.some((model) => model.modelVersionId === id);
}
function statusLabel(id: number) {
  if (isInstalled(id)) return '已安装';
  return statusLabels[deployment(id)?.actualStatus || ''] || '状态待确认';
}
function statusColor(id: number) {
  if (isInstalled(id)) return 'green';
  return deployment(id)?.actualStatus === 'FAILED' ? 'red' : 'blue';
}
function inUse(id: number) {
  return snapshot.value?.tasks.some(
    (t) =>
      t.enabled &&
      (t.config.modelVersionId === id ||
        Object.values(t.config.modelBindings).includes(id)),
  );
}
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'versionId',
      label: '模型版本',
      component: 'Select',
      rules: 'required',
      componentProps: () => ({
        options: versions.value
          .filter(
            (v) =>
              v.publishStatus === 'PUBLISHED' &&
              v.validationStatus === 'VERIFIED',
          )
          .map((v) => ({
            label: `${v.version} · ${v.artifactFormat}`,
            value: v.id,
          })),
      }),
    },
  ],
});
const [InstallModal, modal] = useVbenModal({
  title: '安装模型到当前网关',
  onConfirm: install,
  onClosed: () => {
    versionGeneration++;
    versions.value = [];
    modelId.value = undefined;
  },
});
async function refresh(quiet = false) {
  clearTimeout(timer);
  const expected = ++generation;
  if (!quiet) loading.value = true;
  const results = await Promise.allSettled([
    platformGateway<GatewaySnapshot>(props.node.id, 'snapshot'),
    getNodeModelDeployments(props.node.id),
  ]);
  if (disposed || expected !== generation) return;
  const central = results[1];
  const local = results[0];
  liveSnapshotAvailable.value = local.status === 'fulfilled';
  if (local.status === 'fulfilled') snapshot.value = local.value;
  if (central.status === 'fulfilled') deployments.value = central.value;
  error.value = '';
  if (local.status === 'rejected')
    error.value = '网关暂不可达，已安装模型显示上次读取结果。';
  else if (central.status === 'rejected')
    error.value = '部署状态读取失败，请重试。';
  loading.value = false;
  timer = setTimeout(() => void refresh(true), 5000);
}
async function openInstall() {
  installError.value = '';
  modal.open();
  installing.value = true;
  try {
    const all: AiVideoModelApi.Model[] = [];
    for (let pageNo = 1; ; pageNo++) {
      const page = await getModelPage({ pageNo, pageSize: 100, status: 0 });
      all.push(...page.list);
      if (pageNo * 100 >= page.total || page.list.length === 0) break;
    }
    models.value = all;
  } catch {
    installError.value = '模型目录加载失败，请关闭后重试。';
  } finally {
    installing.value = false;
  }
}
async function selectModel(id: number) {
  modelId.value = id;
  const expected = ++versionGeneration;
  versions.value = [];
  await form.setValues({ versionId: undefined });
  installing.value = true;
  installError.value = '';
  try {
    const result = await getModelVersionList(id);
    if (expected === versionGeneration) versions.value = result;
  } catch {
    if (expected === versionGeneration)
      installError.value = '版本加载失败，请重新选择模型。';
  } finally {
    if (expected === versionGeneration) installing.value = false;
  }
}
async function install() {
  const validation = await form.validate();
  if (installing.value || !validation.valid) return;
  modal.lock();
  try {
    const values = await form.getValues();
    await deployModelVersion(Number(values.versionId), props.node.id);
    message.success('安装任务已提交，可在当前页查看结果');
    modal.close();
    await refresh();
  } catch (error) {
    installError.value =
      error instanceof Error ? error.message : '安装提交失败';
  } finally {
    modal.unlock();
  }
}
async function uninstall(id: number) {
  try {
    await confirm(
      `从“${props.node.name}”卸载“${names.value[id]?.name || `模型 #${id}`}”？只删除当前网关上的模型文件，平台模型资产和其他网关不受影响。关联任务再次启动前需要重新安装。`,
    );
  } catch {
    return;
  }
  busy.value = id;
  try {
    await (deployment(id)
      ? uninstallModelVersion(id, props.node.id)
      : platformGateway(props.node.id, 'model.uninstall', {
          modelVersionId: id,
          sha256: installed.value.find((m) => m.modelVersionId === id)?.sha256,
          requestId: crypto.randomUUID(),
        }));
    message.success('卸载已提交，网关会校验模型占用情况');
    await refresh();
  } catch (error) {
    message.error(error instanceof Error ? error.message : '卸载失败');
  } finally {
    busy.value = undefined;
  }
}
onMounted(() => void refresh());
onBeforeUnmount(() => {
  disposed = true;
  generation++;
  versionGeneration++;
  clearTimeout(timer);
});
</script>
<template>
  <div class="mb-4 flex flex-wrap justify-between gap-3">
    <div>
      <h3 class="text-base font-semibold">模型管理</h3>
      <p class="mt-1 text-sm text-muted-foreground">
        安装提供识别能力；算法是否运行，在“识别算法”中统一控制。
      </p>
    </div>
    <div class="flex gap-2">
      <Button :loading="loading" @click="refresh()">刷新</Button
      ><Button
        v-if="can(['ai-video:model:deploy'])"
        type="primary"
        :disabled="node.onlineStatus !== 1"
        @click="openInstall"
      >
        安装模型
      </Button>
    </div>
  </div>
  <Alert v-if="error" class="mb-4" :message="error" type="warning" show-icon />
  <Alert
    v-if="snapshot && !snapshot.capabilities?.includes('model.uninstall.v1')"
    class="mb-4"
    message="当前网关版本暂不支持卸载；在顶部“在线升级”完成更新后即可使用。"
    type="info"
    show-icon
  />
  <div class="grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
    <article
      v-for="id in modelIds"
      :key="id"
      class="flex flex-col rounded-xl border bg-card p-5"
    >
      <div class="flex items-start justify-between gap-3">
        <h4 class="font-semibold">{{ names[id]?.name || `模型 #${id}` }}</h4>
        <Tag :color="statusColor(id)">
          {{ statusLabel(id) }}
        </Tag>
      </div>
      <p class="mt-2 text-xs text-muted-foreground">
        {{ names[id]?.version || `版本编号 #${id}` }}
      </p>
      <div class="my-4 flex gap-2">
        <Tag>
          {{
            installed.find((m) => m.modelVersionId === id)?.artifactFormat ||
            '格式待上报'
          }} </Tag
        ><Tag>
          {{
            installed.find((m) => m.modelVersionId === id)?.device ||
            '设备待上报'
          }} </Tag
        ><Tag v-if="inUse(id)" color="blue">算法使用中</Tag>
      </div>
      <Alert
        v-if="deployment(id)?.errorMessage"
        class="mb-3"
        type="warning"
        :message="deployment(id)?.errorMessage"
      />
      <details class="mb-4 text-xs text-muted-foreground">
        <summary class="cursor-pointer">模型校验信息</summary>
        <p class="mt-2 break-all">
          SHA256
          {{
            installed.find((m) => m.modelVersionId === id)?.sha256 || '尚未上报'
          }}
        </p>
      </details>
      <div class="mt-auto flex justify-end gap-2 border-t pt-4">
        <Button
          v-if="
            can(['ai-video:model:deploy']) &&
            deployment(id)?.actualStatus === 'FAILED'
          "
          size="small"
          @click="openInstall"
        >
          重新安装 </Button
        ><Button
          v-if="can(['ai-video:model:deploy'])"
          danger
          size="small"
          :loading="busy === id"
          :disabled="
            !!error ||
            busy !== undefined ||
            node.onlineStatus !== 1 ||
            inUse(id) ||
            !snapshot?.capabilities?.includes('model.uninstall.v1') ||
            (deployment(id)
              ? !['READY', 'FAILED'].includes(
                  deployment(id)?.actualStatus || '',
                )
              : !can(['ai-video:node:operate']))
          "
          @click="uninstall(id)"
        >
          卸载
        </Button>
      </div>
    </article>
  </div>
  <Empty
    v-if="!modelIds.length && !loading"
    description="当前网关尚未安装模型"
  />
  <InstallModal
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
    class="ai-dialog"
  >
    <p class="mb-4 text-sm">
      安装目标：<strong>{{ node.name }}</strong> · {{ node.ipAddress }}
    </p>
    <Alert
      v-if="installError"
      class="mb-3"
      type="error"
      :message="installError"
    /><label class="mb-2 block">选择平台模型</label
    ><Select
      :value="modelId"
      show-search
      option-filter-prop="label"
      class="mb-4 w-full"
      :loading="installing"
      :options="models.map((m) => ({ label: m.name, value: m.id }))"
      @change="(value) => selectModel(Number(value))"
    /><Form />
    <p class="text-xs text-muted-foreground">
      仅展示已发布并通过格式校验的版本。执行端会检查硬件与模型兼容性。
    </p>
  </InstallModal>
</template>
