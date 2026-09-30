<script lang="ts" setup>
import type { AiVideoEventApi } from '#/api/ai-video/event';
import type { AiVideoNode } from '#/api/ai-video/node';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import { useNow } from '@vueuse/core';
import {
  Alert,
  Button,
  Card,
  Empty,
  Skeleton,
  Tag,
  Tooltip,
} from 'ant-design-vue';
import dayjs from 'dayjs';

import { getAlgorithmPage } from '#/api/ai-video/algorithm';
import { getCameraPage } from '#/api/ai-video/camera';
import { getEventPage } from '#/api/ai-video/event';
import { getModelPage } from '#/api/ai-video/model';
import { getNodeList } from '#/api/ai-video/node';
import { getTaskPage } from '#/api/ai-video/task';
import {
  AiMetricCard,
  AiPageHeader,
  AiResourceGauge,
  AiStatusIndicator,
} from '#/components/ai-video';
import { $t } from '#/locales';
import {
  eventTypes,
  severityColor,
  severityText,
  statusText,
} from '#/views/ai-video/event/presentation';

import { averageResources, prioritizeEvents } from './presentation';

const router = useRouter();
const { hasAccessByCodes } = useAccess();
const t = (key: string, values: Record<string, number | string> = {}) =>
  $t(`dashboard.${key}`, values);
const canRead = (domain: string) =>
  hasAccessByCodes([`ai-video:${domain}:query`]);
const loading = ref(false);
const loaded = ref(false);
const updatedAt = ref(0);
const eventUpdatedAt = ref(0);
const failedSources = ref<string[]>([]);
const now = useNow({ interval: 1000 });
const stale = computed(
  () => updatedAt.value > 0 && now.value.getTime() - updatedAt.value > 60_000,
);
const camera = ref<{ offline: number; online: number; total: number }>();
const tasks = ref<{ list: AiVideoTaskApi.Task[]; total: number }>();
const events = ref<{ list: AiVideoEventApi.Event[]; total: number }>();
const nodes = ref<AiVideoNode[]>();
const modelTotal = ref<number>();
const algorithmTotal = ref<number>();
const noAccess = computed(
  () =>
    !['camera', 'task', 'event', 'node', 'model', 'algorithm'].some((domain) =>
      canRead(domain),
    ),
);
const recentEvents = computed(() => events.value?.list ?? []);
const taskRunning = computed(
  () =>
    tasks.value?.list.filter((item) => item.actualStatus === 'RUNNING').length,
);
const taskFailed = computed(
  () =>
    tasks.value?.list.filter((item) =>
      ['FAILED', 'OFFLINE'].includes(item.actualStatus),
    ).length,
);
const nodeOnline = computed(
  () => nodes.value?.filter((item) => item.onlineStatus === 1).length,
);
const nodeOffline = computed(
  () => nodes.value?.filter((item) => item.onlineStatus !== 1).length,
);
const todayEvents = computed(() =>
  recentEvents.value.filter((item) =>
    dayjs(item.occurredTime).isSame(dayjs(eventUpdatedAt.value), 'day'),
  ),
);
const unhandledEvents = computed(() =>
  events.value
    ? recentEvents.value.filter((item) =>
        ['ALARM', 'ASSIGNED'].includes(item.status),
      ).length
    : undefined,
);
const priorityEvents = computed(() =>
  prioritizeEvents(recentEvents.value).slice(0, 5),
);
const resourceAverages = computed(() => averageResources(nodes.value ?? []));
const unavailable = (domain: string) =>
  t(canRead(domain) ? 'unavailable' : 'noPermission');
const valueOrDash = (value?: number) => value ?? '—';

