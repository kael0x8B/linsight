<script setup lang="ts">
import type { AiVideoEventApi } from '#/api/ai-video/event';

import { computed, onBeforeUnmount, ref } from 'vue';

import { useAccess } from '@vben/access';
import { confirm, useVbenDrawer } from '@vben/common-ui';

import { Alert, Button, Card, Descriptions, DescriptionsItem, Empty, message, Segmented, Space, Spin, Switch, TabPane, Tabs, Tag, Timeline, TimelineItem } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { assignEvent, closeEvent, getEvent, handleEvent, markEventFalsePositive } from '#/api/ai-video/event';
import { getSimpleUserList } from '#/api/system/user';
import RecognitionFrame from '#/components/ai-video/recognition-frame.vue';

import { actionText, eventFrame, eventTypes, evidenceText, firstEvidence, formatTime, originalSnapshotAvailable, recognitionConfidence, recognitionScoreLabel, record, settingsSummary, severityColor, severityText, statusColor, statusText } from '../presentation';

const emit = defineEmits(['changed']);
const { hasAccessByCodes } = useAccess();
const detail = ref<AiVideoEventApi.Event>();
const loading = ref(false);
const busy = ref(false);
const failed = ref(false);
const videoFailed = ref(false);
const mediaMode = ref('snapshot');
const tab = ref('overview');
const showBoxes = ref(true);
const evidenceStage = ref<HTMLElement>();
async function enlargeEvidence() {
  if (document.fullscreenElement) await document.exitFullscreen();
  else await evidenceStage.value?.requestFullscreen();
}
const terminal = computed(() => ['CLOSED', 'FALSE_POSITIVE'].includes(detail.value?.status ?? ''));
const snapshot = computed(() => detail.value && firstEvidence(detail.value, 'SNAPSHOT'));
const video = computed(() => detail.value && firstEvidence(detail.value, 'VIDEO'));
const originalAvailable = computed(() => detail.value && originalSnapshotAvailable(detail.value));
const frame = computed(() => detail.value && { ...eventFrame(detail.value), objects: snapshot.value && !originalAvailable.value ? [] : eventFrame(detail.value).objects });
const settings = computed(() => detail.value ? settingsSummary(detail.value) : []);
const validation = computed(() => record(record(detail.value?.taskSnapshot).parameters).validationOnly === true);
const canAct = (action: string) => hasAccessByCodes([`ai-video:event:${action}`]);
let generation = 0;
let eventId: number | undefined;
let pollTimer: ReturnType<typeof setTimeout> | undefined;

