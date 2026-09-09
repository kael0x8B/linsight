<script lang="ts" setup>
import { computed, nextTick, ref, watch } from 'vue';

import { IconifyIcon } from '@vben/icons';

import { Button, message } from 'ant-design-vue';

const props = defineProps<{
  logStatus?: string;
  output?: string;
  status?: 'FAILED' | 'QUEUED' | 'RUNNING' | 'SUCCEEDED';
  truncated?: boolean;
}>();

const panelRef = ref<HTMLElement>();
const followTail = ref(true);
const displayOutput = computed(() => {
  if (props.output) return props.output;
  if (props.logStatus === 'LEGACY') return '$ 历史记录未采集 SSH 原始输出，无法回溯。';
  if (props.logStatus === 'FAILED') return '$ SSH 日志采集异常，请查看部署结果和诊断信息。';
  return ['FAILED', 'SUCCEEDED'].includes(props.status ?? '')
    ? '$ 本次部署没有可读取的 SSH 输出。'
    : '$ 等待部署输出…';
});

watch(
  () => props.output,
  async () => {
    if (!followTail.value) return;
    await nextTick();
    if (panelRef.value) panelRef.value.scrollTop = panelRef.value.scrollHeight;
  },
  { flush: 'post' },
);

async function copyOutput() {
  if (!props.output) return;
  await navigator.clipboard.writeText(props.output);
  message.success('部署输出已复制');
}
</script>

<template>
  <section class="deployment-terminal">
    <header>
      <div class="terminal-title">
        <span class="status-dot" :class="status?.toLowerCase()"></span>
        SSH 部署输出
      </div>
      <div class="terminal-actions">
        <Button size="small" type="text" @click="followTail = !followTail">
          <IconifyIcon :icon="followTail ? 'lucide:pause' : 'lucide:play'" />
          {{ followTail ? '暂停滚动' : '跟随输出' }}
        </Button>
        <Button size="small" type="text" :disabled="!output" @click="copyOutput">
          <IconifyIcon icon="lucide:copy" />复制
        </Button>
      </div>
    </header>
    <p v-if="truncated" class="px-4 text-xs text-amber-300">日志已截断，仅显示最近的输出。</p>
    <pre ref="panelRef" aria-live="polite" tabindex="0">{{ displayOutput }}</pre>
  </section>
</template>

<style scoped>
.deployment-terminal { overflow: hidden; border: 1px solid #273244; border-radius: 10px; background: #0b1120; }
.deployment-terminal header { display: flex; min-height: 40px; align-items: center; justify-content: space-between; padding: 0 10px 0 14px; border-bottom: 1px solid #273244; color: #cbd5e1; background: #111827; }
.terminal-title, .terminal-actions { display: flex; align-items: center; gap: 8px; }
.terminal-title { font-size: 12px; font-weight: 600; }
.terminal-actions :deep(.ant-btn) { color: #94a3b8; font-size: 12px; }
.terminal-actions :deep(.ant-btn:hover) { color: #e2e8f0; background: #1e293b; }
.status-dot { width: 8px; height: 8px; border-radius: 999px; background: #64748b; }
.status-dot.running, .status-dot.queued { background: #38bdf8; box-shadow: 0 0 0 3px rgb(56 189 248 / 15%); }
.status-dot.succeeded { background: #4ade80; }
.status-dot.failed { background: #fb7185; }
.deployment-terminal pre { min-height: 220px; max-height: 420px; padding: 14px 16px; margin: 0; overflow: auto; color: #d1fae5; font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace; font-size: 12px; line-height: 1.65; overflow-wrap: anywhere; white-space: pre-wrap; }
</style>
