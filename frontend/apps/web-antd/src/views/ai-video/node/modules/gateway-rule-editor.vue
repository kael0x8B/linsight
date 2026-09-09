<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';

import { computed, ref } from 'vue';

import { Alert, Button, InputNumber, Select, Switch } from 'ant-design-vue';

import { $t } from '#/locales';
import { createRuleAst } from '#/views/ai-video/rule/modules/rule-state';

const props = defineProps<{ image?: string; modelValue: string; }>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const regionIndex = ref(0);
const drawing = ref(false);
const draftPoints = ref<{ x: number; y: number }[]>([]);
const ast = computed<AiVideoRuleApi.RuleAst | null>(() => {
  try { return props.modelValue ? JSON.parse(props.modelValue) : null; } catch { return null; }
});
const region = computed(() => ast.value?.regions[regionIndex.value] ?? ast.value?.regions[0]);
const points = computed(() => (drawing.value ? draftPoints.value : region.value?.points ?? []).map(p => `${p.x * 1000},${p.y * 1000}`).join(' '));
const children = computed(() => (ast.value?.condition.children ?? []) as Record<string, unknown>[]);
const duration = computed(() => Number(children.value.find(c => c.type === 'DURATION')?.seconds ?? 2));
const cooldown = computed(() => ast.value?.cooldownSeconds ?? 30);
const classes = computed(() => (children.value.find(c => c.type === 'ROI_ENTER' && c.regionId === region.value?.id)?.objectClasses ?? ['person']) as string[]);
function update(mutator: (value: AiVideoRuleApi.RuleAst) => void) {
  if (!ast.value) return;
  const value = JSON.parse(JSON.stringify(ast.value)) as AiVideoRuleApi.RuleAst;
  mutator(value); emit('update:modelValue', JSON.stringify(value, null, 2));
}
function enabled(value: boolean | number | string) {
  drawing.value = false;
  emit('update:modelValue', value ? JSON.stringify(createRuleAst('AREA_INTRUSION'), null, 2) : '');
}
function addPoint(event: MouseEvent) {
  if (!drawing.value) return;
  const rect = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
  draftPoints.value.push({ x: Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width)), y: Math.min(1, Math.max(0, (event.clientY - rect.top) / rect.height)) });
}
function finishDrawing() {
  if (draftPoints.value.length < 3) return;
  update(value => { const target = value.regions[regionIndex.value]; if (target) target.points = [...draftPoints.value]; });
  drawing.value = false;
}
function condition(type: string, key: string, value: unknown) {
  update(rule => {
    const nodes = Array.isArray(rule.condition.children) ? rule.condition.children as Record<string, unknown>[] : [];
    const node = nodes.find(c => c.type === type && (type !== 'ROI_ENTER' || c.regionId === region.value?.id));
    if (node) node[key] = value;
  });
}
</script>
<template>
  <div class="mt-5 border-t pt-4">
    <div class="mb-4 flex items-center gap-3"><b>{{ $t('ai-video-gateway.mea96f8bd27') }}</b><Switch :checked="Boolean(ast)" @change="enabled" /></div>
    <template v-if="ast && region">
      <div class="mb-3 flex flex-wrap items-center gap-2">
        <Select v-model:value="regionIndex" class="min-w-40" :options="ast.regions.map((r, i) => ({ label: r.name, value: i }))" />
        <Button @click="drawing = true; draftPoints = []">{{ $t('ai-video-gateway.mfdbea3f99b') }}</Button>
        <Button v-if="drawing" @click="draftPoints.pop()">{{ $t('ai-video-gateway.mce3cdbf32b') }}</Button>
        <Button v-if="drawing" :disabled="draftPoints.length < 3" @click="finishDrawing">{{ $t('ai-video-gateway.ma45f66c9b9') }}</Button>
        <Button @click="update(v => { const r = v.regions[regionIndex]; if (r) r.points = [{x:0,y:0},{x:1,y:0},{x:1,y:1},{x:0,y:1}]; }); drawing = false">{{ $t('ai-video-gateway.mfb20fafd7b') }}</Button>
      </div>
      <Alert v-if="drawing" type="info" class="mb-2" :message="$t('ai-video-gateway.mccc149a891')" />
      <svg viewBox="0 0 1000 1000" preserveAspectRatio="none" :style="{ aspectRatio: `${region.sourceWidth}/${region.sourceHeight}` }" class="max-h-80 w-full cursor-crosshair rounded bg-slate-950" role="img" :aria-label="$t('ai-video-gateway.m0575dcfc50')" @click="addPoint">
        <image v-if="image" :href="`data:image/jpeg;base64,${image}`" width="1000" height="1000" preserveAspectRatio="none" />
        <polygon :points="points" fill="#2563eb33" stroke="#60a5fa" stroke-width="4" />
      </svg>
      <div class="mt-4 grid grid-cols-2 gap-4">
        <label v-if="children.some(c => c.type === 'ROI_ENTER')">{{ $t('ai-video-gateway.targetClasses') }}<Select mode="tags" :value="classes" class="mt-2 w-full" @change="value => condition('ROI_ENTER', 'objectClasses', value)" /></label>
        <label v-if="children.some(c => c.type === 'DURATION')">{{ $t('ai-video-gateway.durationSeconds') }}<InputNumber :value="duration" :min="0" :max="86400" class="mt-2 !w-full" @change="value => condition('DURATION', 'seconds', value)" /></label>
        <label>{{ $t('ai-video-gateway.md7708a1eaf') }}<InputNumber :value="cooldown" :min="0" :max="86400" class="mt-2 !w-full" @change="value => update(v => { v.cooldownSeconds = Number(value); })" /></label>
        <label>{{ $t('ai-video-gateway.me21b391a4a') }}<Select :value="region.pointMode" class="mt-2 w-full" :options="[{label:$t('ai-video-gateway.m83bdaf46e0'),value:'FOOT'},{label:$t('ai-video-gateway.mcadbc29b72'),value:'CENTROID'},{label:$t('ai-video-gateway.m0c14ad2cde'),value:'OVERLAP'}]" @change="value => update(v => { const r = v.regions[regionIndex]; if (r) r.pointMode = value as typeof r.pointMode; })" /></label>
      </div>
    </template>
    <p v-else class="text-muted-foreground">{{ $t('ai-video-gateway.m773c9054ef') }}</p>
  </div>
</template>
