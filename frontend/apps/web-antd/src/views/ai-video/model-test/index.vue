<script lang="ts" setup>
import type { UploadFile } from 'ant-design-vue';

import type { AiVideoModelApi } from '#/api/ai-video/model';
import type { AiVideoNodeSimple } from '#/api/ai-video/node';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { useAccess } from '@vben/access';
import { Page } from '@vben/common-ui';

import {
  Alert,
  Button,
  Card,
  Descriptions,
  DescriptionsItem,
  Empty,
  Form,
  FormItem,
  InputNumber,
  message,
  Select,
  Spin,
  Table,
  Tag,
  Upload,
} from 'ant-design-vue';

import {
  createModelTest,
  deployModelVersion,
  getModelDeployments,
  getModelPage,
  getModelTest,
  getModelTests,
  getModelVersionList,
} from '#/api/ai-video/model';
import { getNodeSimpleList } from '#/api/ai-video/node';
import { AiPageHeader, AiStatusIndicator } from '#/components/ai-video';
import { $t } from '#/locales';

import {
  deploymentStatusText,
  isDeploymentPending,
} from '../model/deployment-status';

interface StandardObject {
  attributes: Record<string, boolean | null | number | string>;
  bbox: { height: number; width: number; x: number; y: number };
  class: string;
  confidence: number;
}

interface StandardResult {
  objects: StandardObject[];
  schemaVersion: '1.0';
  sourceHeight: number;
  sourceWidth: number;
}

const { hasAccessByCodes } = useAccess();
const canDeploy = computed(() => hasAccessByCodes(['ai-video:model:deploy']));
const canTest = computed(() => hasAccessByCodes(['ai-video:model:test']));
const loading = ref(false);
const error = ref('');
const deploymentSubmitting = ref(false);
const deploymentRefreshError = ref('');
let disposed = false;
const models = ref<AiVideoModelApi.Model[]>([]);
const versions = ref<AiVideoModelApi.ModelVersion[]>([]);
const nodes = ref<AiVideoNodeSimple[]>([]);
const deployments = ref<AiVideoModelApi.ModelDeployment[]>([]);
const tests = ref<AiVideoModelApi.ModelTest[]>([]);
const selectedModelId = ref<number>();
const selectedVersionId = ref<number>();
const selectedNodeId = ref<number>();
const uploadFiles = ref<UploadFile[]>([]);
const previewUrl = ref('');
const currentTest = ref<AiVideoModelApi.ModelTest>();
const confidence = ref(0.5);
const nmsThreshold = ref(0.5);
const inputWidth = ref(640);
const inputHeight = ref(640);
let pollTimer: ReturnType<typeof setTimeout> | undefined;
let deploymentPollTimer: ReturnType<typeof setTimeout> | undefined;

const selectedDeployment = computed(() =>
  deployments.value.find((item) => item.nodeId === selectedNodeId.value),
);
const selectedModel = computed(() =>
  models.value.find((item) => item.id === selectedModelId.value),
);
const selectedVersion = computed(() =>
  versions.value.find((item) => item.id === selectedVersionId.value),
);
const versionPublished = computed(
  () => selectedVersion.value?.publishStatus === 'PUBLISHED',
);
const nodeReady = computed(
  () => selectedDeployment.value?.actualStatus === 'READY',
);
const standardResult = computed<StandardResult | undefined>(() => {
  if (!currentTest.value?.result) return undefined;
  try {
    return JSON.parse(currentTest.value.result) as StandardResult;
  } catch {
    return undefined;
  }
});

async function loadInitial() {
  loading.value = true;
  error.value = '';
  try {
    const [modelPage, nodeList] = await Promise.all([
      getModelPage({ pageNo: 1, pageSize: 100, status: 0 }),
      getNodeSimpleList(),
    ]);
    models.value = modelPage.list;
    nodes.value = nodeList;
    selectedModelId.value = modelPage.list[0]?.id;
    selectedNodeId.value = nodeList.find((node) => node.onlineStatus === 1)?.id;
  } catch {
    error.value = '单图测试初始化失败，请检查控制面和节点状态。';
  } finally {
    loading.value = false;
  }
}

