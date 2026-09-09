<script lang="ts" setup>
import type { AiVideoEventApi } from '#/api/ai-video/event';
import type { AiVideoNode } from '#/api/ai-video/node';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { Alert, Button, Card, Empty, Progress, Skeleton, Space, Tag, Tooltip } from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAlgorithmPage } from '#/api/ai-video/algorithm';
import { getCameraPage } from '#/api/ai-video/camera';
import { getEventPage } from '#/api/ai-video/event';
import { getModelPage } from '#/api/ai-video/model';
import { getNodeList } from '#/api/ai-video/node';
import { getTaskPage } from '#/api/ai-video/task';
import { AiMetricCard, AiPageHeader, AiResourceGauge, AiStatusIndicator } from '#/components/ai-video';

const router = useRouter();
const loading = ref(true);
const error = ref('');
const updatedAt = ref('');
const summary = ref({ algorithmTotal: 0, cameraOffline: 0, cameraOnline: 0, cameraTotal: 0, modelTotal: 0, nodeOnline: 0, nodeTotal: 0, taskFailed: 0, taskRunning: 0, taskTotal: 0, todayEvents: 0, unhandledEvents: 0 });
const recentEvents = ref<AiVideoEventApi.Event[]>([]);
const nodes = ref<AiVideoNode[]>([]);

const criticalMetrics = computed(() => [
  { accent: 'warning' as const, description: '基于最近 100 条事件样本', icon: 'lucide:siren', label: '今日事件', path: '/ai-video/event', suffix: '条', value: summary.value.todayEvents },
  { accent: 'danger' as const, description: '等待领取或处置', icon: 'lucide:circle-alert', label: '未处理告警', path: '/ai-video/event', suffix: '条', value: summary.value.unhandledEvents },
  { accent: 'danger' as const, description: `离线摄像头 ${summary.value.cameraOffline} · 异常任务 ${summary.value.taskFailed}`, icon: 'lucide:triangle-alert', label: '设备与任务异常', path: '/ai-video/camera', suffix: '项', value: summary.value.cameraOffline + summary.value.taskFailed + (summary.value.nodeTotal - summary.value.nodeOnline) },
]);

const secondaryMetrics = computed(() => [
  { accent: 'info' as const, description: `在线 ${summary.value.cameraOnline} · 离线 ${summary.value.cameraOffline}`, icon: 'lucide:cctv', label: '摄像头', path: '/ai-video/camera', suffix: '路', value: summary.value.cameraTotal },
  { accent: 'success' as const, description: `共 ${summary.value.taskTotal} 个任务`, icon: 'lucide:scan-line', label: '运行中任务', path: '/ai-video/task', suffix: '个', value: summary.value.taskRunning },
  { accent: 'neutral' as const, description: `${summary.value.algorithmTotal} 个算法能力`, icon: 'lucide:boxes', label: '模型资产', path: '/ai-video/model', suffix: '个', value: summary.value.modelTotal },
  { accent: 'success' as const, description: `在线 ${summary.value.nodeOnline}/${summary.value.nodeTotal}`, icon: 'lucide:server-cog', label: '边缘节点', path: '/ai-video/node', suffix: '台', value: summary.value.nodeTotal },
]);

const trend = computed(() => {
  const buckets = Array.from({ length: 12 }, (_, index) => ({ count: 0, label: `${String(index * 2).padStart(2, '0')}:00` }));
  for (const item of recentEvents.value) {
    const occurred = dayjs(item.occurredTime);
    if (occurred.isSame(dayjs(), 'day')) buckets[Math.floor(occurred.hour() / 2)]!.count += 1;
  }
  const max = Math.max(1, ...buckets.map((item) => item.count));
  return buckets.map((item) => ({ ...item, height: Math.max(item.count ? 14 : 3, Math.round((item.count / max) * 100)) }));
});

const severityDistribution = computed(() => {
  const labels: Record<string, string> = { CRITICAL: '严重', INFO: '提示', MAJOR: '重要', MINOR: '一般', URGENT: '紧急' };
  const colors: Record<string, string> = { CRITICAL: '#dc2626', INFO: '#2563eb', MAJOR: '#d97706', MINOR: '#64748b', URGENT: '#991b1b' };
  const counts = new Map<string, number>();
  recentEvents.value.forEach((item) => counts.set(item.severity, (counts.get(item.severity) ?? 0) + 1));
  return Object.entries(labels).map(([key, label]) => ({ color: colors[key], count: counts.get(key) ?? 0, key, label }));
});

const onlineRate = computed(() => summary.value.cameraTotal ? Math.round((summary.value.cameraOnline / summary.value.cameraTotal) * 100) : 0);

function parseResource(node: AiVideoNode) {
  try { return JSON.parse(node.resourceSnapshot || '{}') as Record<string, number>; } catch { return {} as Record<string, number>; }
}

