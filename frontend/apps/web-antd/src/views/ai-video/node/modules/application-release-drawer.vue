<script setup lang="ts">
import type { VxeTableGridOptions } from '#/adapter/vxe-table';
import type {
  ApplicationRelease,
  ReleaseBuildConfiguration,
} from '#/api/ai-video/node/application-release';

import { computed, onBeforeUnmount, ref } from 'vue';

import { useVbenDrawer, useVbenModal } from '@vben/common-ui';
import { formatDateTime } from '@vben/utils';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  message,
  Tag,
} from 'ant-design-vue';

import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import {
  getReleaseConfiguration,
  getReleaseDownloadUrl,
  getReleasePage,
  retryRelease,
} from '#/api/ai-video/node/application-release';
import { $t } from '#/locales';

import CreateModal from './release-create-modal.vue';

const configuration = ref<ReleaseBuildConfiguration>();
const configurationLoading = ref(false);
const error = ref('');
const details = ref<ApplicationRelease>();
const canGenerate = computed(
  () => !configurationLoading.value && configuration.value?.ready === true,
);
const busy = ref(false);
let active = false;
let generation = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
const [Create, createApi] = useVbenModal({
  connectedComponent: CreateModal,
  destroyOnClose: true,
});
const [Details, detailsApi] = useVbenModal({ footer: false });
const [Drawer] = useVbenDrawer({
  async onOpenChange(open) {
    active = open;
    generation++;
    clearTimeout(timer);
    if (open) {
      const current = generation;
      configuration.value = undefined;
      configurationLoading.value = true;
      error.value = '';
      try {
        const result = await getReleaseConfiguration();
        if (current !== generation) return;
        configuration.value = result;
        await gridApi.query();
      } catch {
        if (current === generation) error.value = $t('box-release.loadError');
      } finally {
        if (current === generation) configurationLoading.value = false;
      }
    }
  },
});
onBeforeUnmount(() => {
  active = false;
  generation++;
  clearTimeout(timer);
});
const [Grid, gridApi] = useVbenVxeGrid<ApplicationRelease>({
  gridOptions: {
    autoResize: true,
    height: 'auto',
    proxyConfig: {
      autoLoad: false,
      ajax: {
        query: async ({ page }) => {
          clearTimeout(timer);
          const current = generation;
          try {
            // A toolbar refresh can recover an initial configuration-load failure too.
            const build =
              configuration.value ?? (await getReleaseConfiguration());
            const result = await getReleasePage({
              pageNo: page.currentPage,
              pageSize: page.pageSize,
            });
            if (current === generation) {
              configuration.value = build;
              error.value = '';
              if (
                active &&
                result.list.some((row) =>
                  ['BUILDING', 'QUEUED', 'STORING'].includes(row.status),
                )
              ) {
                timer = setTimeout(() => {
                  if (active) void gridApi.query();
                }, 5000);
              }
            }
            return result;
          } catch (failure) {
            if (current === generation)
              error.value = $t('box-release.loadError');
            throw failure;
          }
        },
      },
    },
    columns: [
      { field: 'version', title: $t('box-release.version'), minWidth: 145 },
      {
        field: 'profileLabel',
        title: $t('box-release.package'),
        minWidth: 170,
      },
      {
        field: 'status',
        title: $t('box-release.status'),
        width: 120,
        slots: { default: 'status' },
      },
      {
        field: 'message',
        title: $t('box-release.progress'),
        minWidth: 270,
        showOverflow: 'tooltip',
      },
      {
        field: 'createTime',
        title: $t('box-release.createdAt'),
        width: 170,
        formatter: ({ cellValue }) => formatDateTime(cellValue),
      },
      {
        field: 'actions',
        title: $t('box-release.actions'),
        width: 180,
        fixed: 'right',
        slots: { default: 'actions' },
      },
    ],
    rowConfig: { keyField: 'id', isHover: true },
    pagerConfig: { pageSize: 10 },
    toolbarConfig: { refresh: true },
  } as VxeTableGridOptions<ApplicationRelease>,
});
async function refresh() {
  await gridApi.query();
}
function showDetails(row: ApplicationRelease) {
  details.value = row;
  detailsApi.open();
}
async function retry(row: ApplicationRelease) {
  if (busy.value) return;
  busy.value = true;
  try {
    await retryRelease(row.id);
    message.success($t('box-release.queued'));
    await refresh();
  } finally {
    busy.value = false;
  }
}
async function download(
  row: ApplicationRelease,
  artifact: 'bootstrap' | 'bundle' | 'public-key',
) {
  if (busy.value) return;
  busy.value = true;
  try {
    const url = await getReleaseDownloadUrl(row.id, artifact);
    // Let the browser stream the file; do not buffer the entire offline bundle in JavaScript.
    const link = document.createElement('a');
    link.href = url;
    link.download =
      artifact === 'bundle'
        ? row.fileName || ''
        : artifact === 'bootstrap'
          ? 'linsight-bootstrap.pyz'
          : 'release-public.pem';
    link.rel = 'noopener';
    document.body.append(link);
    link.click();
    link.remove();
  } finally {
    busy.value = false;
  }
}
</script>
<template>
  <Drawer
    :title="$t('box-release.title')"
    class="w-[1160px] max-w-[100vw]"
    :footer="false"
  >
    <Create @success="refresh" />
    <div class="flex h-full min-h-0 flex-col gap-4">
      <Alert
        v-if="!configurationLoading && configuration && !configuration.ready"
        :message="$t('box-release.notConfigured')"
        type="warning"
        show-icon
      />
      <Alert v-if="error" :message="error" type="error" show-icon />
      <Grid class="min-h-0 flex-1">
        <template #toolbar-actions>
          <Button
            type="primary"
            :disabled="!canGenerate"
            :loading="configurationLoading"
            @click="createApi.setData({ configuration }).open()"
            >{{ $t('box-release.generate') }}</Button
          >
        </template>
        <template #status="{ row }">
          <Tag
            :color="
              row.status === 'SUCCEEDED'
                ? 'green'
                : row.status === 'FAILED'
                  ? 'red'
                  : 'blue'
            "
            >{{ $t(`box-release.states.${row.status}`) }}</Tag
          >
        </template>
        <template #actions="{ row }">
          <TableAction
            :actions="[
              {
                label: $t('box-release.details'),
                type: 'link',
                onClick: () => showDetails(row),
              },
              {
                label: $t('box-release.download'),
                type: 'link',
                ifShow: row.status === 'SUCCEEDED',
                disabled: busy,
                onClick: () => download(row, 'bundle'),
              },
              {
                label: $t('box-release.retry'),
                type: 'link',
                ifShow: row.status === 'FAILED',
                disabled: busy,
                onClick: () => retry(row),
              },
            ]"
          />
        </template>
      </Grid>
    </div>
    <Details
      :title="$t('box-release.details')"
      class="ai-dialog w-[740px] max-w-[calc(100vw-2rem)]"
      content-class="ai-dialog-content"
      footer-class="ai-dialog-footer"
    >
      <Descriptions v-if="details" bordered :column="1" size="small">
        <DescriptionsItem :label="$t('box-release.version')">{{
          details.version
        }}</DescriptionsItem>
        <DescriptionsItem :label="$t('box-release.package')"
          >{{ details.profileLabel }} ·
          {{ details.architecture }}</DescriptionsItem
        >
        <DescriptionsItem :label="$t('box-release.supportedDevices')">{{
          details.devices.toUpperCase()
        }}</DescriptionsItem>
        <DescriptionsItem :label="$t('box-release.notes')"
          ><span class="whitespace-pre-wrap">{{
            details.notes || '—'
          }}</span></DescriptionsItem
        >
        <DescriptionsItem :label="$t('box-release.progress')">{{
          details.message
        }}</DescriptionsItem>
        <DescriptionsItem :label="$t('box-release.keyId')">{{
          details.keyId
        }}</DescriptionsItem>
        <template v-if="details.status === 'SUCCEEDED'">
          <DescriptionsItem :label="$t('box-release.size')"
            >{{
              ((details.size || 0) / 1024 / 1024).toFixed(1)
            }}
            MiB</DescriptionsItem
          >
          <DescriptionsItem label="SHA-256"
            ><code class="break-all">{{
              details.sha256
            }}</code></DescriptionsItem
          >
          <DescriptionsItem :label="$t('box-release.sourceDigest')"
            ><code class="break-all">{{
              details.sourceSha256
            }}</code></DescriptionsItem
          >
          <DescriptionsItem :label="$t('box-release.bootstrapDigest')"
            ><code class="break-all">{{
              details.bootstrapSha256
            }}</code></DescriptionsItem
          >
        </template>
      </Descriptions>
      <div
        v-if="details?.status === 'SUCCEEDED'"
        class="mt-4 flex flex-wrap gap-2"
      >
        <Button
          type="primary"
          :loading="busy"
          @click="download(details, 'bundle')"
          >{{ $t('box-release.download') }}</Button
        >
        <Button :disabled="busy" @click="download(details, 'bootstrap')">{{
          $t('box-release.bootstrap')
        }}</Button>
        <Button :disabled="busy" @click="download(details, 'public-key')">{{
          $t('box-release.publicKey')
        }}</Button>
      </div>
    </Details>
  </Drawer>
</template>
