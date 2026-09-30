<script setup lang="ts">
import type { FileType } from 'ant-design-vue/es/upload/interface';

import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type {
  GatewayImageResult,
  GatewayTask,
  GatewayTransport,
} from '#/api/ai-video/node/gateway';
import type {
  ValidationHistory,
  ValidationImage,
  ValidationItem,
  ValidationOptions,
  ValidationRun,
  ValidationSample,
  ValidationSet,
} from '#/api/ai-video/node/validation';

import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import {
  Alert,
  Button,
  Empty,
  Select,
  Switch,
  Tag,
  Upload,
} from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { TableAction, useVbenVxeGrid } from '#/adapter/vxe-table';
import { gatewayRequestId } from '#/api/ai-video/node/gateway';
import { readValidationImage } from '#/api/ai-video/node/validation';
import RecognitionFrame from '#/components/ai-video/recognition-frame.vue';
import { $t } from '#/locales';

import {
  downloadValidationReport,
  validationReport,
} from './validation-report';

const props = defineProps<{
  available: boolean;
  task: GatewayTask;
  transport: GatewayTransport;
}>();
const t = (key: string) => $t(`image-validation.${key}`);
const sets = ref<ValidationSet[]>([]);
const dataset = ref<ValidationSet>();
const options = ref<ValidationOptions>({
  algorithms: [],
  models: [],
  tasks: [],
});
const taskId = ref(props.task.config.taskId);
const modelBindings = ref<Record<string, number>>({});
const algorithmSha256 = ref<string>();
const runs = ref<ValidationHistory[]>([]);
const run = ref<ValidationRun>();
const selected = ref<ValidationItem | ValidationSample>();
const preview = ref('');
const previewItem = ref<ValidationItem>();
const boxes = ref(true);
const busy = ref(false);
const running = ref(false);
const error = ref('');
const editorError = ref('');
const filter = ref('ALL');
let disposed = false;
const stop = ref(false);
let imageGeneration = 0;
const currentTask = computed(() =>
  options.value.tasks.find((task) => task.config.taskId === taskId.value),
);
const packageCode = computed(
  () =>
    (
      currentTask.value?.config.pipeline.algorithmPackage as
        | undefined
        | { manifest?: { code: string } }
    )?.manifest?.code,
);
const algorithmOptions = computed(() =>
  options.value.algorithms
    .filter(
      (item) =>
        item.status === 'READY' && item.manifest?.code === packageCode.value,
    )
    .map((item) => ({
      label: `${item.manifest?.name} · ${item.manifest?.version}`,
      value: item.sha256,
    })),
);
const selectedItem = computed(
  () =>
    selected.value &&
    run.value?.items.find((item) => item.id === selected.value?.id),
);
function recognitionText(object: GatewayImageResult['objects'][number]) {
  const value = object.attributes?.plateNumber ?? object.attributes?.plateText;
  return typeof value === 'string' ? value.trim() : '';
}
const recognizedTexts = computed(() =>
  (previewItem.value?.result?.objects ?? [])
    .filter((object) => object.attributes?.visibleByDefault !== false)
    .map(recognitionText)
    .filter(Boolean),
);
const frame = computed<AiVideoCameraApi.OverlayFrame | undefined>(() => {
  const result = previewItem.value?.result;
  return result
    ? {
        ...result,
        sessionId: result.frameId,
        objects: result.objects.map((object) => {
          const text = recognitionText(object);
          return {
            ...object,
            attributes: {
              ...(object.attributes ?? {}),
              ...(text ? { displayLabel: text } : {}),
            },
          };
        }),
      }
    : undefined;
});
const rows = computed(() =>
  (run.value?.items ?? dataset.value?.samples ?? []).filter(
    (item) =>
      filter.value === 'ALL' ||
      ('status' in item && item.status === filter.value),
  ),
);
const progress = computed(
  () =>
    run.value?.items.filter(
      (item) => !['PENDING', 'RUNNING'].includes(item.status),
    ).length ?? 0,
);
const statuses = [
  'PASS',
  'FAIL',
  'INCONCLUSIVE',
  'ERROR',
  'PENDING',
  'RUNNING',
];
const colors: Record<string, string> = {
  PASS: 'green',
  FAIL: 'red',
  ERROR: 'red',
  INCONCLUSIVE: 'orange',
  RUNNING: 'blue',
};
const [Grid, grid] = useVbenVxeGrid<ValidationItem>({
  gridOptions: {
    data: [],
    height: 320,
    pagerConfig: { enabled: false },
    toolbarConfig: { enabled: false },
    rowConfig: { keyField: 'id' },
    columns: [
      { field: 'name', title: t('image'), minWidth: 140, fixed: 'left' },
      {
        field: 'expected',
        title: t('expected'),
        minWidth: 210,
        slots: { default: 'expected' },
      },
      { field: 'actualCount', title: t('actual'), width: 85 },
      {
        field: 'status',
        title: t('status'),
        width: 110,
        slots: { default: 'status' },
      },
      { field: 'note', title: t('note'), minWidth: 140, showOverflow: true },
      {
        title: t('actions'),
        width: 195,
        fixed: 'right',
        slots: { default: 'actions' },
      },
    ],
  },
});
watch(rows, (data) => void grid.setGridOptions({ data }), { immediate: true });
watch(
  currentTask,
  (task) => {
    modelBindings.value = { ...task?.config.modelBindings };
    algorithmSha256.value = (
      task?.config.pipeline.algorithmPackage as undefined | { sha256?: string }
    )?.sha256;
  },
  { immediate: true },
);

