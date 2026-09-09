<script lang="ts" setup>
import { computed } from 'vue';

const props = withDefaults(defineProps<{
  label?: string;
  pulse?: boolean;
  size?: 'md' | 'sm';
  status?: number | string;
}>(), { label: '', pulse: false, size: 'md', status: 'UNKNOWN' });

const normalized = computed(() => String(props.status).toUpperCase());
const tone = computed(() => {
  if (['0', 'DISABLED', 'DRAFT', 'STOPPED', 'UNKNOWN'].includes(normalized.value)) return 'neutral';
  if (['1', 'ACTIVE', 'ENABLED', 'ONLINE', 'PASS', 'PUBLISHED', 'READY', 'RESOLVED', 'RUNNING', 'SUCCEEDED', 'VERIFIED'].includes(normalized.value)) return 'success';
  if (['2', 'CRITICAL', 'ERROR', 'FAILED', 'OFFLINE', 'REJECTED'].includes(normalized.value)) return 'danger';
  if (['ALARM', 'MAJOR', 'MINOR', 'RECONNECTING', 'STARTING', 'STOPPING', 'WARNING'].includes(normalized.value)) return 'warning';
  return 'info';
});
</script>

<template>
  <span class="ai-status" :class="[`ai-status--${tone}`, `ai-status--${size}`]">
    <span class="ai-status__dot" :class="[{ 'ai-status__dot--pulse': pulse && tone === 'success' }]"></span>
    <span>{{ label || status }}</span>
  </span>
</template>

<style scoped>
.ai-status { display: inline-flex; align-items: center; gap: 7px; color: hsl(var(--foreground)); white-space: nowrap; }
.ai-status--sm { font-size: 12px; }
.ai-status--md { font-size: 13px; font-weight: 500; }
.ai-status__dot { width: 7px; height: 7px; flex: 0 0 7px; background: var(--ai-neutral); border-radius: 999px; box-shadow: 0 0 0 3px rgb(100 116 139 / 10%); }
.ai-status--success .ai-status__dot { background: var(--ai-success); box-shadow: 0 0 0 3px rgb(22 163 74 / 10%); }
.ai-status--danger .ai-status__dot { background: var(--ai-danger); box-shadow: 0 0 0 3px rgb(220 38 38 / 10%); }
.ai-status--warning .ai-status__dot { background: var(--ai-warning); box-shadow: 0 0 0 3px rgb(217 119 6 / 10%); }
.ai-status--info .ai-status__dot { background: var(--ai-info); box-shadow: 0 0 0 3px rgb(37 99 235 / 10%); }
.ai-status__dot--pulse { animation: ai-status-pulse 1.8s ease-out infinite; }
@keyframes ai-status-pulse { 0%, 55%, 100% { box-shadow: 0 0 0 3px rgb(22 163 74 / 10%); } 30% { box-shadow: 0 0 0 6px rgb(22 163 74 / 0%); } }
@media (prefers-reduced-motion: reduce) { .ai-status__dot--pulse { animation: none; } }
</style>