const metrics = computed(() => [
  {
    accent: 'info' as const,
    description: camera.value
      ? t('cameraCount', {
          online: camera.value.online,
          total: camera.value.total,
        })
      : unavailable('camera'),
    icon: 'lucide:cctv',
    label: t('cameraOnlineRate'),
    path: '/ai-video/camera',
    suffix: camera.value?.total ? '%' : '',
    value: camera.value?.total
      ? Math.round((camera.value.online / camera.value.total) * 100)
      : '—',
    domain: 'camera',
  },
  {
    accent: 'success' as const,
    description: tasks.value
      ? t(tasks.value.total > 100 ? 'taskSample' : 'taskCount', {
          total: tasks.value.total,
        })
      : unavailable('task'),
    icon: 'lucide:scan-line',
    label: t('runningTasks'),
    path: '/ai-video/task',
    suffix: t('tasksUnit'),
    value: valueOrDash(taskRunning.value),
    domain: 'task',
  },
  {
    accent: 'warning' as const,
    description: events.value
      ? t('eventSample', { count: recentEvents.value.length })
      : unavailable('event'),
    icon: 'lucide:bell-ring',
    label: t('todayEvents'),
    path: '/ai-video/event',
    suffix: t('eventsUnit'),
    value: events.value ? todayEvents.value.length : '—',
    domain: 'event',
  },
  {
    accent: 'info' as const,
    description: nodes.value
      ? t('nodeCount', {
          total: nodes.value.length,
          offline: nodeOffline.value ?? 0,
        })
      : unavailable('node'),
    icon: 'lucide:server',
    label: t('onlineNodes'),
    path: '/ai-video/node',
    suffix: t('nodesUnit'),
    value: valueOrDash(nodeOnline.value),
    domain: 'node',
  },
]);
const attentionItems = computed(() => [
  {
    label: t('pendingEvents'),
    value: unhandledEvents.value,
    path: '/ai-video/event',
    domain: 'event',
    icon: 'lucide:bell-ring',
  },
  {
    label: t('offlineCameras'),
    value: camera.value?.offline,
    path: '/ai-video/camera',
    domain: 'camera',
    icon: 'lucide:video-off',
  },
  {
    label: t('abnormalTasks'),
    value: taskFailed.value,
    path: '/ai-video/task',
    domain: 'task',
    icon: 'lucide:scan-line',
  },
  {
    label: t('offlineNodes'),
    value: nodeOffline.value,
    path: '/ai-video/node',
    domain: 'node',
    icon: 'lucide:server-off',
  },
]);
const trend = computed(() => {
  const buckets = Array.from({ length: 12 }, (_, index) => ({
    count: 0,
    label: `${String(index * 2).padStart(2, '0')}:00`,
  }));
  for (const event of todayEvents.value) {
    const bucket = buckets[Math.floor(dayjs(event.occurredTime).hour() / 2)];
    if (bucket) bucket.count += 1;
  }
  const ceiling =
    Math.ceil(Math.max(4, ...buckets.map((item) => item.count)) / 4) * 4;
  return {
    ticks: [ceiling, (ceiling / 4) * 3, ceiling / 2, ceiling / 4, 0],
    buckets: buckets.map((item) => ({
      ...item,
      height: (item.count / ceiling) * 100,
    })),
  };
});
const severityDistribution = computed(() =>
  ['URGENT', 'CRITICAL', 'MAJOR', 'MINOR', 'INFO'].map((key) => {
    const count = recentEvents.value.filter(
      (item) => item.severity === key,
    ).length;
    const colors: Record<string, string> = {
      URGENT: '#991b1b',
      CRITICAL: '#dc2626',
      MAJOR: '#d97706',
      MINOR: '#64748b',
      INFO: '#2563eb',
    };
    return {
      key,
      label: severityText[key],
      color: colors[key],
      count,
      percent:
        recentEvents.value.length > 0
          ? (count / recentEvents.value.length) * 100
          : 0,
    };
  }),
);

// Keep successful domains visible if another source is unavailable.
async function loadSource<T>(
  domain: string,
  load: () => Promise<T>,
  save: (result: T) => void,
) {
  if (!canRead(domain)) return;
  try {
    save(await load());
  } catch {
    failedSources.value.push(t(`sources.${domain}`));
  }
}
async function loadOverview() {
  if (loading.value) return;
  loading.value = true;
  failedSources.value = [];
  await Promise.all([
    loadSource(
      'camera',
      async () => {
        const [all, online, offline] = await Promise.all([
          getCameraPage({ pageNo: 1, pageSize: 1 }),
          getCameraPage({ onlineStatus: 1, pageNo: 1, pageSize: 1 }),
          getCameraPage({ onlineStatus: 2, pageNo: 1, pageSize: 1 }),
        ]);
        return {
          total: all.total,
          online: online.total,
          offline: offline.total,
        };
      },
      (value) => {
        camera.value = value;
      },
    ),
    loadSource(
      'task',
      () => getTaskPage({ pageNo: 1, pageSize: 100 }),
      (value) => {
        tasks.value = value;
      },
    ),
    loadSource(
      'event',
      () => getEventPage({ pageNo: 1, pageSize: 100 }),
      (value) => {
        events.value = value;
        eventUpdatedAt.value = Date.now();
      },
    ),
    loadSource('node', getNodeList, (value) => {
      nodes.value = value;
    }),
    loadSource(
      'model',
      () => getModelPage({ pageNo: 1, pageSize: 1 }),
      (value) => {
        modelTotal.value = value.total;
      },
    ),
    loadSource(
      'algorithm',
      () => getAlgorithmPage({ pageNo: 1, pageSize: 1 }),
      (value) => {
        algorithmTotal.value = value.total;
      },
    ),
  ]);
  // Never mark retained older data as freshly updated after a partial refresh.
  if (failedSources.value.length === 0 && !noAccess.value)
    updatedAt.value = Date.now();
  loaded.value = true;
  loading.value = false;
}
onMounted(loadOverview);
</script>

