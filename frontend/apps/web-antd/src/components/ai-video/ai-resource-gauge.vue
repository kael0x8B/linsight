<script lang="ts" setup>
import { computed } from 'vue';

const props = defineProps<{ label: string; value?: null | number }>();
const available = computed(() => props.value !== null && props.value !== undefined && Number.isFinite(props.value));
const safeValue = computed(() => Math.max(0, Math.min(100, Number(props.value) || 0)));
const tone = computed(() => safeValue.value >= 90 ? 'danger' : safeValue.value >= 75 ? 'warning' : 'normal');
</script>

<template>
  <div class="ai-resource-gauge">
    <div class="ai-resource-gauge__meta"><span>{{ label }}</span><strong>{{ available ? safeValue.toFixed(0) + '%' : '未上报' }}</strong></div>
    <div class="ai-resource-gauge__track"><span v-if="available" :class="`ai-resource-gauge__fill--${tone}`" :style="{ width: `${safeValue}%` }"></span></div>
  </div>
</template>

<style scoped>
.ai-resource-gauge__meta { display: flex; align-items: center; justify-content: space-between; margin-bottom: 5px; color: hsl(var(--muted-foreground)); font-size: 11px; }
.ai-resource-gauge__meta strong { color: hsl(var(--foreground)); font-weight: 600; }
.ai-resource-gauge__track { height: 5px; overflow: hidden; background: hsl(var(--muted)); border-radius: 99px; }
.ai-resource-gauge__track span { display: block; height: 100%; background: #2563eb; border-radius: inherit; transition: width 240ms ease; }
.ai-resource-gauge__track .ai-resource-gauge__fill--warning { background: var(--ai-warning); }
.ai-resource-gauge__track .ai-resource-gauge__fill--danger { background: var(--ai-danger); }
</style>
