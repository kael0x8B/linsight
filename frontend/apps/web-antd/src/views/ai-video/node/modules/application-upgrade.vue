<script setup lang="ts">
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { ApplicationUpgradeStatus } from './application-upgrade';

import type { GatewayTransport } from '#/api/ai-video/node/gateway';

import { computed, onBeforeUnmount, onMounted, ref } from 'vue';

import { confirm } from '@vben/common-ui';

import { Alert, Button, Descriptions, DescriptionsItem, Progress, Upload } from 'ant-design-vue';

import { gatewayRequestId } from '#/api/ai-video/node/gateway';
import { $t } from '#/locales';

import { upgradeBusy, uploadApplication } from './application-upgrade';

const props = defineProps<{ transport: GatewayTransport }>();
const status = ref<ApplicationUpgradeStatus>();
const error = ref('');
const connectionError = ref('');
const loading = ref(false);
const uploading = ref(false);
const percent = ref(0);
const t = (key: string) => $t(`application-upgrade.${key}`);
const busy = computed(() => uploading.value || loading.value || upgradeBusy(status.value?.job?.phase));
let timer: ReturnType<typeof setTimeout> | undefined;
let alive = true;
let refreshing = false;
let uploadId = '';
let selectedIdentity = '';

async function refresh() {
  if (refreshing || !alive) return;
  refreshing = true;
  try {
    const value = await props.transport<ApplicationUpgradeStatus>('app-upgrade.status');
    if (alive) { status.value = value; connectionError.value = ''; }
  } catch (cause) {
    if (alive) connectionError.value = cause instanceof Error ? cause.message : t('reconnecting');
  } finally {
    refreshing = false;
    if (alive) timer = setTimeout(refresh, 3000);
  }
}

async function choose(file: FileType) {
  if (busy.value) return Upload.LIST_IGNORE;
  const identity = `${file.name}:${file.size}:${file.lastModified}`;
  if (selectedIdentity !== identity || (status.value?.job?.id === uploadId
    && ['FAILED', 'RECOVERY_FAILED', 'ROLLED_BACK', 'SUCCEEDED'].includes(status.value.job.phase))) {
    selectedIdentity = identity;
    uploadId = gatewayRequestId();
  }
  uploading.value = true;
  percent.value = 0;
  error.value = '';
  try {
    await uploadApplication(file, uploadId, props.transport, (value) => { percent.value = value; }, () => !alive);
  } catch (cause) {
    if (alive) error.value = cause instanceof Error && cause.message !== 'INVALID_PACKAGE'
      ? cause.message : t('invalidPackage');
  } finally {
    uploading.value = false;
    // Polling keeps installation independent from the lifecycle of this component.
  }
  return Upload.LIST_IGNORE;
}

async function install() {
  const job = status.value?.job;
  if (!job || job.phase !== 'READY' || busy.value) return;
  try {
    await confirm({ title: t('install'), content: t('impact') });
  } catch { return; }
  error.value = '';
  loading.value = true;
  try {
    await props.transport('app-upgrade.install', { id: job.id });
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('reconnecting');
  } finally { loading.value = false; }
}

async function rollback() {
  try {
    await confirm({ title: t('rollback'), content: t('rollbackImpact') });
  } catch { return; }
  error.value = '';
  loading.value = true;
  try {
    await props.transport('app-upgrade.rollback', { id: gatewayRequestId() });
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('reconnecting');
  } finally { loading.value = false; }
}

onMounted(refresh);
onBeforeUnmount(() => { alive = false; if (timer) clearTimeout(timer); });
</script>

<template>
  <div class="space-y-4 p-4">
    <Alert v-if="connectionError" type="warning" show-icon :message="connectionError" />
    <Alert v-if="status?.lastError" type="error" show-icon :message="status.lastError.message" />
    <Alert v-if="error" type="error" show-icon :message="error" :description="t('retryHint')" />
    <Alert v-if="status && !status.supported" type="warning" show-icon :message="t('migrationRequired')" />
    <Descriptions v-if="status?.supported" bordered :column="1" size="small">
      <DescriptionsItem :label="t('current')">{{ status.current?.version }}</DescriptionsItem>
      <DescriptionsItem v-if="status.job" :label="t('target')">{{ status.job.version || '—' }}</DescriptionsItem>
      <DescriptionsItem v-if="status.job" :label="t('status')">{{ t(`phase.${status.job.phase}`) }}</DescriptionsItem>
      <DescriptionsItem v-if="status.job" :label="t('result')">{{ status.job.message }}</DescriptionsItem>
      <DescriptionsItem v-if="status.job?.notes" :label="t('notes')"><span class="whitespace-pre-wrap">{{ status.job.notes }}</span></DescriptionsItem>
    </Descriptions>
    <div v-if="status?.supported" class="flex flex-wrap items-center gap-3">
      <Upload accept=".lup" :before-upload="choose" :show-upload-list="false" :disabled="busy">
        <Button :loading="uploading" :disabled="busy">{{ t('upload') }}</Button>
      </Upload>
      <Button type="primary" :disabled="busy || status.job?.phase !== 'READY'" @click="install">{{ t('install') }}</Button>
      <Button :disabled="busy || !status.rollbackAvailable" @click="rollback">{{ t('rollback') }}</Button>
    </div>
    <Progress v-if="uploading" :percent="percent" />
    <p v-if="!status && !connectionError" class="text-muted-foreground">{{ t('loading') }}</p>
  </div>
</template>