<template>
  <Page>
    <main class="ai-page dashboard-page" :aria-busy="loading">
      <AiPageHeader
        :title="t('title')"
        :description="t('description')"
        icon="lucide:layout-dashboard"
      >
        <template #extra>
          <div class="dashboard-actions">
            <span
              class="dashboard-updated"
              :class="{ 'is-stale': stale || failedSources.length }"
              role="status"
            >
              <IconifyIcon
                :icon="
                  stale || failedSources.length
                    ? 'lucide:clock-alert'
                    : 'lucide:clock-3'
                "
              />
              {{
                failedSources.length
                  ? t('partialData')
                  : stale
                    ? t('stale')
                    : t('updated')
              }}
              <time
                v-if="updatedAt"
                :datetime="new Date(updatedAt).toISOString()"
                :title="dayjs(updatedAt).format('YYYY-MM-DD HH:mm:ss Z')"
                >{{ dayjs(updatedAt).format('HH:mm:ss') }}</time
              >
            </span>
            <Button :loading="loading" @click="loadOverview">
              <IconifyIcon icon="lucide:refresh-cw" />{{ t('refresh') }}
            </Button>
            <Button
              v-if="hasAccessByCodes(['ai-video:camera:preview'])"
              type="primary"
              @click="router.push('/ai-video/live')"
            >
              <IconifyIcon icon="lucide:play" />{{ t('liveVideo') }}
            </Button>
          </div>
        </template>
      </AiPageHeader>
      <Alert
        v-if="failedSources.length"
        :message="t('loadFailed', { sources: failedSources.join('、') })"
        show-icon
        type="warning"
      >
        <template #action>
          <Button size="small" :loading="loading" @click="loadOverview">
            {{ t('retry') }}
          </Button>
        </template>
      </Alert>
      <Skeleton v-if="loading && !loaded" active :paragraph="{ rows: 10 }" />
      <Empty v-else-if="noAccess" :description="t('noAccess')" />
      <template v-else>
        <section class="dashboard-kpis" :aria-label="t('coreMetrics')">
          <AiMetricCard
            v-for="item in metrics"
            :key="item.domain"
            v-bind="item"
            :disabled="!canRead(item.domain)"
            @select="router.push(item.path)"
          />
        </section>
        <section
          class="attention-strip ai-surface"
          :aria-label="t('attention')"
        >
          <div class="attention-label">
            <IconifyIcon icon="lucide:activity" />{{ t('attention') }}
          </div>
          <div class="attention-items">
            <button
              v-for="item in attentionItems"
              :key="item.domain"
              type="button"
              :disabled="!canRead(item.domain)"
              @click="router.push(item.path)"
            >
              <IconifyIcon :icon="item.icon" /><span>{{ item.label }}</span
              ><strong :class="{ 'attention-count': (item.value ?? 0) > 0 }">{{
                valueOrDash(item.value)
              }}</strong
              ><IconifyIcon
                icon="lucide:chevron-right"
                class="attention-arrow"
              />
            </button>
          </div>
        </section>
        <section class="dashboard-grid" :aria-label="t('eventAnalysis')">
          <Card class="dashboard-card trend-card" :bordered="false">
            <template #title>
              <h2>{{ t('trendTitle') }}</h2>
              <p class="card-caption">{{ t('trendDescription') }}</p>
            </template>
            <template #extra>
              <span class="period-label">{{ t('today') }}</span>
            </template>
            <div
              v-if="events && todayEvents.length"
              class="trend-chart"
              role="img"
              :aria-label="t('trendAccessible', { count: todayEvents.length })"
            >
              <div class="trend-axis">
                <span v-for="tick in trend.ticks" :key="tick">{{ tick }}</span>
              </div>
              <div class="trend-plot">
                <div
                  v-for="item in trend.buckets"
                  :key="item.label"
                  class="trend-column"
                >
                  <Tooltip
                    :title="
                      t('bucketCount', { time: item.label, count: item.count })
                    "
                  >
                    <div
                      class="trend-bar-area"
                      tabindex="0"
                      :aria-label="
                        t('bucketCount', {
                          time: item.label,
                          count: item.count,
                        })
                      "
                    >
                      <div
                        v-if="item.count"
                        class="trend-bar"
                        :style="{ height: `${item.height}%` }"
                      >
                        <span class="trend-value">{{ item.count }}</span>
                      </div>
                    </div>
                  </Tooltip>
                  <span class="trend-label">{{ item.label }}</span>
                </div>
              </div>
            </div>
            <div v-else class="chart-empty">
              <Empty
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                :description="
                  events ? t('noTodayEvents') : unavailable('event')
                "
              />
            </div>
          </Card>
          <Card class="dashboard-card" :bordered="false">
            <template #title>
              <h2>{{ t('severityTitle') }}</h2>
              <p class="card-caption">
                {{ t('severityDescription') }}
              </p>
            </template>
            <div v-if="events" class="severity-list">
              <div class="severity-summary">
                <span>{{ t('sampleTotal') }}</span
                ><strong
                  >{{ recentEvents.length
                  }}<small>{{ t('eventsUnit') }}</small></strong
                >
              </div>
              <div
                v-for="item in severityDistribution"
                :key="item.key"
                class="severity-row"
              >
                <span
                  class="severity-dot"
                  :style="{ background: item.color }"
                ></span
                ><span>{{ item.label }}</span
                ><span class="severity-track"
                  ><span
                    :style="{
                      width: `${item.percent}%`,
                      background: item.color,
                    }"
                  ></span></span
                ><strong>{{ item.count }}</strong
                ><small>{{ Math.round(item.percent) }}%</small>
              </div>
            </div>
            <div v-else class="chart-empty">
              <Empty
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                :description="unavailable('event')"
              />
            </div>
          </Card>
          <Card class="dashboard-card events-card" :bordered="false">
            <template #title>
              <h2>
                {{ t('priorityTitle')
                }}<span v-if="unhandledEvents" class="pending-badge">{{
                  t('pendingCount', { count: unhandledEvents })
                }}</span>
              </h2>
              <p class="card-caption">
                {{ t('priorityDescription') }}
              </p>
            </template>
            <template #extra>
              <Button
                v-if="canRead('event')"
                type="link"
                size="small"
                @click="router.push('/ai-video/event')"
              >
                {{ t('allEvents') }}<IconifyIcon icon="lucide:arrow-up-right" />
              </Button>
            </template>
            <div v-if="priorityEvents.length" class="recent-events">
              <button
                v-for="item in priorityEvents"
                :key="item.id"
                type="button"
                class="recent-event"
                @click="
                  router.push({
                    path: '/ai-video/event',
                    query: { eventId: item.id },
                  })
                "
              >
                <span
                  class="event-icon"
                  :class="{
                    'event-icon--pending': ['ALARM', 'ASSIGNED'].includes(
                      item.status,
                    ),
                  }"
                  ><IconifyIcon icon="lucide:bell-ring"
                /></span>
                <span class="recent-event__body"
                  ><strong>{{
                    eventTypes[item.eventType] ?? item.eventType
                  }}</strong
                  ><small
                    >{{
                      item.cameraName || t('cameraName', { id: item.cameraId })
                    }}<span
                      class="event-time"
                      :title="
                        dayjs(item.occurredTime).format('YYYY-MM-DD HH:mm:ss Z')
                      "
                      >{{
                        dayjs(item.occurredTime).format('MM-DD HH:mm:ss')
                      }}</span
                    ></small
                  ></span
                >
                <Tag :color="severityColor[item.severity]">
                  {{ severityText[item.severity] ?? item.severity }}
                </Tag>
                <AiStatusIndicator
                  :label="statusText[item.status] ?? item.status"
                  :status="item.status"
                  size="sm"
                />
                <IconifyIcon icon="lucide:chevron-right" class="event-arrow" />
              </button>
            </div>
            <div v-else class="events-empty">
              <Empty
                :image="Empty.PRESENTED_IMAGE_SIMPLE"
                :description="events ? t('noEvents') : unavailable('event')"
              />
            </div>
          </Card>
          <Card class="dashboard-card health-card" :bordered="false">
            <template #title>
              <h2>{{ t('healthTitle') }}</h2>
              <p class="card-caption">{{ t('healthDescription') }}</p>
            </template>
            <template #extra>
              <Button
                v-if="canRead('node')"
                type="link"
                size="small"
                @click="router.push('/ai-video/node')"
              >
                {{ t('manageNodes')
                }}<IconifyIcon icon="lucide:arrow-up-right" />
              </Button>
            </template>
            <div v-if="nodes?.length" class="resource-panel">
              <div class="node-summary">
                <span class="node-summary-icon"
                  ><IconifyIcon icon="lucide:server"
                /></span>
                <div>
                  <strong>{{
                    t('nodeOnlineCount', {
                      online: nodeOnline ?? 0,
                      total: nodes.length,
                    })
                  }}</strong>
                  <p>
                    {{ nodeOnline ? t('resourceScope') : t('allNodesOffline') }}
                  </p>
                </div>
                <AiStatusIndicator
                  :status="nodeOffline ? 'WARNING' : 'ONLINE'"
                  :label="
                    nodeOffline
                      ? t('offlineCount', { count: nodeOffline })
                      : t('allOnline')
                  "
                  size="sm"
                />
              </div>
              <div class="resource-list">
                <AiResourceGauge
                  label="CPU"
                  :value="resourceAverages.cpu"
                /><AiResourceGauge
                  :label="t('memory')"
                  :value="resourceAverages.memory"
                /><AiResourceGauge label="GPU" :value="resourceAverages.gpu" />
              </div>
            </div>
            <Empty
              v-else
              :image="Empty.PRESENTED_IMAGE_SIMPLE"
              :description="nodes ? t('noNodes') : unavailable('node')"
            >
              <Button
                v-if="nodes && canRead('node')"
                size="small"
                @click="router.push('/ai-video/node')"
              >
                {{ t('connectNode') }}
              </Button>
            </Empty>
            <div class="asset-links">
              <button
                type="button"
                :disabled="!canRead('model')"
                @click="router.push('/ai-video/model')"
              >
                <IconifyIcon icon="lucide:boxes" /><span>{{ t('models') }}</span
                ><strong>{{ valueOrDash(modelTotal) }}</strong
                ><IconifyIcon icon="lucide:chevron-right" />
              </button>
              <button
                type="button"
                :disabled="!canRead('algorithm')"
                @click="router.push('/ai-video/algorithm')"
              >
                <IconifyIcon icon="lucide:workflow" /><span>{{
                  t('algorithms')
                }}</span
                ><strong>{{ valueOrDash(algorithmTotal) }}</strong
                ><IconifyIcon icon="lucide:chevron-right" />
              </button>
            </div>
          </Card>
        </section>
        <footer class="dashboard-footnote">
          <IconifyIcon icon="lucide:info" />{{ t('sampleNote') }}
        </footer>
      </template>
    </main>
  </Page>