const [ActionForm, formApi] = useVbenForm({
  layout: 'vertical', showDefaultActions: false,
  commonConfig: { componentProps: { class: 'w-full' }, formItemClass: 'col-span-2' },
  schema: [
    { fieldName: 'assigneeId', label: '处置人', component: 'ApiSelect', componentProps: { api: getSimpleUserList, labelField: 'nickname', valueField: 'id', allowClear: true, placeholder: '选择处置人' }, dependencies: { triggerFields: [''], show: () => canAct('assign') } },
    { fieldName: 'reasonCode', label: '处置原因', component: 'Select', componentProps: { allowClear: true, placeholder: '请选择原因', options: [ { label: '现场已确认', value: 'SITE_CONFIRMED' }, { label: '目标误识别', value: 'OBJECT_MISCLASSIFIED' }, { label: '识别区域不准确', value: 'ROI_INACCURATE' }, { label: '告警确认条件不合理', value: 'TEMPORAL_THRESHOLD' } ] } },
    { fieldName: 'remark', label: '处置说明', component: 'Textarea', componentProps: { rows: 3, maxlength: 1000, placeholder: '填写现场核实情况或误报原因' } },
  ],
});
function cancelPoll() { if (pollTimer) clearTimeout(pollTimer); pollTimer = undefined; }
async function refresh(manual = false) {
  if (!eventId) return;
  const request = generation; const id = eventId;
  if (manual || !detail.value) loading.value = true;
  try {
    const result = await getEvent(id);
    if (request !== generation) return;
    if (!manual && detail.value?.id === id) {
      result.media?.forEach(media => { const old = detail.value?.media?.find(item => item.id === media.id); if (old?.accessUrl) media.accessUrl = old.accessUrl; });
    }
    detail.value = result; failed.value = false;
    if (manual) videoFailed.value = false;
  } catch { if (request === generation) failed.value = true; }
  finally {
    if (request === generation) {
      loading.value = false; cancelPoll();
      if (!detail.value || ['PARTIAL', 'PENDING'].includes(detail.value.evidenceStatus)) pollTimer = setTimeout(() => void refresh(), 5000);
    }
  }
}
const [Drawer, drawerApi] = useVbenDrawer({
  showConfirmButton: false, showCancelButton: false,
  onOpenChange(open) {
    generation += 1; cancelPoll();
    if (!open) { eventId = undefined; return; }
    eventId = drawerApi.getData<{ id: number }>().id;
    detail.value = undefined; failed.value = false; videoFailed.value = false;
    mediaMode.value = 'snapshot'; tab.value = 'overview'; showBoxes.value = true;
    void formApi.resetForm(); void refresh();
  },
});
async function submitAction(type: 'assign' | 'close' | 'false-positive' | 'handle') {
  if (!detail.value || busy.value || terminal.value || !canAct(type)) return;
  const action = await formApi.getValues() as AiVideoEventApi.EventActionRequest;
  if (type === 'assign' && !action.assigneeId) { message.warning('请选择处置人'); return; }
  if (type !== 'assign' && !action.remark?.trim()) { message.warning('请填写处置说明'); return; }
  if (type === 'false-positive' && !action.reasonCode) { message.warning('请选择误报原因'); return; }
  if (type === 'close') await confirm(`确认关闭事件“${detail.value.eventNo}”吗？关闭后处理记录将保留。`);
  if (type === 'false-positive') await confirm(`确认将事件“${detail.value.eventNo}”标记为误报吗？该结果将用于后续复核。`);
  busy.value = true;
  try {
    const api = { assign: assignEvent, close: closeEvent, 'false-positive': markEventFalsePositive, handle: handleEvent }[type];
    await api(detail.value.id, action); message.success('事件处理结果已保存'); await refresh(); emit('changed');
  } catch { message.warning('操作未完成，请刷新事件核对最新状态；已填写的内容已保留。'); }
  finally { busy.value = false; }
}
onBeforeUnmount(() => { generation += 1; cancelPoll(); });
</script>

<template>
  <Drawer title="事件详情与处置" class="w-[1440px] max-w-[calc(100vw-32px)]" :footer="false">
    <Alert v-if="failed" class="mb-4" message="事件或证据暂时加载失败" description="请刷新重试，已填写的处置内容会保留。" type="error" show-icon><template #action><Button @click="refresh(true)">重试</Button></template></Alert>
    <Spin :spinning="loading">
      <template v-if="detail">
        <header class="event-summary">
          <div>
