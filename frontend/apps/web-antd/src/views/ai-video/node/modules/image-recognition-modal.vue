<script setup lang="ts">
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type {
  GatewayImageResult,
  GatewayTask,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';

import { computed, onBeforeUnmount, ref, shallowRef, watch } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { Alert, Button, Empty, Switch, Tag, Upload } from 'ant-design-vue';

import { useVbenVxeGrid } from '#/adapter/vxe-table';
import RecognitionFrame from '#/components/ai-video/recognition-frame.vue';
import { $t } from '#/locales';

import ImageValidationPanel from './image-validation-panel.vue';

const props = withDefaults(
  defineProps<{ available?: boolean; transport: GatewayTransport }>(),
  { available: true },
);
const t = (key: string) => $t(`image-recognition.${key}`);
const task = ref<GatewayTask>();
const supported = ref(false);
const validationSupported = ref(false);
const validationMode = ref(false);
const opened = ref(false);
const selectedFile = shallowRef<File>();
const previewUrl = ref('');
const result = ref<GatewayImageResult>();
const busy = ref(false);
const error = ref('');
const showBoxes = ref(true);
let generation = 0;

function clearImage() {
  generation++;
  if (previewUrl.value) URL.revokeObjectURL(previewUrl.value);
  previewUrl.value = '';
  selectedFile.value = undefined;
  result.value = undefined;
  error.value = '';
  busy.value = false;
}
const [Modal, modalApi] = useVbenModal({
  showConfirmButton: false,
  showCancelButton: false,
  onOpenChange(open) {
    clearImage();
    opened.value = open;
    validationMode.value = false;
    if (open) {
      const data = modalApi.getData<{
        supported: boolean;
        task: GatewayTask;
        validationSupported?: boolean;
      }>();
      task.value = data.task;
      supported.value = data.supported;
      validationSupported.value = data.validationSupported ?? false;
      showBoxes.value = true;
    }
  },
});
const frame = computed<AiVideoCameraApi.OverlayFrame | undefined>(() => {
  if (!result.value) return undefined;
  return {
    ...result.value,
    sessionId: result.value.frameId,
    objects: result.value.objects.map((object) => {
      const attributes = object.attributes ?? {};
      const value = attributes.plateNumber ?? attributes.plateText;
      const text = typeof value === 'string' ? value.trim() : '';
      return {
        ...object,
        attributes: {
          ...attributes,
          ...(text ? { displayLabel: text } : {}),
        },
      };
    }),
  };
});
type ImageDetection = GatewayImageResult['objects'][number] & {
  id: number;
  text: string;
};
const detections = computed<ImageDetection[]>(() =>
  (result.value?.objects ?? []).map((object, index) => ({
    ...object,
    id: index + 1,
    text: String(
      object.attributes?.plateText ?? object.attributes?.plateNumber ?? '—',
    ),
  })),
);
const [Grid, gridApi] = useVbenVxeGrid<ImageDetection>({
  gridOptions: {
    data: [],
    columns: [
      { field: 'id', title: '#', width: 48 },
      { field: 'class', title: t('category'), minWidth: 120 },
      {
        field: 'confidence',
        title: t('confidence'),
        width: 110,
        slots: { default: 'confidence' },
      },
      { field: 'text', title: t('recognizedText'), minWidth: 150 },
    ],
    height: 230,
    pagerConfig: { enabled: false },
    rowConfig: { keyField: 'id' },
    toolbarConfig: { enabled: false },
  },
});
watch(detections, (data) => void gridApi.setGridOptions({ data }));

function selectFile(file: FileType) {
  if (busy.value) return Upload.LIST_IGNORE;
  clearImage();
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) {
    error.value = t('invalidType');
    return Upload.LIST_IGNORE;
  }
  if (!file.size || file.size > 4 * 1024 * 1024) {
    error.value = t('invalidSize');
    return Upload.LIST_IGNORE;
  }
  selectedFile.value = file;
  previewUrl.value = URL.createObjectURL(file);
  return false;
}

function imageBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(new Error(t('readFailed')));
    reader.onabort = () => reject(new Error(t('readFailed')));
    reader.readAsDataURL(file);
  });
}

async function recognize() {
  if (
    busy.value ||
    !selectedFile.value ||
    !task.value ||
    !supported.value ||
    !props.available
  )
    return;
  const current = ++generation;
  const file = selectedFile.value;
  const taskId = task.value.config.taskId;
  busy.value = true;
  result.value = undefined;
  error.value = '';
  try {
    const image = await imageBase64(file);
    if (current !== generation) return;
    const response = await props.transport<GatewayImageResult>(
      'task.recognize-image',
      {
        taskId,
        imageBase64: image,
      },
    );
    if (current === generation) result.value = response;
  } catch (cause) {
    if (current === generation)
      error.value = cause instanceof Error ? cause.message : t('failed');
  } finally {
    if (current === generation) busy.value = false;
  }
}
onBeforeUnmount(clearImage);
</script>