</template>

<style scoped>
.dashboard-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.dashboard-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}

.dashboard-updated {
  display: flex;
  gap: 5px;
  align-items: center;
  margin-right: 6px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.dashboard-updated.is-stale {
  color: var(--ai-warning);
}

.dashboard-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.dashboard-kpis :deep(.ai-metric-card) {
  min-height: 126px;
  padding: 16px 18px;
}

.dashboard-kpis :deep(.ai-metric-card__top) {
  width: 100%;
}

.dashboard-kpis :deep(.ai-metric-card__description) {
  max-width: 100%;
}

.dashboard-page button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
}

.dashboard-page button:focus-visible,
.trend-bar-area:focus-visible {
  outline: 2px solid hsl(var(--primary));
  outline-offset: 3px;
}

.attention-strip {
  display: flex;
  gap: 20px;
  align-items: center;
  padding: 8px 18px;
}

.attention-label {
  display: flex;
  flex-shrink: 0;
  gap: 8px;
  align-items: center;
  font-size: 12px;
  font-weight: 600;
}

.attention-label > svg {
  color: hsl(var(--primary));
}

.attention-items {
  display: grid;
  flex: 1;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.attention-items button {
  display: flex;
  gap: 8px;
  align-items: center;
  padding: 5px 10px;
  font-size: 12px;
  color: hsl(var(--muted-foreground));
  border-radius: 6px;
}

.attention-items button:hover,
.asset-links button:hover,
.recent-event:hover {
  background: hsl(var(--muted) / 55%);
}

.attention-items strong {
  margin-left: auto;
  font-size: 15px;
  color: hsl(var(--foreground));
}

.attention-items .attention-count {
  color: var(--ai-danger);
}

.attention-arrow {
  width: 12px;
  opacity: 0.55;
}

.dashboard-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.65fr) minmax(340px, 1fr);
  gap: 16px;
  align-items: stretch;
}