async function perform(action: () => Promise<void>) {
  if (busy.value || disposed) return;
  busy.value = true;
  error.value = '';
  try {
    await action();
  } catch (cause) {
    if (!disposed)
      error.value = cause instanceof Error ? cause.message : t('failed');
  } finally {
    if (!disposed) busy.value = false;
  }
}
async function load() {
  await perform(async () => {
    const [list, versions] = await Promise.all([
      props.transport<ValidationSet[]>('validation.list'),
      props.transport<ValidationOptions>('validation.options'),
    ]);
    if (disposed) return;
    sets.value = list;
    options.value = versions;
    if (dataset.value) {
      const id = dataset.value.id;
      const [current, history] = await Promise.all([
        props.transport<ValidationSet>('validation.get', { id }),
        props.transport<ValidationHistory[]>('validation.runs', { id }),
      ]);
      if (disposed) return;
      dataset.value = current;
      runs.value = history;
      if (run.value) {
        const currentRun = await props.transport<ValidationRun>(
          'validation.run-get',
          { id: run.value.id },
        );
        if (!disposed) run.value = currentRun;
      }
    }
  });
}
function clearPreview() {
  imageGeneration++;
  preview.value = '';
  selected.value = undefined;
  previewItem.value = undefined;
}
async function chooseSet(id: string) {
  await perform(async () => {
    const [value, history] = await Promise.all([
      props.transport<ValidationSet>('validation.get', { id }),
      props.transport<ValidationHistory[]>('validation.runs', { id }),
    ]);
    if (disposed) return;
    dataset.value = value;
    runs.value = history;
    run.value = undefined;
    filter.value = 'ALL';
    clearPreview();
  });
}
async function showSample(sample: ValidationSample) {
  const generation = ++imageGeneration;
  selected.value = sample;
  preview.value = '';
  previewItem.value = undefined;
  try {
    const id = run.value?.id ?? dataset.value?.id;
    if (!id) return;
    const [image, item] = await Promise.all([
      readValidationImage(
        props.transport,
        id,
        sample.id,
        () => !disposed && generation === imageGeneration,
      ),
      run.value
        ? props.transport<ValidationItem>('validation.result', {
            id,
            sampleId: sample.id,
          })
        : Promise.resolve(undefined),
    ]);
    if (!disposed && generation === imageGeneration) {
      preview.value = `data:${image.mime};base64,${image.imageBase64}`;
      previewItem.value = item;
    }
  } catch (cause) {
    if (!disposed && generation === imageGeneration)
      error.value = cause instanceof Error ? cause.message : t('failed');
  }
}
const [SetForm, setForm] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'name',
      label: t('name'),
      component: 'Input',
      rules: 'required',
      componentProps: { maxlength: 100 },
    },
  ],
});
const [SetModal, setModal] = useVbenModal({
  title: t('create'),
  async onConfirm() {
    if (!(await setForm.validate()).valid) return;
    setModal.lock();
    editorError.value = '';
    try {
      const values = await setForm.getValues();
      const value = await props.transport<ValidationSet>('validation.save', {
        id: gatewayRequestId(),
        requestId: gatewayRequestId(),
        expectedRevision: 0,
        name: values.name,
      });
      if (disposed) return;
      dataset.value = value;
      sets.value.unshift(value);
      runs.value = [];
      run.value = undefined;
      clearPreview();
      setModal.close();
    } catch (cause) {
      editorError.value = cause instanceof Error ? cause.message : t('failed');
    } finally {
      setModal.unlock();
    }
  },
});
const [SampleForm, sampleForm] = useVbenForm({
  showDefaultActions: false,
  schema: [
    {
      fieldName: 'category',
      label: t('category'),
      component: 'Input',
      componentProps: { placeholder: t('categoryHint'), maxlength: 100 },
    },
    {
      fieldName: 'count',
      label: t('count'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: {
        min: 0,
        max: 1000,
        precision: 0,
        'aria-label': t('count'),
      },
    },
    {
      fieldName: 'confidence',
      label: t('confidence'),
      component: 'InputNumber',
      rules: 'required',
      componentProps: {
        min: 0,
        max: 1,
        step: 0.05,
        'aria-label': t('confidence'),
      },
    },
    {
      fieldName: 'text',
      label: t('text'),
      component: 'Input',
      componentProps: { maxlength: 100 },
    },
    {
      fieldName: 'note',
      label: t('note'),
      component: 'Textarea',
      componentProps: { maxlength: 2000, rows: 3 },
    },
  ],
});
const editing = ref<ValidationSample>();
const [SampleModal, sampleModal] = useVbenModal({
  title: t('edit'),
  async onConfirm() {
    if (
      !editing.value ||
      !dataset.value ||
      !(await sampleForm.validate()).valid
    )
      return;
    sampleModal.lock();
    editorError.value = '';
    try {
      const values = await sampleForm.getValues();
      const value = await props.transport<ValidationSet>(
        'validation.sample-save',
        {
          id: dataset.value.id,
          expectedRevision: dataset.value.revision,
          requestId: gatewayRequestId(),
          sampleId: editing.value.id,
          name: editing.value.name,
          expected: {
            category: values.category ?? '',
            count: values.count,
            confidence: values.confidence,
            text: values.text ?? '',
          },
          note: values.note ?? '',
        },
      );
      if (disposed) return;
      dataset.value = value;
      sampleModal.close();
    } catch (cause) {
      editorError.value = cause instanceof Error ? cause.message : t('failed');
    } finally {
      sampleModal.unlock();
    }
  },
});
function editSample(sample: ValidationSample) {
  editing.value = sample;
  editorError.value = '';
  sampleModal.open();
  void sampleForm.setValues({ ...sample.expected, note: sample.note });
}
function readImage(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '');
    reader.onerror = () => reject(new Error(t('readFailed')));
    reader.onabort = () => reject(new Error(t('readFailed')));
    reader.readAsDataURL(file);
  });
}
function upload(file: FileType, files: FileType[]) {
  if (file !== files[0] || busy.value || !dataset.value) return false;
  void perform(async () => {
    const failures: string[] = [];
    for (const image of files) {
      if (disposed) break;
      if (
        !['image/jpeg', 'image/png', 'image/webp'].includes(image.type) ||
        !image.size ||
        image.size > 4 * 1024 * 1024
      ) {
        failures.push(`${image.name}: ${t('limits')}`);
        continue;
      }
      const current = dataset.value;
      if (!current || current.samples.length >= 50) {
        failures.push(t('sampleLimit'));
        break;
      }
      try {
        const value = await props.transport<ValidationSet>(
          'validation.sample-save',
          {
            id: current.id,
            expectedRevision: current.revision,
            requestId: gatewayRequestId(),
            sampleId: gatewayRequestId(),
            name: image.name,
            expected: { category: '', count: 0, confidence: 0.5, text: '' },
            note: '',
            imageBase64: await readImage(image),
          },
        );
        if (!disposed) dataset.value = value;
      } catch (cause) {
        failures.push(
          `${image.name}: ${cause instanceof Error ? cause.message : t('failed')}`,
        );
        break;
      }
    }
    if (!disposed) error.value = failures.join('\n');
  });
  return false;
}
async function loadRun(id: string) {
  await perform(async () => {
    const value = await props.transport<ValidationRun>('validation.run-get', {
      id,
    });
    if (!disposed) {
      run.value = value;
      filter.value = 'ALL';
      clearPreview();
    }
  });
}
async function execute(resume = false) {
  await perform(async () => {
    if (!props.available) return;
    stop.value = false;
    running.value = true;
    try {
      if (!resume) {
        if (!dataset.value || !currentTask.value) return;
        const value = await props.transport<ValidationRun>(
          'validation.run-create',
          {
            id: dataset.value.id,
            expectedRevision: dataset.value.revision,
            requestId: gatewayRequestId(),
            taskId: currentTask.value.config.taskId,
            taskRevision: currentTask.value.revision,
            modelBindings: modelBindings.value,
            ...(algorithmSha256.value
              ? { algorithmSha256: algorithmSha256.value }
              : {}),
          },
        );
        if (disposed) return;
        run.value = value;
        runs.value.unshift(value);
        clearPreview();
        filter.value = 'ALL';
      }
      const active = run.value;
      if (!active) return;
      for (const item of active.items) {
        if (stop.value || disposed || !props.available) break;
        if (item.status !== 'PENDING') continue;
        const value = await props.transport<ValidationItem>(
          'validation.run-item',
          { id: active.id, sampleId: item.id },
        );
        if (disposed) return;
        active.items = active.items.map((old) =>
          old.id === value.id ? value : old,
        );
      }
    } finally {
      if (!disposed) running.value = false;
    }
  });
}
async function exportReport() {
  await perform(async () => {
    const active = run.value;
    if (!active) return;
    const images: Record<string, ValidationImage> = {};
    for (const item of active.items) {
      images[item.id] = await readValidationImage(
        props.transport,
        active.id,
        item.id,
        () => !disposed,
      );
      Object.assign(
        item,
        await props.transport<ValidationItem>('validation.result', {
          id: active.id,
          sampleId: item.id,
        }),
      );
      if (disposed) return;
    }
    downloadValidationReport(validationReport(active, images, t), active.id);
  });
}
async function removeSample(sample: ValidationSample) {
  await perform(async () => {
    if (!dataset.value) return;
    const value = await props.transport<ValidationSet>(
      'validation.sample-delete',
      {
        id: dataset.value.id,
        expectedRevision: dataset.value.revision,
        requestId: gatewayRequestId(),
        sampleId: sample.id,
      },
    );
    if (!disposed) {
      dataset.value = value;
      clearPreview();
    }
  });
}
async function deleteSet() {
  await perform(async () => {
    if (!dataset.value) return;
    await props.transport('validation.delete', {
      id: dataset.value.id,
      expectedRevision: dataset.value.revision,
      requestId: gatewayRequestId(),
    });
    sets.value = sets.value.filter((item) => item.id !== dataset.value?.id);
    dataset.value = undefined;
    run.value = undefined;
    runs.value = [];
    clearPreview();
  });
}
onMounted(load);
onBeforeUnmount(() => {
  disposed = true;
  stop.value = true;
  clearPreview();
});
</script>