<template>
  <Modal :title="t('title')" class="!w-[1100px] max-w-[95vw]">
    <div class="mb-4 flex gap-2">
      <Button
        :type="validationMode ? 'default' : 'primary'"
        @click="validationMode = false"
        >{{ $t('image-validation.single') }}</Button
      >
      <Button
        :type="validationMode ? 'primary' : 'default'"
        :disabled="busy"
        @click="validationMode = true"
        >{{ $t('image-validation.title') }}</Button
      >
    </div>
    <template v-if="validationMode && opened">
      <ImageValidationPanel
        v-if="validationSupported && task"
        :task="task"
        :transport="transport"
        :available="available"
      />
      <Alert
        v-else
        type="warning"
        show-icon
        :message="$t('image-validation.upgrade')"
      />
    </template>
    <div v-else class="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
      <div class="space-y-4">
        <div class="rounded-lg border bg-muted/30 p-4">
          <div class="mb-1 text-xs text-muted-foreground">
            {{ t('currentTask') }}
          </div>
          <strong class="break-words">{{
            task?.displayNames?.task || task?.name
          }}</strong>
          <p class="mt-2 text-xs leading-5 text-muted-foreground">
            {{ t('description') }}
          </p>
        </div>
        <Alert
          v-if="!available"
          type="warning"
          show-icon
          :message="t('offline')"
        />
        <Alert
          v-else-if="!supported"
          type="warning"
          show-icon
          :message="t('upgrade')"
        />
        <div class="h-36">
          <Upload.Dragger
            accept="image/jpeg,image/png,image/webp"
            :before-upload="selectFile"
            :show-upload-list="false"
            :disabled="busy || !available || !supported"
            :multiple="false"
          >
            <p class="px-2 py-4 font-medium">{{ t('upload') }}</p>
            <p class="px-2 pb-3 text-xs text-muted-foreground">
              {{ t('limits') }}
            </p>
          </Upload.Dragger>
        </div>
        <div
          v-if="selectedFile"
          class="break-all text-xs text-muted-foreground"
        >
          {{ selectedFile.name }} ·
          {{ (selectedFile.size / 1024).toFixed(0) }} KB
          <Button
            class="!px-0"
            type="link"
            size="small"
            :disabled="busy"
            @click="clearImage"
            >{{ t('remove') }}</Button
          >
        </div>
        <Button
          block
          type="primary"
          :loading="busy"
          :disabled="!selectedFile || !available || !supported"
          @click="recognize"
        >
          {{ busy ? t('recognizing') : result ? t('retry') : t('start') }}
        </Button>
        <p class="text-xs leading-5 text-muted-foreground">
          {{ t('singleFrame') }}
        </p>
        <Alert
          v-if="error"
          type="error"
          show-icon
          :message="error"
          class="break-words"
        />
      </div>
      <div class="min-w-0 space-y-3">
        <div class="flex items-center justify-between gap-3">
          <strong>{{ t('result') }}</strong>
          <label class="flex items-center gap-2 text-xs">
            <Switch
              v-model:checked="showBoxes"
              size="small"
              :aria-label="t('boxes')"
            />
            {{ t('boxes') }}
          </label>
        </div>
        <div class="h-[380px] overflow-hidden rounded-lg border">
          <RecognitionFrame
            :key="result?.frameId ?? previewUrl"
            :source="previewUrl"
            :frame="frame"
            :title="t('result')"
            :empty-text="t('emptyImage')"
            :empty-result-text="t('noObjects')"
            :context-label="busy ? t('recognizing') : t('sampleImage')"
            :show-boxes="showBoxes"
            historical
            show-all-objects
          />
        </div>
        <template v-if="result">
          <div
            class="flex flex-wrap items-center gap-x-4 gap-y-2 text-xs text-muted-foreground"
          >
            <Tag color="blue">{{ detections.length }} {{ t('objects') }}</Tag>
            <span>{{ t('elapsed') }} {{ result.totalMillis }} ms</span>
            <span>{{ result.backend }} / {{ result.device }}</span>
            <span>{{ result.sourceWidth }} × {{ result.sourceHeight }}</span>
          </div>
          <Alert
            v-if="!result.observationValid"
            type="warning"
            show-icon
            :message="t('observationInvalid')"
          />
          <Grid>
            <template #confidence="{ row }"
              >{{ (row.confidence * 100).toFixed(1) }}%</template
            >
            <template #empty><Empty :description="t('noObjects')" /></template>
          </Grid>
          <p class="break-all text-xs text-muted-foreground">
            {{ t('diagnostic') }} {{ result.diagnosticId }} ·
            {{ t('revision') }} {{ result.revision }}
          </p>
        </template>
      </div>
    </div>
  </Modal>
</template>