.dashboard-card {
  min-width: 0;
  border: 1px solid hsl(var(--border) / 60%);
  border-radius: var(--ai-radius-lg);
}

.dashboard-card :deep(.ant-card-head) {
  min-height: 68px;
}

.dashboard-card :deep(.ant-card-head-title) {
  padding-block: 13px;
  white-space: normal;
}

.dashboard-card :deep(.ant-card-extra) {
  margin-left: 12px;
}

.dashboard-card h2 {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: hsl(var(--foreground));
}

.card-caption {
  margin: 3px 0 0;
  font-size: 11px;
  font-weight: 400;
  line-height: 1.5;
  color: hsl(var(--muted-foreground));
}

.period-label {
  padding: 4px 10px;
  font-size: 11px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 7%);
  border-radius: 6px;
}

.trend-chart {
  display: flex;
  gap: 10px;
  height: 202px;
  padding: 14px 0 0;
}

.trend-axis {
  display: flex;
  flex-shrink: 0;
  flex-direction: column;
  justify-content: space-between;
  width: 24px;
  padding-bottom: 24px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  text-align: right;
}

.trend-plot {
  display: flex;
  flex: 1;
  min-width: 0;
  padding-top: 5px;
  background-image: repeating-linear-gradient(
    to top,
    hsl(var(--border) / 55%) 0,
    hsl(var(--border) / 55%) 1px,
    transparent 1px,
    transparent 25%
  );
  background-repeat: no-repeat;
  background-position: left 5px;
  background-size: 100% calc(100% - 29px);
}

