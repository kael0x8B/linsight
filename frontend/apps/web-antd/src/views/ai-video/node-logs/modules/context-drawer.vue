<script lang="ts" setup>
import type { AiVideoNodeLogApi } from '#/api/ai-video/node-log';

import { ref } from 'vue';

import { useVbenDrawer } from '@vben/common-ui';

import { Alert, Button, Empty, Spin, Tag } from 'ant-design-vue';

import { getNodeLogContext } from '#/api/ai-video/node-log';

const logs = ref<AiVideoNodeLogApi.Log[]>([]);
const loading = ref(false);
const error = ref('');

const levelColors: Record<string, string> = {
  DEBUG: 'default',
  ERROR: 'error',
  INFO: 'processing',
  WARN: 'warning',
};

async function load() {
  const selected = drawerApi.getData<AiVideoNodeLogApi.Log>();
  if (!selected?.id) return;
  loading.value = true;
  error.value = '';
  try {
    logs.value = await getNodeLogContext(selected.id);
  } catch {
    error.value = '日志上下文加载失败，请检查权限和控制面状态。';
  } finally {
    loading.value = false;
  }
}

const [Drawer, drawerApi] = useVbenDrawer({
  async onOpenChange(open) {
    if (open) await load();
    else logs.value = [];
  },
});
</script>

<template>
  <Drawer class="w-[1000px] max-w-[calc(100vw-32px)]" :footer="false" title="前后 100 行日志上下文">
    <div class="px-3 py-2">
      <Alert v-if="error" :message="error" show-icon type="error">
        <template #action><Button size="small" @click="load">重试</Button></template>
      </Alert>
      <Spin :spinning="loading">
        <div v-if="logs.length" class="max-h-[calc(100vh-150px)] overflow-auto rounded bg-[#111827] p-3 font-mono text-xs text-slate-200">
          <div v-for="item in logs" :key="item.id" class="grid grid-cols-[175px_70px_110px_1fr] gap-2 border-b border-slate-800 py-1.5">
            <span class="text-slate-400">{{ item.loggedAt }}</span>
            <Tag :color="levelColors[item.level] || 'default'">{{ item.level }}</Tag>
            <span class="text-cyan-300">{{ item.component }}</span>
            <span class="whitespace-pre-wrap break-all">{{ item.message }}</span>
          </div>
        </div>
        <Empty v-else-if="!loading && !error" description="该日志没有可读取的上下文" />
      </Spin>
    </div>
  </Drawer>
</template>