async function loadVersions() {
  deployments.value = [];
  tests.value = [];
  currentTest.value = undefined;
  selectedVersionId.value = undefined;
  if (!selectedModelId.value) {
    versions.value = [];
    return;
  }
  const versionList = await getModelVersionList(selectedModelId.value);
  versions.value = versionList;
  selectedVersionId.value =
    versionList.find((item) => item.publishStatus === 'PUBLISHED')?.id ??
    selectedModel.value?.currentVersionId ??
    versionList[0]?.id;
}

async function loadExecutionState() {
  deployments.value = [];
  tests.value = [];
  currentTest.value = undefined;
  if (!selectedVersionId.value) return;
  [deployments.value, tests.value] = await Promise.all([
    getModelDeployments(selectedVersionId.value),
    getModelTests(selectedVersionId.value),
  ]);
}

async function deploy() {
  if (deploymentSubmitting.value) return;
  if (!selectedVersionId.value || !selectedNodeId.value) return;
  if (!versionPublished.value) {
    message.warning('请先在模型资产页发布该版本');
    return;
  }
  deploymentSubmitting.value = true;
  try {
    await deployModelVersion(selectedVersionId.value, selectedNodeId.value);
    message.success('部署命令已进入节点耐久队列');
    await loadExecutionState();
  } finally {
    deploymentSubmitting.value = false;
    scheduleDeploymentPoll();
  }
}

function scheduleDeploymentPoll() {
  if (deploymentPollTimer) clearTimeout(deploymentPollTimer);
  if (disposed || !selectedVersionId.value || nodeReady.value) return;
  const versionId = selectedVersionId.value;
  deploymentPollTimer = setTimeout(async () => {
    try {
      const result = await getModelDeployments(versionId);
      if (disposed || versionId !== selectedVersionId.value) return;
      deployments.value = result;
      deploymentRefreshError.value = '';
    } catch {
      deploymentRefreshError.value = $t('model-deployment.refreshFailed');
    }
    if (
      deploymentRefreshError.value ||
      isDeploymentPending(selectedDeployment.value?.actualStatus)
    )
      scheduleDeploymentPoll();
  }, 1500);
}

function handleFileChanged() {
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  const file = uploadFiles.value[0]?.originFileObj;
  previewUrl.value = file ? URL.createObjectURL(file) : '';
}

async function runTest() {
  const image = uploadFiles.value[0]?.originFileObj;
  if (!selectedVersionId.value || !selectedNodeId.value || !image) {
    message.warning('请选择版本、在线节点和测试图片');
    return;
  }
  if (!nodeReady.value) {
    message.warning('模型必须先在所选节点进入 ready 状态');
    return;
  }
  loading.value = true;
  try {
    const id = await createModelTest({
      confidence: confidence.value,
      image,
      inputHeight: inputHeight.value,
      inputWidth: inputWidth.value,
      modelVersionId: selectedVersionId.value,
      nmsThreshold: nmsThreshold.value,
      nodeId: selectedNodeId.value,
    });
    currentTest.value = await getModelTest(id);
    schedulePoll(id);
    await loadExecutionState();
  } finally {
    loading.value = false;
  }
}

function schedulePoll(id: number) {
  if (pollTimer) clearTimeout(pollTimer);
  pollTimer = setTimeout(async () => {
    currentTest.value = await getModelTest(id);
    if (['QUEUED', 'RUNNING'].includes(currentTest.value.status))
      schedulePoll(id);
    else await loadExecutionState();
  }, 1500);
}

watch(selectedModelId, loadVersions);
watch(selectedVersionId, async () => {
  await loadExecutionState();
  scheduleDeploymentPoll();
});
watch(selectedNodeId, scheduleDeploymentPoll);
watch(uploadFiles, handleFileChanged, { deep: true });
onMounted(loadInitial);
onBeforeUnmount(() => {
  disposed = true;
  if (pollTimer) clearTimeout(pollTimer);
  if (deploymentPollTimer) clearTimeout(deploymentPollTimer);
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
});
</script>