.trend-column {
  position: relative;
  display: flex;
  flex: 1;
  flex-direction: column;
  align-items: center;
  min-width: 0;
}

.trend-bar-area {
  display: flex;
  flex: 1;
  align-items: flex-end;
  justify-content: center;
  width: 100%;
  min-height: 0;
  border-radius: 3px;
}

.trend-bar {
  position: relative;
  width: min(30px, 58%);
  min-height: 2px;
  background: linear-gradient(
    180deg,
    hsl(var(--primary) / 65%),
    hsl(var(--primary))
  );
  border-radius: 5px 5px 0 0;
}

.trend-bar-area:hover .trend-bar {
  opacity: 0.8;
}

.trend-value {
  position: absolute;
  top: -19px;
  width: 100%;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  text-align: center;
}

.trend-label {
  height: 24px;
  padding-top: 8px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  white-space: nowrap;
}

.chart-empty {
  display: grid;
  place-items: center;
  min-height: 202px;
}

.severity-list {
  display: grid;
  gap: 9px;
  align-content: space-between;
  min-height: 202px;
}

.severity-summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding-bottom: 9px;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  border-bottom: 1px solid hsl(var(--border) / 60%);
}

.severity-summary strong {
  font-size: 20px;
  line-height: 1;
  color: hsl(var(--foreground));
}

.severity-summary small {
  margin-left: 5px;
  font-size: 11px;
  font-weight: 400;
  color: hsl(var(--muted-foreground));
}

.severity-row {
  display: grid;
  grid-template-columns: 7px 32px minmax(30px, 1fr) 30px 34px;
  gap: 9px;
  align-items: center;
  font-size: 12px;
}

.severity-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
}

.severity-track {
  height: 6px;
  overflow: hidden;
  background: hsl(var(--muted));
  border-radius: 99px;
}

.severity-track > span {
  display: block;
  height: 100%;
  border-radius: inherit;
}

.severity-row strong,
.severity-row small {
  text-align: right;
}

