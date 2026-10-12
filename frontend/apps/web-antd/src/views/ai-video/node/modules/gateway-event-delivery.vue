<script setup lang="ts">
import type {
  GatewayEventStreamStatus,
  GatewaySnapshot,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';

import { onBeforeUnmount, onMounted, ref } from 'vue';

import {
  Alert,
  Button,
  Descriptions,
  DescriptionsItem,
  message,
  Modal,
  Tag,
} from 'ant-design-vue';

import { $t } from '#/locales';

const props = defineProps<{
  canEdit: boolean;
  snapshot: GatewaySnapshot;
  transport: GatewayTransport;
}>();
const t = (key: string) => $t(`ai-video-delivery.${key}`);
const status = ref<GatewayEventStreamStatus>();
const key = ref('');
const error = ref('');
const saving = ref(false);
const protocolExample = `{"type":"challenge","version":"3.0","nonce":"…"}
{"type":"auth","hmac":"HMAC-SHA256(key, nonce) hex"}
{"type":"subscribe","taskIds":[],"eventTypes":[]}`;
const eventExample = JSON.stringify(
  {
    type: 'ai-video.event.created',
    version: '3.0',
    sourceEventId: '…',
    occurredAt: '2026-09-24T02:15:30.123+00:00',
    data: {
      eventType: 'AREA_INTRUSION',
      severity: 'MAJOR',
      taskId: 101,
      taskName: '禁入区域识别',
      algorithmId: 301,
      algorithmName: '区域入侵',
      cameraId: 201,
      cameraName: '东侧摄像头',
      location: { locationCode: 'ZONE-01', locationName: '作业一区' },
      result: {
        class: 'person',
        confidence: 0.95,
        bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.5 },
        trackId: 'person-1',
        attributes: {},
      },
      snapshot: {
        contentType: 'image/jpeg',
        url: 'http://<当前连接的盒子IP>:48901/event-images/…?expires=…&signature=…',
        sha256: '<图片字节SHA-256的64个小写十六进制字符>',
        expiresAt: '2026-09-24T03:15:30.123+00:00',
      },
    },
  },
  null,
  2,
);
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;
async function refresh() {
  try {
    const current = await props.transport<GatewayEventStreamStatus>(
      'event-stream.status',
    );
    if (!disposed) status.value = current;
    error.value = '';
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('loadFailed');
  }
}
async function poll() {
  await refresh();
  if (!disposed) timer = setTimeout(poll, 5000);
}
async function configure(enabled: boolean, rotateKey: boolean) {
  if (!status.value) return;
  saving.value = true;
  try {
    const result = await props.transport<GatewayEventStreamStatus>(
      'event-stream.configure',
      {
        enabled,
        rotateKey,
        expectedRevision: status.value.revision,
      },
    );
    status.value = result;
    if (result.key) key.value = result.key;
    message.success(t('saved'));
  } catch (cause) {
    error.value = cause instanceof Error ? cause.message : t('saveFailed');
  } finally {
    saving.value = false;
  }
}
function rotate() {
  Modal.confirm({
    title: t('rotateKey'),
    content: t('rotateWarning'),
    onOk: () => configure(!!status.value?.enabled, true),
  });
}
async function copyKey() {
  await navigator.clipboard.writeText(key.value);
  message.success(t('copied'));
}
onMounted(poll);
onBeforeUnmount(() => {
  disposed = true;
  clearTimeout(timer);
});
</script>

<template>
  <div class="space-y-4">
    <Alert v-if="error" type="error" show-icon :message="error" />
    <div class="flex flex-wrap justify-end gap-2">
      <Button @click="refresh">{{ t('refresh') }}</Button>
      <Button v-if="canEdit" :disabled="!status || saving" @click="rotate">{{
        t('rotateKey')
      }}</Button>
      <Button
        v-if="canEdit"
        type="primary"
        :loading="saving"
        :disabled="
          !status ||
          !status.listening ||
          !status.imageHttpEnabled ||
          (!status.enabled && status.revision === 0)
        "
        @click="configure(!status?.enabled, false)"
      >
        {{ status?.enabled ? t('disableStream') : t('enableStream') }}
      </Button>
    </div>
    <Descriptions v-if="status" bordered :column="2">
      <DescriptionsItem :label="t('status')">
        <Tag :color="status.enabled && status.listening ? 'green' : 'default'">
          {{
            status.enabled && status.listening ? t('enabled') : t('disabled')
          }}
        </Tag>
      </DescriptionsItem>
      <DescriptionsItem :label="t('tcpPort')">{{
        status.port
      }}</DescriptionsItem>
      <DescriptionsItem :label="t('connectedClients')">{{
        status.clients
      }}</DescriptionsItem>
      <DescriptionsItem :label="t('imageHttpPort')">{{
        status.imageHttpPort
      }}</DescriptionsItem>
    </Descriptions>
    <Alert
      v-if="!status?.listening"
      type="warning"
      show-icon
      :message="t('notListening')"
    />
    <Alert
      v-if="status && !status.imageHttpEnabled"
      type="warning"
      show-icon
      :message="t('imageHttpUnavailable')"
    />
    <Alert
      v-if="status?.revision === 0"
      type="info"
      show-icon
      :message="t('generateFirst')"
    />
    <Alert v-if="key" type="warning" show-icon :message="t('oneTimeKey')" />
    <div v-if="key" class="flex flex-wrap items-center gap-2">
      <code class="break-all rounded bg-muted px-3 py-2">{{ key }}</code>
      <Button @click="copyKey">{{ t('copyKey') }}</Button>
    </div>
    <div class="space-y-2 rounded border p-4">
      <h3 class="font-semibold">{{ t('subscriptionProtocol') }}</h3>
      <p>{{ t('protocolHint') }}</p>
      <pre class="overflow-x-auto rounded bg-muted p-3 text-xs">{{
        protocolExample
      }}</pre>
      <p>{{ t('liveHint') }}</p>
    </div>
    <div class="space-y-2 rounded border p-4">
      <h3 class="font-semibold">{{ t('eventFields') }}</h3>
      <p>{{ t('eventFieldsHint') }}</p>
      <pre class="overflow-x-auto rounded bg-muted p-3 text-xs">{{
        eventExample
      }}</pre>
    </div>
  </div>
</template>
