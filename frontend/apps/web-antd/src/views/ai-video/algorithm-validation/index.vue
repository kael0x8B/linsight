<script lang="ts" setup>
import type { AiVideoAlgorithmApi } from '#/api/ai-video/algorithm';
import type { AiVideoTaskApi } from '#/api/ai-video/task';

import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { Page } from '@vben/common-ui';
import { IconifyIcon } from '@vben/icons';

import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  DescriptionsItem,
  Divider,
  Form,
  FormItem,
  Input,
  InputNumber,
  message,
  Progress,
  Row,
  Select,
  Space,
  Statistic,
  Steps,
  Switch,
  Tag,
} from 'ant-design-vue';

import {
  getPipelineVersions,
  getRunnableAlgorithms,
  publishPipeline,
  savePipeline,
  validatePipeline,
} from '#/api/ai-video/algorithm';
import { getEventPage } from '#/api/ai-video/event';
import { getTaskPage } from '#/api/ai-video/task';
import { AiPageHeader } from '#/components/ai-video';

const router = useRouter();

const { hasAccessByCodes } = useAccess();
const canRecord = computed(() =>
  hasAccessByCodes(['ai-video:algorithm:update', 'ai-video:algorithm:publish']),
);

const loading = ref(false);
const saving = ref(false);
const algorithms = ref<AiVideoAlgorithmApi.Algorithm[]>([]);
const tasks = ref<AiVideoTaskApi.Task[]>([]);
const selectedAlgorithmId = ref<number>();
const selectedTaskId = ref<number>();
const taskEventTotal = ref(0);
const falsePositiveTotal = ref(0);

const form = reactive({
  averageFps: 1,
  acceleratorMemoryPeakMiB: 0,
  cooldownDedupPass: false,
  cpuPeakPercent: 0,
  datasetSha256: '',
  datasetVersion: '',
  endToEndP95Ms: 0,
  eventPrecision: 0,
  eventRecall: 0,
  evidenceRef: '',
  falsePositivesPerStreamHour: 0,
  maxEndToEndP95Ms: 1500,
  maxFalsePositivesPerStreamHour: 1,
  maxMissedEvents: 0,
  memoryPeakMiB: 0,
  minAverageFps: 1,
  minEventPrecision: 0.9,
  minEventRecall: 0.9,
  missedEvents: 0,
  note: '',
});

const selectedAlgorithm = computed(() =>
  algorithms.value.find((item) => item.id === selectedAlgorithmId.value),
);
const selectedTask = computed(() =>
  tasks.value.find((item) => item.id === selectedTaskId.value),
);
const availableTasks = computed(() =>
  tasks.value.filter((item) => item.algorithmId === selectedAlgorithmId.value),
);
const evidenceComplete = computed(
  () =>
    Boolean(selectedTaskId.value) &&
    Boolean(form.datasetVersion.trim()) &&
    /^[a-fA-F0-9]{64}$/.test(form.datasetSha256.trim()) &&
    Boolean(form.evidenceRef.trim()) &&
    form.memoryPeakMiB > 0 &&
    form.averageFps > 0,
);
const metricsPass = computed(
  () =>
    evidenceComplete.value &&
    form.eventPrecision >= form.minEventPrecision &&
    form.eventRecall >= form.minEventRecall &&
    form.falsePositivesPerStreamHour <= form.maxFalsePositivesPerStreamHour &&
    form.missedEvents <= form.maxMissedEvents &&
    form.endToEndP95Ms <= form.maxEndToEndP95Ms &&
    form.averageFps >= form.minAverageFps &&
    form.cooldownDedupPass,
);
const completionPercent = computed(() => {
  const checks = [
    Boolean(selectedAlgorithmId.value),
    Boolean(selectedTaskId.value),
    Boolean(form.datasetVersion.trim()),
    /^[a-fA-F0-9]{64}$/.test(form.datasetSha256.trim()),
    Boolean(form.evidenceRef.trim()),
    form.memoryPeakMiB > 0,
    form.averageFps > 0,
    form.cooldownDedupPass,
  ];
  return Math.round((checks.filter(Boolean).length / checks.length) * 100);
});

