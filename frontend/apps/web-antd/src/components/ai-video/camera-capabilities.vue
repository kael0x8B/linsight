<script lang="ts" setup>
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { Tag } from 'ant-design-vue';

import { $t } from '#/locales';

const props = defineProps<{
  capabilities?: AiVideoCameraApi.CameraCapability[];
  selectable?: boolean;
  selectedId?: number | string;
}>();
const emit = defineEmits<{
  select: [capability: AiVideoCameraApi.CameraCapability];
}>();
function capabilityId(capability: AiVideoCameraApi.CameraCapability) {
  return capability.entryAccessId
    ? `entry-${capability.entryAccessId}`
    : capability.taskId;
}
function select(capability: AiVideoCameraApi.CameraCapability) {
  if (props.selectable) emit('select', capability);
}

function statusColor(status: string) {
  if (status === 'RUNNING') return 'green';
  if (['FAILED', 'OFFLINE'].includes(status)) return 'red';
  if (['STALE', 'STARTING', 'STOPPING'].includes(status)) return 'orange';
  return 'default';
}
function statusLabel(status: string) {
  const known = [
    'RUNNING',
    'STOPPED',
    'DRAFT',
    'FAILED',
    'OFFLINE',
    'STALE',
    'STARTING',
    'STOPPING',
  ];
  return known.includes(status)
    ? $t(`page.aiVideo.recognition.status.${status}`)
    : status;
}
</script>

<template>
  <div class="capabilities">
    <p v-if="capabilities === undefined" class="capabilities__empty">
      {{ $t('page.aiVideo.recognition.unavailable') }}
    </p>
    <p v-else-if="!capabilities.length" class="capabilities__empty">
      {{ $t('page.aiVideo.recognition.empty') }}
    </p>
    <article
      v-for="capability in capabilities"
      :key="capabilityId(capability) ?? undefined"
      class="capability"
      :class="{
        'capability--selectable': selectable,
        'capability--selected':
          selectable && selectedId === capabilityId(capability),
      }"
      :role="selectable ? 'button' : undefined"
      :tabindex="selectable ? 0 : undefined"
      :aria-pressed="
        selectable ? selectedId === capabilityId(capability) : undefined
      "
      :aria-label="
        selectable
          ? `查看${capability.algorithmName || capability.taskName}`
          : undefined
      "
      @click="select(capability)"
      @keydown.enter="select(capability)"
      @keydown.space="
        selectable && $event.preventDefault();
        select(capability);
      "
    >
      <header>
        <strong>{{ capability.algorithmName || capability.taskName }}</strong>
        <Tag :color="statusColor(capability.effectiveStatus)">
{{
          capability.stationState === 'NO_REFERENCE'
            ? $t('camera-face.needsReferences')
            : statusLabel(capability.effectiveStatus)
        }}
</Tag>
      </header>
      <div class="capability__detail">
        {{ capability.taskName }} ·
        {{ capability.nodeName || `#${capability.nodeId}` }}
      </div>
      <Tag v-if="capability.validationOnly" color="orange">
{{
        $t('page.aiVideo.recognition.validationOnly')
      }}
</Tag>
      <div
        v-if="
          !capability.entryAccessId && capability.effectiveStatus === 'RUNNING'
        "
        class="capability__metrics"
      >
        <Tag
          v-if="capability.executionBackend"
          :color="capability.executionBackend === 'RKNPU' ? 'blue' : 'default'"
          >
{{
            capability.executionBackend === 'RKNPU'
              ? 'NPU 加速'
              : capability.executionBackend === 'CPU'
                ? 'CPU 分析'
                : capability.executionBackend === 'CPU+RKNPU'
                  ? 'CPU + NPU'
                  : '等待分析'
          }}
</Tag>
        <span>{{ $t('page.aiVideo.recognition.analysisRate') }}
          {{ capability.analysisFps?.toFixed(2) ?? '—' }} FPS</span>
        <span>{{ $t('page.aiVideo.recognition.latency') }}
          {{
            capability.totalLatencyMillis == null
              ? '—'
              : (capability.totalLatencyMillis / 1000).toFixed(2)
          }}
          s</span>
      </div>
      <p
        v-if="
          capability.effectiveStatus === 'STALE' &&
          capability.stationState !== 'NO_REFERENCE'
        "
        class="capability__detail"
      >
        {{ $t('page.aiVideo.recognition.staleTask') }}
      </p>
      <p v-if="capability.stationState" class="capability__detail">
        {{ $t(`entry-access.stationStates.${capability.stationState}`) }}
      </p>
      <p
        v-if="capability.desiredStatus === 'STOPPED' && capability.errorCode"
        class="capability__error"
      >
        {{ $t('camera-face.stopFailed') }}
        {{
          capability.errorMessage?.includes('gateway configuration changed')
            ? $t('camera-face.revisionConflict')
            : capability.errorMessage
        }}
      </p>
      <slot name="actions" :capability="capability"></slot>
    </article>
  </div>
</template>

<style scoped>
.capabilities {
  display: grid;
  gap: 12px;
}
.capability {
  padding: 12px;
  border: 1px solid hsl(var(--border));
  border-radius: 8px;
  background: hsl(var(--card));
}
.capability--selectable {
  cursor: pointer;
  transition:
    border-color 150ms,
    background 150ms;
}
.capability--selectable:hover {
  border-color: hsl(var(--primary) / 45%);
  background: hsl(var(--muted) / 40%);
}
.capability--selectable:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}
.capability--selected {
  border-color: hsl(var(--primary));
  background: hsl(var(--primary) / 5%);
  box-shadow: inset 3px 0 hsl(var(--primary));
}
.capability--selectable .capability__detail {
  line-height: 1.6;
}
.capability--selectable :deep(.ant-tag) {
  margin-inline-end: 0;
  flex-shrink: 0;
}
.capability__error {
  color: #dc2626;
  margin-top: 8px;
  font-size: 12px;
}
.capability header {
  display: flex;
  gap: 6px;
  align-items: flex-start;
  justify-content: space-between;
}
.capability header strong {
  font-size: 13px;
}
.capability__detail,
.capabilities__empty {
  margin: 7px 0;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
}
.capability__metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 6px;
  font-size: 12px;
}
</style>