<template>
  <div class="space-y-4">
    <SetModal
      ><SetForm /><Alert v-if="editorError" type="error" :message="editorError"
    /></SetModal>
    <SampleModal
      ><SampleForm />
      <p class="text-xs text-muted-foreground">{{ t('comparisonHelp') }}</p>
      <Alert v-if="editorError" type="error" :message="editorError"
    /></SampleModal>
    <Alert v-if="!available" type="warning" show-icon :message="t('offline')" />
    <Alert
      v-if="error"
      type="error"
      show-icon
      :message="error"
      class="whitespace-pre-line"
    />
    <div class="flex flex-wrap items-center gap-2">
      <Select
        :value="dataset?.id"
        :options="sets.map((item) => ({ label: item.name, value: item.id }))"
        :placeholder="t('selectSet')"
        :aria-label="t('selectSet')"
        class="w-64"
        :disabled="busy || !available"
        @change="(id) => typeof id === 'string' && chooseSet(id)"
      />
      <Button
        :disabled="busy || !available"
        @click="
          editorError = '';
          setModal.open();
          setForm.resetForm();
        "
        >{{ t('create') }}</Button
      >
      <Button
        :loading="busy && !running"
        :disabled="busy || !available"
        @click="load"
        >{{ t('refresh') }}</Button
      >
      <TableAction
        v-if="dataset"
        :actions="[
          {
            label: t('delete'),
            danger: true,
            disabled: busy || !available,
            popConfirm: { title: t('deleteConfirm'), confirm: deleteSet },
          },
        ]"
      />
    </div>
    <Empty v-if="!dataset" :description="t('empty')" />
    <template v-else>
      <div class="grid gap-4 lg:grid-cols-[280px_minmax(0,1fr)]">
        <div class="space-y-3 rounded-lg border bg-muted/30 p-4">
          <strong
            >{{ dataset.name }} · {{ t('revision') }}
            {{ dataset.revision }}</strong
          >
          <label class="block text-xs">{{ t('task') }}</label>
          <Select
            v-model:value="taskId"
            class="w-full"
            :aria-label="t('task')"
            :disabled="busy"
            :options="
              options.tasks.map((item) => ({
                label: `${item.displayNames?.task || item.name} · r${item.revision} / P${item.config.pipelineVersionId}`,
                value: item.config.taskId,
              }))
            "
          />
          <template v-if="algorithmOptions.length">
            <label class="block text-xs">{{ t('algorithm') }}</label>
            <Select
              v-model:value="algorithmSha256"
              class="w-full"
              :aria-label="t('algorithm')"
              :disabled="busy"
              :options="algorithmOptions"
            />
          </template>
          <template v-for="(_, slot) in modelBindings" :key="slot">
            <label class="block text-xs">{{ t('model') }} · {{ slot }}</label>
            <Select
              v-model:value="modelBindings[slot]"
              class="w-full"
              :aria-label="`${t('model')} ${slot}`"
              :disabled="busy"
              :options="
                options.models.map((item) => ({
                  label: `${item.displayName || item.modelVersionId} · ${item.version || item.modelVersionId}`,
                  value: item.modelVersionId,
                }))
              "
            />
          </template>
          <Button
            block
            type="primary"
            :disabled="
              busy || !available || !dataset.samples.length || !currentTask
            "
            @click="execute()"
            >{{ t('run') }}</Button
          >
          <Button v-if="running" block @click="stop = true">{{
            t('pause')
          }}</Button>
          <Button
            v-else-if="run?.items.some((item) => item.status === 'PENDING')"
            block
            :disabled="busy || !available"
            @click="execute(true)"
            >{{ t('resume') }}</Button
          >
          <p class="text-xs leading-5 text-muted-foreground">
            {{ t('scope') }}
          </p>
        </div>
        <div class="min-w-0 space-y-3">
          <div class="flex flex-wrap items-center gap-2">
            <Select
              :value="run?.id || ''"
              class="min-w-64 flex-1"
              :disabled="busy"
              :aria-label="t('history')"
              :options="[
                { label: t('editSet'), value: '' },
                ...runs.map((item) => ({
                  label: `${new Date(item.createdAt).toLocaleString()} · ${item.target.name} · ${t('revision')} ${item.setRevision}`,
                  value: item.id,
                })),
              ]"
              @change="
                (id) =>
                  typeof id === 'string' &&
                  (id ? loadRun(id) : ((run = undefined), clearPreview()))
              "
            />
            <Button
              :disabled="!run || busy || !available"
              @click="exportReport"
              >{{ t('export') }}</Button
            >
            <Switch v-model:checked="boxes" :aria-label="t('boxes')" /><span
              class="text-xs"
              >{{ t('boxes') }}</span
            >
          </div>
          <div class="h-[300px] overflow-hidden rounded-lg border">
            <RecognitionFrame
              :key="`${preview}-${frame?.frameId}`"
              :source="preview"
              :title="t('image')"
              :context-label="t('sample')"
              :frame="frame"
              :show-boxes="boxes"
              :empty-text="t('preview')"
              :empty-result-text="t('noObjects')"
              historical
            />
          </div>
          <p v-if="selected" class="break-words text-xs">
            {{ selected.name }} · {{ t('expected') }}:
            {{ selected.expected.category || t('allCategories') }} ×
            {{ selected.expected.count }} · {{ selected.expected.text }} ·
            {{ t('confidence') }} ≥ {{ selected.expected.confidence }}<br />{{
              selected.note
            }}
          </p>
          <p v-if="selectedItem" class="break-words text-xs">
            {{ t(selectedItem.status) }} · {{ t('actual') }}
            {{ selectedItem.actualCount ?? '—' }} ·
            {{ selectedItem.result?.totalMillis ?? '—' }} ms ·
            {{ selectedItem.error }} ·
            {{ selectedItem.result?.diagnosticId || selectedItem.diagnosticId
            }}<template v-if="recognizedTexts.length"
              ><br />{{ t('recognizedText') }}：{{
                recognizedTexts.join('、')
              }}</template
            >
          </p>
        </div>
      </div>
      <p v-if="run" class="break-words text-xs text-muted-foreground">
        {{ t('executionVersion') }}:
        {{ run.target.algorithm?.manifest?.name || run.target.name }}
        {{
          run.target.algorithm?.manifest?.version ||
          `P${run.target.pipelineVersionId}`
        }}
        ·
        {{
          run.target.models
            .map(
              (model) =>
                `${model.displayName || model.modelVersionId} / ${model.version || model.modelVersionId}`,
            )
            .join(' · ')
        }}
      </p>
      <div v-if="run" class="flex flex-wrap items-center gap-2">
        <span>{{ progress }} / {{ run.items.length }}</span>
        <Tag v-for="status in statuses" :key="status" :color="colors[status]"
          >{{ t(status) }}
          {{ run.items.filter((item) => item.status === status).length }}</Tag
        >
        <Select
          v-model:value="filter"
          class="w-36"
          :aria-label="t('status')"
          :options="
            ['ALL', ...statuses].map((value) => ({ value, label: t(value) }))
          "
        />
      </div>
      <Upload.Dragger
        v-else
        accept="image/jpeg,image/png,image/webp"
        multiple
        :show-upload-list="false"
        :disabled="busy || !available"
        :before-upload="upload"
      >
        <p class="p-2">{{ t('upload') }}</p>
        <p class="text-xs text-muted-foreground">
          {{ t('limits') }} · {{ t('defaultExpected') }}
        </p>
      </Upload.Dragger>
      <Grid>
        <template #expected="{ row }"
          >{{ row.expected.category || t('allCategories') }} ×
          {{ row.expected.count
          }}<span v-if="row.expected.text">
            · {{ row.expected.text }}</span
          ></template
        >
        <template #status="{ row }"
          ><Tag v-if="row.status" :color="colors[row.status]">{{
            t(row.status)
          }}</Tag
          ><span v-else>—</span></template
        >
        <template #actions="{ row }"
          ><TableAction
            :actions="[
              { label: t('view'), onClick: () => showSample(row) },
              {
                label: t('edit'),
                ifShow: !run,
                disabled: busy || !available,
                onClick: () => editSample(row),
              },
              {
                label: t('remove'),
                ifShow: !run,
                disabled: busy || !available,
                danger: true,
                popConfirm: {
                  title: t('removeConfirm'),
                  confirm: () => removeSample(row),
                },
              },
            ]"
        /></template>
        <template #empty><Empty :description="t('emptySamples')" /></template>
      </Grid>
    </template>
  </div>
</template>