.severity-row small {
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.pending-badge {
  padding: 2px 7px;
  font-size: 10px;
  font-weight: 500;
  color: var(--ai-danger);
  background: rgb(220 38 38 / 7%);
  border-radius: 5px;
}

.events-card :deep(.ant-card-body) {
  padding-block: 5px;
}

.recent-events {
  display: grid;
}

.recent-event {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) auto 76px 12px;
  gap: 12px;
  align-items: center;
  min-height: 59px;
  padding: 9px 4px;
  text-align: left;
  border-bottom: 1px solid hsl(var(--border) / 50%);
}

.recent-event:last-child {
  border-bottom: 0;
}

.event-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  color: hsl(var(--muted-foreground));
  background: hsl(var(--muted) / 65%);
  border-radius: 8px;
}

.event-icon--pending {
  color: var(--ai-warning);
  background: rgb(217 119 6 / 8%);
}

.recent-event__body {
  display: grid;
  gap: 3px;
  min-width: 0;
}

.recent-event__body strong {
  overflow: hidden;
  text-overflow: ellipsis;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.recent-event__body small {
  display: flex;
  flex-wrap: wrap;
  gap: 3px 12px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
  overflow-wrap: anywhere;
}

.event-time {
  white-space: nowrap;
}

.event-arrow {
  color: hsl(var(--muted-foreground));
}

.events-empty {
  display: grid;
  place-items: center;
  min-height: 270px;
}

.node-summary {
  display: flex;
  gap: 10px;
  align-items: center;
}

.node-summary-icon {
  display: grid;
  flex-shrink: 0;
  place-items: center;
  width: 34px;
  height: 34px;
  color: hsl(var(--primary));
  background: hsl(var(--primary) / 7%);
  border-radius: 8px;
}

.node-summary > div {
  flex: 1;
  min-width: 0;
}

.node-summary strong {
  font-size: 12px;
  font-weight: 600;
}

.node-summary p {
  margin: 3px 0 0;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.resource-list {
  display: grid;
  gap: 15px;
  margin-top: 20px;
}

.asset-links {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding-top: 14px;
  margin-top: 20px;
  border-top: 1px solid hsl(var(--border) / 60%);
}

.asset-links button {
  display: flex;
  gap: 7px;
  align-items: center;
  padding: 6px 0;
  font-size: 11px;
  color: hsl(var(--muted-foreground));
  border-radius: 5px;
}

.asset-links strong {
  margin-left: auto;
  font-size: 14px;
  color: hsl(var(--foreground));
}

.asset-links svg {
  flex-shrink: 0;
}

.dashboard-footnote {
  display: flex;
  gap: 6px;
  align-items: center;
  padding-inline: 2px;
  font-size: 10px;
  color: hsl(var(--muted-foreground));
}

.dashboard-footnote svg {
  flex-shrink: 0;
}

@media (width <= 1100px) {
  .dashboard-grid {
    grid-template-columns: minmax(0, 1.4fr) minmax(310px, 1fr);
  }

  .attention-strip {
    gap: 12px;
    padding-inline: 12px;
  }

  .attention-items {
    gap: 0;
  }

  .attention-items button {
    gap: 5px;
    padding-inline: 8px;
  }

  .recent-event {
    grid-template-columns: minmax(0, 1fr) auto 68px;
    gap: 8px;
  }

  .event-icon,
  .event-arrow {
    display: none;
  }

  .trend-column:nth-child(even) .trend-label {
    visibility: hidden;
  }
}

@media (width <= 900px) {
  .dashboard-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .dashboard-grid {
    grid-template-columns: minmax(0, 1fr);
  }

  .attention-strip {
    flex-direction: column;
    gap: 6px;
    align-items: flex-start;
  }

  .attention-items {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 2px 12px;
    width: 100%;
  }

  .trend-column:nth-child(even) .trend-label {
    visibility: visible;
  }
}

@media (width <= 480px) {
  .dashboard-page,
  .dashboard-kpis,
  .dashboard-grid {
    gap: 12px;
  }

  .dashboard-kpis :deep(.ai-metric-card) {
    padding: 12px;
  }

  .dashboard-kpis :deep(.ai-metric-card__description) {
    white-space: normal;
  }

  .dashboard-kpis :deep(.ai-metric-card__label) {
    font-size: 11px;
  }

  .dashboard-kpis :deep(.ai-metric-card__icon) {
    width: 24px;
    height: 24px;
  }

  .trend-column:nth-child(even) .trend-label {
    visibility: hidden;
  }

  .dashboard-footnote {
    align-items: flex-start;
  }
}
</style>
