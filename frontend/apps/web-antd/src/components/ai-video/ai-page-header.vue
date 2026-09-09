<script lang="ts" setup>
import { IconifyIcon } from '@vben/icons';

import { Tag } from 'ant-design-vue';

withDefaults(defineProps<{
  description?: string;
  eyebrow?: string;
  icon?: string;
  status?: string;
  statusColor?: string;
  title: string;
}>(), {
  description: '',
  eyebrow: 'LINSIGHT CONSOLE',
  icon: 'lucide:scan-eye',
  status: '',
  statusColor: 'blue',
});
</script>

<template>
  <header class="ai-page-header">
    <div class="ai-page-header__identity">
      <span class="ai-page-header__icon" aria-hidden="true"><IconifyIcon :icon="icon" /></span>
      <div class="min-w-0">
        <div class="ai-page-header__eyebrow">{{ eyebrow }}</div>
        <div class="ai-page-header__title-row">
          <h1>{{ title }}</h1>
          <Tag v-if="status" :color="statusColor">{{ status }}</Tag>
        </div>
        <p v-if="description">{{ description }}</p>
      </div>
    </div>
    <div v-if="$slots.extra" class="ai-page-header__extra"><slot name="extra"></slot></div>
  </header>
</template>

<style scoped>
.ai-page-header { display: flex; min-height: 76px; align-items: center; justify-content: space-between; gap: 24px; padding: 2px 2px 4px; }
.ai-page-header__identity { display: flex; min-width: 0; align-items: center; gap: 12px; }
.ai-page-header__icon { display: inline-flex; width: 40px; height: 40px; flex: 0 0 40px; align-items: center; justify-content: center; color: #2563eb; font-size: 20px; background: rgb(37 99 235 / 9%); border: 1px solid rgb(37 99 235 / 14%); border-radius: 10px; }
.ai-page-header__eyebrow { margin-bottom: 2px; color: hsl(var(--muted-foreground)); font-size: 10px; font-weight: 700; letter-spacing: 0.12em; }
.ai-page-header__title-row { display: flex; align-items: center; gap: 10px; }
h1 { margin: 0; color: hsl(var(--foreground)); font-size: clamp(20px, 1.7vw, 24px); font-weight: 650; letter-spacing: -0.035em; line-height: 1.25; }
p { max-width: 860px; margin: 4px 0 0; color: hsl(var(--muted-foreground)); font-size: 13px; line-height: 1.55; }
.ai-page-header__extra { display: flex; flex: 0 0 auto; align-items: center; }
@media (width <= 900px) { .ai-page-header { align-items: flex-start; flex-direction: column; gap: 12px; } }
</style>