async function loadBaseData() {
  loading.value = true;
  try {
    const [algorithmList, taskPage] = await Promise.all([
      getRunnableAlgorithms(),
      getTaskPage({ pageNo: 1, pageSize: 100 }),
    ]);
    algorithms.value = algorithmList;
    tasks.value = taskPage.list;
    selectedAlgorithmId.value ??= algorithmList[0]?.id;
  } finally {
    loading.value = false;
  }
}

async function loadObservedEvents() {
  taskEventTotal.value = 0;
  falsePositiveTotal.value = 0;
  if (!selectedTaskId.value) return;
  const [allEvents, falsePositives] = await Promise.all([
    getEventPage({ pageNo: 1, pageSize: 1, taskId: selectedTaskId.value }),
    getEventPage({
      pageNo: 1,
      pageSize: 1,
      status: 'FALSE_POSITIVE',
      taskId: selectedTaskId.value,
    }),
  ]);
  taskEventTotal.value = allEvents.total;
  falsePositiveTotal.value = falsePositives.total;
}

watch(selectedAlgorithmId, () => {
  if (!availableTasks.value.some((item) => item.id === selectedTaskId.value)) {
    selectedTaskId.value = availableTasks.value[0]?.id;
  }
});
watch(selectedTaskId, () => void loadObservedEvents());

function acceptancePayload() {
  return {
    cooldownDedupPass: form.cooldownDedupPass,
    datasetSha256: form.datasetSha256.trim().toLowerCase(),
    datasetVersion: form.datasetVersion.trim(),
    evidenceRef: form.evidenceRef.trim(),
    metrics: {
      averageFps: form.averageFps,
      endToEndP95Ms: form.endToEndP95Ms,
      eventPrecision: form.eventPrecision,
      eventRecall: form.eventRecall,
      falsePositivesPerStreamHour: form.falsePositivesPerStreamHour,
      missedEvents: form.missedEvents,
    },
    note: form.note.trim(),
    observedEventCount: taskEventTotal.value,
    observedFalsePositiveCount: falsePositiveTotal.value,
    resourceUsage: {
      acceleratorMemoryPeakMiB: form.acceleratorMemoryPeakMiB,
      cpuPeakPercent: form.cpuPeakPercent,
      memoryPeakMiB: form.memoryPeakMiB,
    },
    source: 'VIDEO_ACCEPTANCE',
    status: metricsPass.value ? 'PASS' : 'PENDING',
    taskId: selectedTaskId.value,
    thresholds: {
      maxEndToEndP95Ms: form.maxEndToEndP95Ms,
      maxFalsePositivesPerStreamHour: form.maxFalsePositivesPerStreamHour,
      maxMissedEvents: form.maxMissedEvents,
      minAverageFps: form.minAverageFps,
      minEventPrecision: form.minEventPrecision,
      minEventRecall: form.minEventRecall,
    },
    validatedAt: new Date().toISOString(),
  };
}

async function saveAcceptance() {
  if (
    !selectedAlgorithm.value?.currentPipelineVersionId ||
    !selectedTaskId.value
  ) {
    message.warning('请先选择已发布 Pipeline 的算法和对应任务');
    return;
  }
  if (!evidenceComplete.value) {
    message.warning('请补齐固定测试集、SHA256、证据引用和资源指标');
    return;
  }
  saving.value = true;
  try {
    const versions = await getPipelineVersions(selectedAlgorithm.value.id);
    const current = versions.find(
      (item) => item.id === selectedAlgorithm.value?.currentPipelineVersionId,
    );
    if (!current) throw new Error('当前 Pipeline 版本不存在');
    const dag = JSON.parse(JSON.stringify(current.dag)) as Record<
      string,
      unknown
    >;
    dag.acceptance = acceptancePayload();
    const versionId = await savePipeline({
      algorithmId: selectedAlgorithm.value.id,
      dag,
    });
    const errors = await validatePipeline(versionId);
    if (errors.length > 0) {
      message.error(errors.join('；'));
      return;
    }
    if (metricsPass.value) {
      await publishPipeline(versionId);
      message.success('视频验收通过，已发布带验收证据的新 Pipeline 版本');
    } else {
      message.warning('已保存为待验收版本；指标达标并补齐证据后才能发布');
    }
    await loadBaseData();
  } finally {
    saving.value = false;
  }
}

