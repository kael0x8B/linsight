<script lang="ts" setup>
import { IconifyIcon } from '@vben/icons';

withDefaults(
  defineProps<{
    accent?: 'danger' | 'info' | 'neutral' | 'success' | 'warning';
    description?: string;
    emphasized?: boolean;
    icon?: string;
    label: string;
    suffix?: string;
    value?: number | string;
  }>(),
  {
    accent: 'neutral',
    description: '',
    emphasized: false,
    icon: 'lucide:activity',
    suffix: '',
    value: 0,
  },
);

defineEmits<{ select: [] }>();
</script>

<template>
  <button
    class="ai-metric-card"
    :class="[
      `ai-metric-card--${accent}`,
      { 'ai-metric-card--emphasized': emphasized },
    ]"
    type="button"
    @click="$emit('select')"
  >
    <span class="ai-metric-card__top">
      <span class="ai-metric-card__label">{{ label }}</span>
      <span class="ai-metric-card__icon"><IconifyIcon :icon="icon" /></span>
    </span>
    <span class="ai-metric-card__value"
      >{{ value }}<small v-if="suffix">{{ suffix }}</small></span
    >
    <span class="ai-metric-card__description">{{
      description || '暂无补充数据'
    }}</span>
  </button>
</template>

<style scoped>
.ai-metric-card {
  position: relative;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 124px;
  padding: 16px;
  color: inherit;
  text-align: left;
  cursor: pointer;
  background: hsl(var(--card));
  border: 1px solid hsl(var(--border) / 66%);
  border-radius: var(--ai-radius-lg);
  box-shadow: var(--ai-shadow-sm);
  transition:
    transform 150ms ease,
    border-color 150ms ease,
    box-shadow 150ms ease;
}

.ai-metric-card:hover {
  border-color: hsl(var(--primary) / 34%);
  box-shadow: var(--ai-shadow-md);
  transform: translateY(-1px);
}

.ai-metric-card:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 2px;
}

.ai-metric-card--emphasized {
  min-height: 140px;
  background: linear-gradient(
    145deg,
    hsl(var(--card)),
    hsl(var(--muted) / 45%)
  );
}

.ai-metric-card--danger {
  border-top: 2px solid var(--ai-danger);
}

.ai-metric-card--warning {
  border-top: 2px solid var(--ai-warning);
}

.ai-metric-card--success {
  border-top: 2px solid var(--ai-success);
}

.ai-metric-card--info {
  border-top: 2px solid var(--ai-info);
}

.ai-metric-card__top {
  display: flex;
  gap: 10px;
  align-items: center;
  justify-content: space-between;
}

.ai-metric-card__label {
  font-size: 12px;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.ai-metric-card__icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 50%);
  border-radius: 7px;
}

.ai-metric-card--danger .ai-metric-card__icon {
  color: var(--ai-danger);
  background: rgb(220 38 38 / 8%);
}

.ai-metric-card--warning .ai-metric-card__icon {
  color: var(--ai-warning);
  background: rgb(217 119 6 / 8%);
}

.ai-metric-card--success .ai-metric-card__icon {
  color: var(--ai-success);
  background: rgb(22 163 74 / 8%);
}

.ai-metric-card--info .ai-metric-card__icon {
  color: var(--ai-info);
  background: rgb(37 99 235 / 8%);
}

.ai-metric-card__value {
  margin-top: 10px;
  font-size: 29px;
  font-weight: 680;
  line-height: 1;
  color: hsl(var(--foreground));
  letter-spacing: -0.04em;
}

.ai-metric-card__value small {
  margin-left: 4px;
  font-size: 12px;
  font-weight: 500;
  color: hsl(var(--muted-foreground));
  letter-spacing: 0;
}

.ai-metric-card__description {
  padding-top: 10px;
  margin-top: auto;
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}
</style>