<div class="event-summary__title"><h2>{{ eventTypes[detail.eventType] || '识别事件' }}</h2><Tag :color="severityColor[detail.severity]">{{ severityText[detail.severity] || '未分级' }}</Tag><Tag :color="statusColor[detail.status]">{{ statusText[detail.status] || '状态待确认' }}</Tag><Tag v-if="validation" color="orange">现场验证</Tag></div>
            <p>{{ detail.cameraName || `摄像头 ${detail.cameraId}` }} · {{ formatTime(detail.occurredTime) }}（北京时间）</p>
          </div>
          <Button :loading="loading" @click="refresh(true)">刷新证据</Button>
        </header>
        <div class="event-workspace">
          <main class="event-evidence">
            <div class="evidence-toolbar"><Segmented v-model:value="mediaMode" :options="[{ label: '告警截图', value: 'snapshot' }, { label: video?.accessUrl ? (detail.eventType.startsWith('ENTRY_') ? '本次核验录像' : '前后录像') : '录像未到达', value: 'video', disabled: !video?.accessUrl }]" /><label v-if="mediaMode === 'snapshot'"><Switch v-model:checked="showBoxes" size="small" />标出告警目标</label></div>
            <Button size="small" class="mb-2" @click="enlargeEvidence">放大证据</Button>
            <div ref="evidenceStage" class="evidence-stage">
              <RecognitionFrame v-if="mediaMode === 'snapshot'" historical :context-label="snapshot && !originalAvailable ? '历史图片，时间可能不同' : undefined" empty-result-text="目标标记不可用" :frame="frame" :source="snapshot?.accessUrl" :show-boxes="showBoxes" :show-all-objects="true" :title="snapshot && !originalAvailable ? '历史截图（原图已被覆盖）' : `${eventTypes[detail.eventType] || '识别事件'} · 告警截图`" empty-text="告警截图尚未到达，系统会自动刷新。" />
              <video v-else-if="video?.accessUrl && !videoFailed" controls :src="video.accessUrl" :poster="snapshot?.accessUrl" @error="videoFailed = true"></video>
              <Empty v-else description="录像暂时无法播放，请刷新证据重试。" />
            </div>
            <Alert v-if="snapshot && !originalAvailable" class="mt-3" type="warning" show-icon message="这条历史告警的原始截图已被旧版本覆盖" description="当前图片只能辅助查看，无法准确还原事发时的目标位置，因此不显示识别框。修复后的新事件将独立保存原图。" />
            <Alert v-if="mediaMode === 'video' && video?.originalContentAvailable === false" class="mt-3" type="warning" show-icon message="这段历史录像已被旧版本替换，无法作为原始事件录像使用。" />
            <div class="evidence-note"><Tag :color="detail.evidenceStatus === 'READY' ? 'green' : 'orange'">{{ evidenceText[detail.evidenceStatus] || '证据状态待确认' }}</Tag><span>{{ mediaMode === 'video' ? (detail.eventType.startsWith('ENTRY_') ? '录像仅覆盖本次主动核验；目标标记见告警截图。' : '录像用于查看事发前后过程；目标标记见告警截图。') : snapshot && !originalAvailable ? '历史证据异常，目标标记已隐藏。' : !frame?.objects.length ? '该历史事件未保存有效目标坐标，暂时无法标框。' : '框的位置来自这次告警的识别结果，可放大查看。' }}</span><span v-if="!video?.accessUrl">录像尚未到达，请稍后刷新。</span></div>
            <Tabs v-model:active-key="tab" class="event-tabs">
              <TabPane key="overview" tab="识别结论">
                <div class="conclusion"><span>告警目标</span><strong>{{ eventTypes[detail.eventType] || '识别事件' }}</strong><span>{{ recognitionScoreLabel(detail) }}</span><strong>{{ recognitionConfidence(detail) }}</strong></div>
                <Descriptions :column="2" size="small">
                  <DescriptionsItem label="识别任务">{{ detail.taskName || detail.taskSnapshot?.name || (detail.taskId ? `任务 ${detail.taskId}` : '主动入口核验') }}</DescriptionsItem>
                  <DescriptionsItem label="确认持续时间">{{ (detail.durationMs / 1000).toFixed(1) }} 秒</DescriptionsItem>
                  <DescriptionsItem label="首次观察">{{ formatTime(detail.firstSeenTime) }}</DescriptionsItem>
                  <DescriptionsItem label="告警确认">{{ formatTime(detail.occurredTime) }}</DescriptionsItem>
                </Descriptions>
                <p v-if="validation" class="muted">该能力处于现场验证阶段，请结合截图核实识别结果。</p>
              </TabPane>
              <TabPane key="object" tab="识别目标">
                <Descriptions :column="2" size="small">
                  <DescriptionsItem label="目标类型">{{ detail.objectSnapshot?.class === 'person' ? '人员' : '检测目标' }}</DescriptionsItem>
                  <DescriptionsItem v-if="detail.eventType.startsWith('ENTRY_')" label="登记人员">{{ detail.objectSnapshot?.personName || '身份未确认' }}</DescriptionsItem>
                  <DescriptionsItem label="目标编号">{{ detail.trackId?.replace('track-', '') || '未记录' }}</DescriptionsItem>
                  <DescriptionsItem label="识别结论">{{ eventTypes[detail.eventType] || '识别事件' }}</DescriptionsItem>
                  <DescriptionsItem :label="recognitionScoreLabel(detail)">{{ recognitionConfidence(detail) }}</DescriptionsItem>
                </Descriptions>
                <p class="muted">截图只标出触发本次告警的目标，画面中的其他人员不代表本次事件的告警对象。</p>
              </TabPane>
              <TabPane key="settings" tab="告警条件">
                <p class="muted">以下为事件发生时使用的设置，后续调整不会改变本次记录。</p>
                <dl class="settings-list"><template v-for="item in settings" :key="item.label"><dt>{{ item.label }}</dt><dd>{{ item.value }}</dd></template></dl>
              </TabPane>
              <TabPane key="history" tab="处理记录">
                <Timeline v-if="detail.actions?.length"><TimelineItem v-for="item in detail.actions" :key="item.id"><strong>{{ actionText[item.actionType] || '状态更新' }}</strong><Tag class="ml-2">{{ statusText[item.toStatus] || '状态待确认' }}</Tag><p class="muted">{{ formatTime(item.createTime) }}</p><p v-if="item.remark">{{ item.remark === 'Runtime 规则状态机确认告警' ? '系统根据连续识别结果确认告警' : item.remark === 'Runtime 规则状态变更' ? '系统根据后续识别结果更新事件状态' : item.remark }}</p></TimelineItem></Timeline><Empty v-else description="暂无处理记录" />
              </TabPane>
            </Tabs>
          </main>
          <aside class="event-actions">