const resourceAverages = computed(() => {
  const active = nodes.value.filter((item) => item.onlineStatus === 1).map(parseResource);
  const average = (key: string) => active.length ? active.reduce((sum, item) => sum + Number(item[key] ?? 0), 0) / active.length : 0;
  const memory = active.map((item) => item.memoryTotalBytes ? (Number(item.memoryUsedBytes ?? 0) / Number(item.memoryTotalBytes)) * 100 : 0);
  return { cpu: average('cpuUsage'), gpu: average('gpuUsage'), memory: memory.length ? memory.reduce((sum, value) => sum + value, 0) / memory.length : 0 };
});

function severityLabel(value: string) { return ({ CRITICAL: '严重', INFO: '提示', MAJOR: '重要', MINOR: '一般', URGENT: '紧急' }[value] ?? value); }
function severityColor(value: string) { return ({ CRITICAL: 'red', INFO: 'blue', MAJOR: 'orange', MINOR: 'default', URGENT: 'red' }[value] ?? 'default'); }

async function loadOverview() {
  loading.value = true;
  error.value = '';
  try {
    const [cameraPage, onlineCameraPage, offlineCameraPage, taskPage, eventPage, nodeList, modelPage, algorithmPage] = await Promise.all([
      getCameraPage({ pageNo: 1, pageSize: 1 }), getCameraPage({ onlineStatus: 1, pageNo: 1, pageSize: 1 }), getCameraPage({ onlineStatus: 2, pageNo: 1, pageSize: 1 }),
      getTaskPage({ pageNo: 1, pageSize: 100 }), getEventPage({ pageNo: 1, pageSize: 100 }), getNodeList(), getModelPage({ pageNo: 1, pageSize: 1 }), getAlgorithmPage({ pageNo: 1, pageSize: 1 }),
    ]);
    recentEvents.value = eventPage.list;
    nodes.value = nodeList;
    summary.value = {
      algorithmTotal: algorithmPage.total, cameraOffline: offlineCameraPage.total, cameraOnline: onlineCameraPage.total, cameraTotal: cameraPage.total, modelTotal: modelPage.total,
      nodeOnline: nodeList.filter((item) => item.onlineStatus === 1).length, nodeTotal: nodeList.length,
      taskFailed: taskPage.list.filter((item) => ['FAILED', 'OFFLINE'].includes(item.actualStatus)).length, taskRunning: taskPage.list.filter((item) => item.actualStatus === 'RUNNING').length, taskTotal: taskPage.total,
      todayEvents: eventPage.list.filter((item) => dayjs(item.occurredTime).isSame(dayjs(), 'day')).length, unhandledEvents: eventPage.list.filter((item) => ['ALARM', 'ASSIGNED'].includes(item.status)).length,
    };
    updatedAt.value = dayjs().format('HH:mm:ss');
  } catch { error.value = '运行数据加载失败，请检查租户、后端服务和数据库迁移。'; }
  finally { loading.value = false; }
}

onMounted(loadOverview);
</script>

<template>
  <Page>
    <main class="ai-page dashboard-page">
      <AiPageHeader title="运行总览" description="聚焦告警、视频源、分析任务与边缘算力的实时运行态势。" icon="lucide:layout-dashboard">
        <template #extra><Space><span v-if="updatedAt" class="dashboard-updated">更新于 {{ updatedAt }}</span><Button :loading="loading" @click="loadOverview"><IconifyIcon icon="lucide:refresh-cw" />刷新</Button><Button type="primary" @click="router.push('/ai-video/live')"><IconifyIcon icon="lucide:play" />实时视频</Button></Space></template>
      </AiPageHeader>
      <Alert v-if="error" :message="error" show-icon type="error"><template #action><Button @click="loadOverview">重试</Button></template></Alert>
      <Skeleton v-if="loading && !updatedAt" active :paragraph="{ rows: 9 }" />
      <template v-else>
        <section class="dashboard-critical" aria-label="重点指标"><AiMetricCard v-for="item in criticalMetrics" :key="item.label" v-bind="item" emphasized @select="router.push(item.path)" /></section>
        <section class="dashboard-secondary" aria-label="运行指标"><AiMetricCard v-for="item in secondaryMetrics" :key="item.label" v-bind="item" @select="router.push(item.path)" /></section>
        <section class="dashboard-main-grid">
          <Card class="dashboard-trend" :bordered="false"><template #title><div><div class="ai-section-title">今日事件趋势</div><div class="ai-section-description">2 小时粒度 · 最近 100 条事件样本</div></div></template><div class="trend-chart" role="img" aria-label="今日事件趋势柱状图"><Tooltip v-for="item in trend" :key="item.label" :title="`${item.label} · ${item.count} 条`"><div class="trend-bar-wrap"><span class="trend-value">{{ item.count || '' }}</span><span class="trend-bar" :style="{ height: `${item.height}%` }"></span><span class="trend-label">{{ item.label }}</span></div></Tooltip></div></Card>
          <Card :bordered="false"><template #title><div><div class="ai-section-title">事件等级分布</div><div class="ai-section-description">当前事件样本的风险构成</div></div></template><div class="severity-list"><div v-for="item in severityDistribution" :key="item.key" class="severity-row"><span class="severity-dot" :style="{ background: item.color }"></span><span class="severity-name">{{ item.label }}</span><strong>{{ item.count }}</strong></div></div></Card>
        </section>
        <section class="dashboard-bottom-grid">
          <Card :bordered="false"><template #title><div><div class="ai-section-title">设备与计算资源</div><div class="ai-section-description">在线率与在线节点平均负载</div></div></template><div class="health-grid"><div class="online-rate"><Progress type="dashboard" :percent="onlineRate" :stroke-width="9" :width="116" /><div><strong>摄像头在线率</strong><p>{{ summary.cameraOnline }} 在线 / {{ summary.cameraTotal }} 总计</p></div></div><div class="resource-list"><AiResourceGauge label="CPU" :value="resourceAverages.cpu" /><AiResourceGauge label="Memory" :value="resourceAverages.memory" /><AiResourceGauge label="GPU" :value="resourceAverages.gpu" /></div></div></Card>
          <Card :bordered="false"><template #title><div class="dashboard-card-title"><div><div class="ai-section-title">最近告警</div><div class="ai-section-description">优先展示仍需处理的事件</div></div><Button type="link" @click="router.push('/ai-video/event')">查看全部</Button></div></template><div v-if="recentEvents.length" class="recent-events"><button v-for="item in recentEvents.slice(0, 5)" :key="item.id" type="button" @click="router.push('/ai-video/event')"><Tag :color="severityColor(item.severity)">{{ severityLabel(item.severity) }}</Tag><span class="recent-event__body"><strong>{{ item.eventType }}</strong><small>#{{ item.cameraId }} · {{ dayjs(item.occurredTime).format('MM-DD HH:mm:ss') }}</small></span><AiStatusIndicator :label="item.status" :status="item.status" size="sm" /></button></div><Empty v-else description="暂无事件；接入视频并启动分析任务后，告警会显示在这里" /></Card>
        </section>
      </template>
    </main>
  </Page>