<template>
  <Page auto-content-height>
    <Spin :spinning="loading">
      <div class="ai-page ai-page-stack h-full">
        <AiPageHeader
          title="模型单图测试"
          description="上传图片，验证模型的识别结果。"
          icon="lucide:scan-search"
        />

        <Alert v-if="error" :message="error" show-icon type="error">
          <template #action>
            <Button @click="loadInitial">重试</Button>
          </template>
        </Alert>
        <div class="model-test-layout">
          <Card class="model-test-parameters" title="测试参数">
            <Form layout="vertical" class="model-test-form">
              <FormItem label="模型">
                <Select
                  v-model:value="selectedModelId"
                  :options="
                    models.map((item) => ({ label: item.name, value: item.id }))
                  "
                />
              </FormItem>
              <FormItem label="模型版本">
                <Select
                  v-model:value="selectedVersionId"
                  :options="
                    versions.map((item) => ({
                      label: `${item.version} · ${item.artifactFormat} · ${item.publishStatus}`,
                      value: item.id,
                    }))
                  "
                />
              </FormItem>
              <Alert
                v-if="selectedVersion && !versionPublished"
                class="mb-4"
                message="当前版本尚未发布，可查看但不能下发部署或执行测试。请先到模型资产页发布。"
                show-icon
                type="warning"
              />
              <FormItem label="执行节点">
                <Select
                  v-model:value="selectedNodeId"
                  :options="
                    nodes.map((item) => ({
                      label: `${item.name} · ${item.onlineStatus === 1 ? '在线' : '离线'}`,
                      value: item.id,
                      disabled: item.onlineStatus !== 1,
                    }))
                  "
                />
              </FormItem>
              <div class="model-test-deployment">
                <div class="model-test-deployment__actions">
                  <AiStatusIndicator
                    :status="selectedDeployment?.actualStatus ?? 'UNKNOWN'"
                    :label="`部署状态：${deploymentStatusText(selectedDeployment?.actualStatus)}`"
                  />
                  <Button
                    v-if="canDeploy && !nodeReady"
                    :disabled="
                      !versionPublished ||
                      !selectedNodeId ||
                      isDeploymentPending(selectedDeployment?.actualStatus)
                    "
                    :loading="deploymentSubmitting"
                    @click="deploy"
                  >
                    {{
                      selectedDeployment?.actualStatus === 'FAILED'
                        ? $t('model-deployment.retry')
                        : '部署模型'
                    }}
                  </Button>
                </div>
                <Alert
                  v-if="
                    selectedDeployment?.errorMessage || deploymentRefreshError
                  "
                  :message="
                    selectedDeployment?.errorMessage || deploymentRefreshError
                  "
                  :type="
                    selectedDeployment?.actualStatus === 'FAILED'
                      ? 'error'
                      : 'warning'
                  "
                  show-icon
                />
                <p
                  v-else-if="
                    isDeploymentPending(selectedDeployment?.actualStatus)
                  "
                  class="ai-form-note"
                >
                  {{ $t('model-deployment.preparing') }}
                </p>
              </div>
              <FormItem label="测试图片">
                <Upload
                  v-model:file-list="uploadFiles"
                  :before-upload="() => false"
                  :max-count="1"
                  accept="image/jpeg,image/png,image/webp"
                >
                  <Button>选择图片</Button>
                </Upload>
              </FormItem>
              <div class="model-test-dimensions">
                <FormItem label="置信度">
                  <InputNumber
                    v-model:value="confidence"
                    :min="0.01"
                    :max="1"
                    :step="0.05"
                  />
                </FormItem>
                <FormItem label="NMS">
                  <InputNumber
                    v-model:value="nmsThreshold"
                    :min="0.01"
                    :max="1"
                    :step="0.05"
                  />
                </FormItem>
                <FormItem label="输入宽度（px）">
                  <InputNumber
                    v-model:value="inputWidth"
                    :min="32"
                    :max="2048"
                  />
                </FormItem>
                <FormItem label="输入高度（px）">
                  <InputNumber
                    v-model:value="inputHeight"
                    :min="32"
                    :max="2048"
                  />
                </FormItem>
              </div>
              <Button
                v-if="canTest"
                block
                type="primary"
                :disabled="
                  !nodeReady || !versionPublished || !uploadFiles.length
                "
                @click="runTest"
              >
                执行单图测试
              </Button>
            </Form>
          </Card>

          <Card class="model-test-results" title="识别结果">
            <div class="ai-workflow">
              <div
                v-if="previewUrl"
                class="relative mx-auto overflow-hidden bg-black"
              >
                <img
                  :src="previewUrl"
                  alt="测试图片"
                  class="block h-auto w-full"
                />
                <div
                  v-for="(object, index) in standardResult?.objects ?? []"
                  :key="index"
                  class="absolute border-2 border-cyan-400"
                  :style="{
                    left: `${object.bbox.x * 100}%`,
                    top: `${object.bbox.y * 100}%`,
                    width: `${object.bbox.width * 100}%`,
                    height: `${object.bbox.height * 100}%`,
                  }"
                >
                  <span
                    class="absolute left-0 top-0 bg-cyan-400 px-1 text-xs text-black"
                  >
                    {{ object.class }}
                    {{ (object.confidence * 100).toFixed(1) }}%
                  </span>
                </div>
              </div>
              <div v-else class="model-test-empty">
                <Empty description="选择图片后在这里查看识别结果" />
              </div>
              <Descriptions
                v-if="currentTest"
                class="mt-4"
                bordered
                size="small"
              >
                <DescriptionsItem label="状态">
                  <Tag>{{ currentTest.status }}</Tag>
                </DescriptionsItem>
                <DescriptionsItem label="后端">
                  {{ currentTest.backend ?? '-' }}
                </DescriptionsItem>
                <DescriptionsItem label="诊断 ID">
                  {{ currentTest.diagnosticId ?? '-' }}
                </DescriptionsItem>
                <DescriptionsItem label="预处理">
                  {{ currentTest.preprocessMillis ?? '-' }} ms
                </DescriptionsItem>
                <DescriptionsItem label="推理">
                  {{ currentTest.inferenceMillis ?? '-' }} ms
                </DescriptionsItem>
                <DescriptionsItem label="后处理">
                  {{ currentTest.postprocessMillis ?? '-' }} ms
                </DescriptionsItem>
              </Descriptions>
              <Table
                v-if="standardResult"
                :columns="[
                  { title: '类别', dataIndex: 'class' },
                  { title: '置信度', dataIndex: 'confidence' },
                  { title: '归一化 bbox', dataIndex: 'bbox' },
                ]"
                :data-source="standardResult?.objects ?? []"
                :pagination="false"
                :row-key="(_record, index) => String(index)"
                size="small"
              >
                <template #bodyCell="{ column, record }">
                  <template v-if="column.dataIndex === 'confidence'">
                    {{ record.confidence.toFixed(4) }}
                  </template>
                  <template v-else-if="column.dataIndex === 'bbox'">
                    {{ JSON.stringify(record.bbox) }}
                  </template>
                </template>
              </Table>
            </div>
          </Card>
        </div>
      </div>
    </Spin>
  </Page>
</template>

<style scoped>
.model-test-layout {
  display: grid;
  grid-template-columns: minmax(320px, 2fr) minmax(0, 3fr);
  gap: 20px;
  align-items: start;
}

.model-test-form {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.model-test-form :deep(.ant-form-item) {
  margin: 0;
}

.model-test-form :deep(.ant-input-number) {
  width: 100%;
}

.model-test-dimensions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.model-test-deployment {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 14px;
  background: var(--ai-surface-subtle);
  border: 1px solid hsl(var(--border));
  border-radius: var(--ai-radius-md);
}

.model-test-deployment__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
}

.model-test-empty {
  display: grid;
  place-items: center;
  min-height: 420px;
}

@media (width <= 1100px) {
  .model-test-layout {
    grid-template-columns: minmax(0, 1fr);
  }

  .model-test-empty {
    min-height: 240px;
  }
}
</style>