<Card title="处置操作" size="small">
            <Alert v-if="terminal" message="事件已结束" description="可在处理记录中查看完整过程。" type="success" show-icon />
            <Alert v-else-if="!['assign', 'handle', 'close', 'false-positive'].some(canAct)" message="当前账号可查看事件，没有处置权限。" type="info" show-icon />
            <template v-else><ActionForm /><Space wrap><Button v-if="canAct('handle')" type="primary" :loading="busy" @click="submitAction('handle')">完成处置</Button><Button v-if="canAct('assign')" :disabled="busy" @click="submitAction('assign')">指派</Button><Button v-if="canAct('close')" :disabled="busy" @click="submitAction('close')">关闭事件</Button><Button v-if="canAct('false-positive')" danger :disabled="busy" @click="submitAction('false-positive')">标记误报</Button></Space></template>
          </Card><div class="event-reference"><span>事件编号</span><code>{{ detail.eventNo }}</code><span>处理结果</span><p>{{ detail.handlingResult || detail.falsePositiveReason || '暂无人工处置结论' }}</p></div>
</aside>
        </div>
      </template>
      <div v-else class="initial-loading">正在加载事件详情…</div>
    </Spin>
  </Drawer>
</template>

<style scoped>
.event-summary { display: flex; gap: 16px; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.event-summary__title { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.event-summary h2 { margin: 0 8px 0 0; font-size: 23px; font-weight: 650; }
.event-summary p { margin: 8px 0 0; color: hsl(var(--muted-foreground)); }
.event-workspace { display: grid; grid-template-columns: minmax(0, 1fr) 300px; gap: 20px; }
.event-evidence { min-width: 0; }
.evidence-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.evidence-toolbar label { display: inline-flex; gap: 8px; align-items: center; font-size: 13px; }
.evidence-stage { height: min(52vh, 580px); min-height: 300px; overflow: hidden; background: #030711; border-radius: 8px; }
.evidence-stage video { width: 100%; height: 100%; object-fit: contain; }
.evidence-note { display: flex; flex-wrap: wrap; gap: 6px; margin: 12px 0; font-size: 12px; color: hsl(var(--muted-foreground)); }
.event-tabs { padding: 0 16px 16px; border: 1px solid hsl(var(--border)); border-radius: 8px; }
.conclusion { display: flex; flex-wrap: wrap; gap: 8px 16px; align-items: center; padding: 12px; margin-bottom: 16px; background: hsl(var(--muted)); border-radius: 6px; }
.conclusion strong { margin-right: 20px; font-size: 18px; }
.muted { margin: 8px 0; font-size: 12px; color: hsl(var(--muted-foreground)); }
.settings-list { display: grid; grid-template-columns: 126px minmax(0, 1fr); gap: 12px; margin: 16px 0 0; font-size: 13px; }
.settings-list dt { color: hsl(var(--muted-foreground)); }
.settings-list dd { margin: 0; }
.event-reference { display: flex; flex-direction: column; gap: 8px; padding: 20px 12px; overflow-wrap: anywhere; }
.event-reference span { font-size: 12px; color: hsl(var(--muted-foreground)); }
.event-reference code { margin-bottom: 8px; font-size: 11px; }
.initial-loading { min-height: 320px; padding: 80px 24px; text-align: center; }
@media (max-width: 1000px) { .event-workspace { grid-template-columns: 1fr; } .event-summary { align-items: flex-start; } .evidence-stage { height: 45vh; } }
</style>