onMounted(async () => {
  await loadBaseData();
  await loadObservedEvents();
});
</script>

<template>
  <Page auto-content-height>
    <div class="ai-page ai-page-stack h-full">
      <AiPageHeader
        title="视频识别验收"
        description="使用测试集和现场指标验证识别效果。"
        icon="lucide:clipboard-check"
      >
        <template #extra>
          <Button @click="router.push('/ai-video/task')">任务中心</Button>
          <Button
            type="primary"
            :disabled="!canRecord || !evidenceComplete"
            :loading="saving"
            @click="saveAcceptance"
          >
            <IconifyIcon icon="lucide:save" />记录验收
          </Button>
        </template>
      </AiPageHeader>

      <Steps
        :current="
          metricsPass ? 3 : selectedTaskId ? 2 : selectedAlgorithmId ? 1 : 0
        "
        :items="[
          { title: '选择能力' },
          { title: '绑定任务' },
          { title: '填写实测指标' },
          { title: '发布验收版本' },
        ]"
      />

      <Row :gutter="16">
        <Col :span="8">
          <Card title="1. 选择测试对象" :loading="loading">
            <Form layout="vertical">
              <FormItem label="动态 AI 能力" required>
                <Select
                  v-model:value="selectedAlgorithmId"
                  show-search
                  :field-names="{ label: 'name', value: 'id' }"
                  :options="algorithms"
                  option-filter-prop="name"
                />
              </FormItem>
              <FormItem label="真实视频任务" required>
                <Select
                  v-model:value="selectedTaskId"
                  :field-names="{ label: 'name', value: 'id' }"
                  :options="availableTasks"
                  placeholder="先在任务中心创建并运行任务"
                />
              </FormItem>
            </Form>
            <Descriptions bordered :column="1" size="small">
              <DescriptionsItem label="能力编码">
                {{ selectedAlgorithm?.code ?? '-' }}
              </DescriptionsItem>
              <DescriptionsItem label="Pipeline 状态">
                <Tag
                  :color="
                    selectedAlgorithm?.pipelineAcceptanceStatus === 'PASS'
                      ? 'green'
                      : 'orange'
                  "
                >
                  {{
                    selectedAlgorithm?.pipelineAcceptanceStatus ?? 'UNPUBLISHED'
                  }}
                </Tag>
              </DescriptionsItem>
              <DescriptionsItem label="任务状态">
                {{ selectedTask?.actualStatus ?? '-' }}
              </DescriptionsItem>
            </Descriptions>
            <Divider />
            <Row :gutter="12">
              <Col :span="12">
                <Statistic title="任务已产出事件" :value="taskEventTotal" />
              </Col>
              <Col :span="12">
                <Statistic title="已标记误报" :value="falsePositiveTotal" />
              </Col>
            </Row>
          </Card>

          <Card class="mt-4" title="验收完整度">
            <Progress
              :percent="completionPercent"
              :status="metricsPass ? 'success' : 'active'"
            />
            <Alert
              class="mt-4"
              :message="
                metricsPass
                  ? '指标达到所填阈值，可以发布验收版本。'
                  : '仍有证据未填写或指标未达到阈值。'
              "
              :type="metricsPass ? 'success' : 'info'"
              show-icon
            />
          </Card>
        </Col>

        <Col :span="16">
          <Card title="2. 固定测试集与证据">
            <Form layout="vertical">
              <Row :gutter="16">
                <Col :span="8">
                  <FormItem label="测试集版本" required>
                    <Input
                      v-model:value="form.datasetVersion"
                      placeholder="例如 plant-a-v1"
                    />
                  </FormItem>
                </Col>
                <Col :span="16">
                  <FormItem label="测试集 SHA256" required>
                    <Input
                      v-model:value="form.datasetSha256"
                      :maxlength="64"
                      placeholder="64 位 SHA256"
                    />
                  </FormItem>
                </Col>
                <Col :span="24">
                  <FormItem label="视频/报告证据引用" required>
                    <Input
                      v-model:value="form.evidenceRef"
                      placeholder="对象存储引用、内部报告编号或受控文件路径"
                    />
                  </FormItem>
                </Col>
              </Row>
            </Form>
          </Card>

          <Card class="mt-4" title="3. 实测指标与验收阈值">
            <Form layout="vertical">
              <Row :gutter="16">
                <Col :span="8">
                  <FormItem label="事件准确率">
                    <InputNumber
                      v-model:value="form.eventPrecision"
                      :min="0"
                      :max="1"
                      :step="0.01"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="最低准确率">
                    <InputNumber
                      v-model:value="form.minEventPrecision"
                      :min="0"
                      :max="1"
                      :step="0.01"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="事件召回率">
                    <InputNumber
                      v-model:value="form.eventRecall"
                      :min="0"
                      :max="1"
                      :step="0.01"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="最低召回率">
                    <InputNumber
                      v-model:value="form.minEventRecall"
                      :min="0"
                      :max="1"
                      :step="0.01"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="每路每小时误报">
                    <InputNumber
                      v-model:value="form.falsePositivesPerStreamHour"
                      :min="0"
                      :step="0.1"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="允许最大误报">
                    <InputNumber
                      v-model:value="form.maxFalsePositivesPerStreamHour"
                      :min="0"
                      :step="0.1"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="漏报事件数">
                    <InputNumber
                      v-model:value="form.missedEvents"
                      :min="0"
                      :precision="0"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="允许最大漏报">
                    <InputNumber
                      v-model:value="form.maxMissedEvents"
                      :min="0"
                      :precision="0"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="端到端 P95(ms)">
                    <InputNumber v-model:value="form.endToEndP95Ms" :min="0" />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="最大 P95(ms)">
                    <InputNumber
                      v-model:value="form.maxEndToEndP95Ms"
                      :min="1"
                      :max="1999"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="平均分析 FPS">
                    <InputNumber
                      v-model:value="form.averageFps"
                      :min="0.1"
                      :step="0.1"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="最低分析 FPS">
                    <InputNumber
                      v-model:value="form.minAverageFps"
                      :min="0.1"
                      :step="0.1"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="CPU 峰值(%)">
                    <InputNumber
                      v-model:value="form.cpuPeakPercent"
                      :min="0"
                      :max="100"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="内存峰值(MiB)">
                    <InputNumber v-model:value="form.memoryPeakMiB" :min="0" />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="加速器显存峰值(MiB)">
                    <InputNumber
                      v-model:value="form.acceleratorMemoryPeakMiB"
                      :min="0"
                    />
                  </FormItem>
                </Col>
                <Col :span="8">
                  <FormItem label="冷却与去重验证">
                    <Switch
                      v-model:checked="form.cooldownDedupPass"
                      checked-children="通过"
                      un-checked-children="未通过"
                    />
                  </FormItem>
                </Col>
                <Col :span="24">
                  <FormItem label="验收备注">
                    <Input.TextArea
                      v-model:value="form.note"
                      :rows="3"
                      placeholder="记录测试摄像头、光照、遮挡、硬件和异常样本情况"
                    />
                  </FormItem>
                </Col>
              </Row>
            </Form>
            <Space>
              <Tag :color="metricsPass ? 'green' : 'orange'">
                {{ metricsPass ? 'PASS' : 'PENDING' }}
              </Tag>
              <span class="text-muted-foreground"
                >结论由当前指标与可编辑阈值实时计算，服务端会再次校验。</span
              >
            </Space>
          </Card>
        </Col>
      </Row>
    </div>
  </Page>
</template>

<style scoped>
:deep(.ant-input-number) {
  width: 100%;
}
</style>