</template>

<style scoped>
.dashboard-page { display: flex; flex-direction: column; gap: 16px; }
.dashboard-updated { color: hsl(var(--muted-foreground)); font-size: 12px; }
.dashboard-critical { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }
.dashboard-secondary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; }
.dashboard-main-grid { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, .72fr); gap: 16px; }
.dashboard-bottom-grid { display: grid; grid-template-columns: minmax(380px, .9fr) minmax(0, 1.3fr); gap: 16px; }
.dashboard-page :deep(.ant-card) { height: 100%; }
.dashboard-card-title { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.trend-chart { display: flex; height: 190px; align-items: flex-end; gap: clamp(5px, 1.1vw, 14px); padding: 16px 8px 0; border-bottom: 1px solid hsl(var(--border)); background-image: linear-gradient(to bottom, hsl(var(--border) / 32%) 1px, transparent 1px); background-size: 100% 25%; }
.trend-bar-wrap { position: relative; display: flex; height: 100%; min-width: 16px; flex: 1; align-items: center; justify-content: flex-end; flex-direction: column; }
.trend-bar { width: min(28px, 72%); min-height: 3px; background: linear-gradient(to top, #2563eb, #22d3ee); border-radius: 5px 5px 2px 2px; opacity: .88; }
.trend-value { min-height: 17px; color: hsl(var(--muted-foreground)); font-size: 10px; }
.trend-label { margin-top: 8px; color: hsl(var(--muted-foreground)); font-size: 10px; white-space: nowrap; }
.severity-list { display: grid; gap: 4px; }
.severity-row { display: grid; grid-template-columns: 8px 1fr auto; align-items: center; gap: 10px; min-height: 30px; padding: 4px 8px; border-radius: 6px; }
.severity-row:hover { background: hsl(var(--muted) / 45%); }
.severity-dot { width: 7px; height: 7px; border-radius: 99px; }
.severity-name { color: hsl(var(--muted-foreground)); font-size: 12px; }
.severity-row strong { font-size: 13px; }
.health-grid { display: grid; grid-template-columns: 1fr 1fr; align-items: center; gap: 24px; }
.online-rate { display: flex; align-items: center; gap: 16px; }
.online-rate strong { font-size: 13px; }
.online-rate p { margin: 5px 0 0; color: hsl(var(--muted-foreground)); font-size: 11px; }
.resource-list { display: grid; gap: 13px; }
.recent-events { display: grid; gap: 3px; }
.recent-events button { display: grid; grid-template-columns: auto minmax(0, 1fr) auto; align-items: center; gap: 10px; min-height: 45px; padding: 6px 8px; text-align: left; border-radius: 7px; }
.recent-events button:hover { background: hsl(var(--muted) / 48%); }
.recent-event__body { display: grid; min-width: 0; }
.recent-event__body strong { overflow: hidden; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.recent-event__body small { color: hsl(var(--muted-foreground)); font-size: 10px; }
@media (width <= 1200px) { .dashboard-secondary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .dashboard-bottom-grid { grid-template-columns: 1fr; } }
@media (width <= 900px) { .dashboard-critical, .dashboard-main-grid { grid-template-columns: 1fr; } }
</style>
