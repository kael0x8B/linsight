<script setup lang="ts">
import type { AiVideoRuleApi } from '#/api/ai-video/rule';
import type { PreviewTransport } from '#/components/ai-video/preview-transport';

import { computed, onBeforeUnmount, ref, watch } from 'vue';

import { Alert, Button, message, Select, Switch } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import { getPublishedRules, getRuleVersions } from '#/api/ai-video/rule';
import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';
import RuleRegionCanvas from '#/components/ai-video/rule-region-canvas.vue';
import { regionGeometryError } from '#/components/ai-video/rule-region-geometry';
import {
  recognitionRegionKey,
  useDisplayPreferences,
} from '#/components/ai-video/use-display-preferences';
import { $t } from '#/locales';
import { createRuleAst } from '#/views/ai-video/rule/modules/rule-state';

const props = defineProps<{
  allowTemplateImport?: boolean;
  camera?: {
    code: string;
    id: number;
    name: string;
    onlineStatus?: number;
    status: number;
  };
  defaultRule?: AiVideoRuleApi.RuleAst;
  disabled?: boolean;
  eventType?: string;
  image?: string;
  imageSize?: { height: number; width: number };
  local?: boolean;
  modelValue: string;
  nodeId?: number;
  previewTransport?: PreviewTransport;
  taskId?: number;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: string] }>();
const t = (key: string) => $t(`rule-canvas.${key}`);
const displayPrefs = useDisplayPreferences(
  computed(() => props.camera?.id),
  props.local,
);
const regionDisplayKey = computed(() =>
  recognitionRegionKey(`task-${props.taskId}`),
);
const regionIndex = ref(0);
const canvasBusy = ref(false);
const canvas = ref<InstanceType<typeof RuleRegionCanvas>>();
const preview = ref(false);
const still = ref('');
const frameSize = ref<{ height: number; width: number }>();
const previousRule = ref('');
const player = ref<InstanceType<typeof CameraPreviewPlayer>>();
const undoStack = ref<string[]>([]);
const redoStack = ref<string[]>([]);
let lastEmitted: string | undefined;
const ast = computed<AiVideoRuleApi.RuleAst | null>(() => {
  try {
    return props.modelValue ? JSON.parse(props.modelValue) : null;
  } catch {
    return null;
  }
});
const region = computed(
  () => ast.value?.regions?.[regionIndex.value] ?? ast.value?.regions?.[0],
);
const canvasRegion = computed(() =>
  region.value && frameSize.value
    ? {
        ...region.value,
        sourceWidth: frameSize.value.width,
        sourceHeight: frameSize.value.height,
      }
    : region.value,
);
const children = computed(
  () => (ast.value?.condition?.children ?? []) as Record<string, unknown>[],
);
const has = (type: string) => children.value.some((c) => c.type === type);
const valueOf = (type: string, key: string, fallback: unknown) =>
  children.value.find((c) => c.type === type)?.[key] ?? fallback;
function update(mutator: (value: AiVideoRuleApi.RuleAst) => void) {
  if (!ast.value || props.disabled) return;
  const value = JSON.parse(JSON.stringify(ast.value)) as AiVideoRuleApi.RuleAst;
  mutator(value);
  replaceValue(JSON.stringify(value, null, 2));
}
function replaceValue(value: string, record = true) {
  if (props.disabled || value === props.modelValue) return;
  if (record) {
    undoStack.value.push(props.modelValue);
    if (undoStack.value.length > 30) undoStack.value.shift();
    redoStack.value = [];
  }
  importedFrom.value = '';
  lastEmitted = value;
  emit('update:modelValue', value);
}
function undo() {
  if (props.disabled || canvasBusy.value) return;
  const value = undoStack.value.pop();
  if (value !== undefined) {
    redoStack.value.push(props.modelValue);
    replaceValue(value, false);
  }
}
function redo() {
  if (props.disabled || canvasBusy.value) return;
  const value = redoStack.value.pop();
  if (value !== undefined) {
    undoStack.value.push(props.modelValue);
    replaceValue(value, false);
  }
}
function updatePoints(points: AiVideoRuleApi.Point[]) {
  update((value) => {
    const target = value.regions[regionIndex.value];
    if (!target) return;
    target.points = points;
    if (frameSize.value) {
      target.sourceWidth = frameSize.value.width;
      target.sourceHeight = frameSize.value.height;
    }
  });
}

const importOpen = ref(false);
const templateRules = ref<AiVideoRuleApi.Rule[]>([]);
const templateId = ref<number>();
const templateVersions = ref<AiVideoRuleApi.RuleVersion[]>([]);
const templateVersionId = ref<number>();
const templateRegionIndex = ref(0);
const templateLoading = ref(false);
const templateError = ref('');
const importedFrom = ref('');
let templateGeneration = 0;
const templateVersion = computed(() =>
  templateVersions.value.find((v) => v.id === templateVersionId.value),
);
const templateRegion = computed(
  () => templateVersion.value?.ast.regions[templateRegionIndex.value],
);
async function loadTemplates() {
  if (!props.allowTemplateImport || props.disabled || canvasBusy.value) return;
  importOpen.value = true;
  templateError.value = '';
  templateLoading.value = true;
  templateRules.value = [];
  templateId.value = undefined;
  templateVersions.value = [];
  templateVersionId.value = undefined;
  templateRegionIndex.value = 0;
  const generation = ++templateGeneration;
  try {
    const list = await getPublishedRules();
    if (generation !== templateGeneration) return;
    templateRules.value = list.filter(
      (r) =>
        r.status === 0 &&
        r.currentVersionId &&
        !r.code.startsWith('task-rule-'),
    );
  } catch {
    if (generation === templateGeneration)
      templateError.value = t('templateLoadFailed');
  } finally {
    if (generation === templateGeneration) templateLoading.value = false;
  }
}
async function loadTemplate(id: number) {
  if (!props.allowTemplateImport || props.disabled || canvasBusy.value) return;
  templateId.value = id;
  templateVersions.value = [];
  templateVersionId.value = undefined;
  templateRegionIndex.value = 0;
  templateError.value = '';
  templateLoading.value = true;
  const generation = ++templateGeneration;
  try {
    const list = await getRuleVersions(id);
    if (generation !== templateGeneration) return;
    templateVersions.value = list.filter(
      (v) => v.validationStatus === 'PUBLISHED',
    );
    const current = templateRules.value.find(
      (r) => r.id === id,
    )?.currentVersionId;
    templateVersionId.value =
      templateVersions.value.find((v) => v.id === current)?.id ??
      templateVersions.value[0]?.id;
  } catch {
    if (generation === templateGeneration)
      templateError.value = t('templateLoadFailed');
  } finally {
    if (generation === templateGeneration) templateLoading.value = false;
  }
}
function importRegion() {
  const source = templateRegion.value;
  if (
    !props.allowTemplateImport ||
    props.disabled ||
    canvasBusy.value ||
    !source ||
    templateLoading.value
  )
    return;
  const invalid = regionGeometryError(source.points);
  if (invalid) {
    templateError.value = t(invalid);
    return;
  }
  update((value) => {
    const target = value.regions[regionIndex.value];
    if (!target) return;
    // Copy geometry only: region IDs and conditions belong to this task.
    target.points = source.points.map((p) => ({ ...p }));
    target.sourceWidth = frameSize.value?.width ?? source.sourceWidth;
    target.sourceHeight = frameSize.value?.height ?? source.sourceHeight;
  });
  importedFrom.value = `${templateRules.value.find((r) => r.id === templateId.value)?.name ?? ''} · v${templateVersion.value?.version} · ${source.name}`;
  importOpen.value = false;
}
onBeforeUnmount(() => {
  templateGeneration++;
});
function condition(type: string, key: string, value: unknown) {
  if (value === null || value === undefined) return;
  update((rule) => {
    const nodes = Array.isArray(rule.condition.children)
      ? (rule.condition.children as Record<string, unknown>[])
      : [];
    const node = nodes.find(
      (c) =>
        c.type === type &&
        (type !== 'ROI_ENTER' || c.regionId === region.value?.id),
    );
    if (node) node[key] = value;
  });
}
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  commonConfig: { componentProps: { class: 'w-full' } },
  schema: [
    {
      fieldName: 'classes',
      label: '参与告警的目标',
      component: 'Select',
      componentProps: {
        mode: 'tags',
        onChange: (v: string[]) => condition('ROI_ENTER', 'objectClasses', v),
      },
    },
    {
      fieldName: 'minimumCount',
      label: '最低在岗人数',
      component: 'InputNumber',
      help: '岗位区域人数低于此值时开始离岗确认。',
      componentProps: {
        min: 1,
        max: 10_000,
        precision: 0,
        onChange: (v: number) => condition('COUNT_BELOW', 'min', v),
      },
    },
    {
      fieldName: 'recovery',
      label: '恢复确认时间（秒）',
      component: 'InputNumber',
      componentProps: {
        min: 0,
        max: 86_400,
        onChange: (v: number) => {
          if (v !== null && v !== undefined)
            update((r) => {
              r.recoverySeconds = v;
            });
        },
      },
    },
    {
      fieldName: 'duration',
      label: '持续时间（秒）',
      component: 'InputNumber',
      help: '目标满足条件并连续确认后，持续达到此时间才告警。',
      componentProps: {
        min: 0,
        max: 86_400,
        onChange: (v: number) => condition('DURATION', 'seconds', v),
      },
    },
    {
      fieldName: 'n',
      label: '至少命中帧数',
      component: 'InputNumber',
      componentProps: {
        min: 1,
        max: 300,
        precision: 0,
        onChange: (v: number) => condition('N_OF_M', 'n', v),
      },
    },
    {
      fieldName: 'm',
      label: '观察窗口帧数',
      component: 'InputNumber',
      componentProps: {
        min: 1,
        max: 300,
        precision: 0,
        onChange: (v: number) => condition('N_OF_M', 'm', v),
      },
    },
    {
      fieldName: 'cooldown',
      label: '重复告警间隔（秒）',
      component: 'InputNumber',
      componentProps: {
        min: 0,
        max: 86_400,
        onChange: (v: number) => {
          if (v !== null && v !== undefined)
            update((r) => {
              r.cooldownSeconds = v;
            });
        },
      },
    },
    {
      fieldName: 'movement',
      label: '静止位置容差',
      component: 'InputNumber',
      help: '相对于停车起始位置，允许的画面归一化位移。默认 0.02 表示 2%；移动车辆重新计时。',
      componentProps: {
        min: 0.001,
        max: 1,
        step: 0.005,
        onChange: (v: number) => condition('STATIONARY', 'maxMovement', v),
      },
    },
  ],
});
watch(
  () => children.value.map((c) => c.type).join('|'),
  () => {
    form.updateSchema(
      Object.entries({
        classes: 'ROI_ENTER',
        minimumCount: 'COUNT_BELOW',
        duration: 'DURATION',
        n: 'N_OF_M',
        m: 'N_OF_M',
        movement: 'STATIONARY',
      }).map(([fieldName, type]) => ({
        fieldName,
        dependencies: { triggerFields: ['cooldown'], show: has(type) },
      })),
    );
  },
  { immediate: true },
);
watch(
  () => props.modelValue,
  (value) => {
    if (value !== lastEmitted) {
      undoStack.value = [];
      redoStack.value = [];
      importedFrom.value = '';
    }
    if (ast.value)
      void form.setValues({
        classes: valueOf('ROI_ENTER', 'objectClasses', []),
        minimumCount: valueOf('COUNT_BELOW', 'min', 1),
        recovery: ast.value.recoverySeconds,
        duration: valueOf('DURATION', 'seconds', 2),
        n: valueOf('N_OF_M', 'n', 3),
        m: valueOf('N_OF_M', 'm', 5),
        cooldown: ast.value.cooldownSeconds,
        movement: valueOf('STATIONARY', 'maxMovement', 0.02),
      });
  },
  { immediate: true },
);
watch(
  () => [props.image, props.imageSize] as const,
  ([image, size]) => {
    still.value = '';
    frameSize.value = size;
    if (image)
      still.value = image.startsWith('data:')
        ? image
        : `data:image/jpeg;base64,${image}`;
  },
  { immediate: true },
);
watch(
  () => props.camera?.id,
  () => {
    still.value = '';
    frameSize.value = undefined;
    preview.value = false;
    canvas.value?.cancel();
    undoStack.value = [];
    redoStack.value = [];
  },
);
function enabled(value: boolean | number | string) {
  if (props.disabled) return;
  canvas.value?.cancel();
  preview.value = false;
  if (!value) {
    previousRule.value = props.modelValue;
    replaceValue('');
    return;
  }
  replaceValue(
    previousRule.value ||
      JSON.stringify(
        props.defaultRule ??
          createRuleAst(props.eventType ?? 'ALGORITHM_EVENT'),
        null,
        2,
      ),
  );
}
function capture() {
  const frame = player.value?.captureFrame();
  if (!frame) {
    message.warning('请等待视频画面');
    return;
  }
  still.value = frame.dataUrl;
  frameSize.value = { width: frame.width, height: frame.height };
  preview.value = false;
  update((rule) => {
    const r = rule.regions[regionIndex.value];
    if (r) {
      r.sourceWidth = frame.width;
      r.sourceHeight = frame.height;
    }
  });
}
function validate() {
  if (canvasBusy.value) {
    message.warning(t('finishBeforeSave'));
    return false;
  }
  if (
    props.modelValue.trim() &&
    (!ast.value ||
      !Array.isArray(ast.value.regions) ||
      !ast.value.regions.length)
  ) {
    message.warning(t('invalidRule'));
    return false;
  }
  for (const item of ast.value?.regions ?? []) {
    const invalid = Array.isArray(item.points)
      ? regionGeometryError(item.points)
      : 'tooFewPoints';
    if (invalid) {
      message.warning(`${item.name}：${t(invalid)}`);
      return false;
    }
  }
  if (
    has('N_OF_M') &&
    Number(valueOf('N_OF_M', 'n', 3)) > Number(valueOf('N_OF_M', 'm', 5))
  ) {
    message.warning('命中帧数不能大于观察窗口帧数');
    return false;
  }
  return true;
}
defineExpose({ validate });
</script>
<template>
  <section class="space-y-4">
    <div class="flex items-center justify-between">
      <div>
        <h4 class="font-semibold">告警条件</h4>
        <p class="mt-1 text-xs text-muted-foreground">{{ t('taskScope') }}</p>
      </div>
      <Switch
        :checked="Boolean(ast)"
        :disabled="disabled || canvasBusy"
        aria-label="启用告警"
        @change="enabled"
      />
    </div>
    <template v-if="ast && region">
      <Form />
      <div class="rounded-lg border p-3">
        <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
          <strong class="text-sm">告警区域</strong
          ><Select
            v-model:value="regionIndex"
            class="min-w-40"
            :disabled="canvasBusy"
            :options="ast.regions.map((r, i) => ({ label: r.name, value: i }))"
          />
        </div>
        <div class="mb-3 flex flex-wrap items-center gap-2">
          <Button
            v-if="camera"
            :disabled="canvasBusy"
            :type="preview ? 'primary' : 'default'"
            @click="preview = !preview"
          >
            {{ preview ? '关闭预览' : '获取摄像头画面' }} </Button
          ><Button v-if="preview" @click="capture">截取当前画面</Button>
          <Button
            v-if="allowTemplateImport"
            :disabled="disabled || canvasBusy || preview"
            @click="loadTemplates"
            >{{ t('importRegion') }}</Button
          >
          <label
            v-if="camera && taskId"
            class="ml-auto flex items-center gap-2 text-sm"
            :title="t('regionDisplayHint')"
          >
            <Switch
              size="small"
              :aria-label="t('showRecognitionRegion')"
              :checked="!displayPrefs.hidden.value.includes(regionDisplayKey)"
              :disabled="!displayPrefs.ready.value || displayPrefs.saving.value"
              @change="
                (value) =>
                  displayPrefs.setVisible(regionDisplayKey, Boolean(value))
              "
            />
            {{ t('showRecognitionRegion') }}
          </label>
        </div>
        <Alert
          v-if="camera && displayPrefs.error.value"
          class="mb-3"
          type="warning"
          :message="displayPrefs.error.value"
        >
          <template #action
            ><Button @click="displayPrefs.reload">{{
              t('retry')
            }}</Button></template
          >
        </Alert>
        <div
          v-if="importOpen && allowTemplateImport"
          class="mb-3 space-y-3 rounded border bg-muted/20 p-3"
        >
          <p class="text-xs text-muted-foreground">{{ t('importHint') }}</p>
          <div class="flex flex-wrap gap-2">
            <Select
              :value="templateId"
              :aria-label="t('template')"
              :placeholder="t('chooseTemplate')"
              class="min-w-48 flex-1"
              show-search
              option-filter-prop="label"
              :loading="templateLoading"
              :disabled="disabled || canvasBusy"
              :options="
                templateRules.map((r) => ({ label: r.name, value: r.id }))
              "
              @change="(value) => loadTemplate(Number(value))"
            />
            <Select
              v-model:value="templateVersionId"
              :aria-label="t('templateVersion')"
              :placeholder="t('templateVersion')"
              class="min-w-28"
              :disabled="disabled || canvasBusy || templateLoading"
              :options="
                templateVersions.map((v) => ({
                  label: `v${v.version}`,
                  value: v.id,
                }))
              "
              @change="templateRegionIndex = 0"
            />
            <Select
              :value="templateRegion ? templateRegionIndex : undefined"
              :aria-label="t('templateRegion')"
              :placeholder="t('templateRegion')"
              class="min-w-36"
              :disabled="disabled || canvasBusy || templateLoading"
              :options="
                (templateVersion?.ast.regions ?? []).map((r, i) => ({
                  label: r.name,
                  value: i,
                }))
              "
              @change="templateRegionIndex = Number($event)"
            />
          </div>
          <Alert
            v-if="templateError"
            type="error"
            :message="templateError"
            show-icon
          >
            <template #action
              ><Button
                @click="templateId ? loadTemplate(templateId) : loadTemplates()"
                >{{ t('retry') }}</Button
              ></template
            >
          </Alert>
          <p
            v-else-if="!templateLoading && !templateRules.length"
            class="text-sm text-muted-foreground"
          >
            {{ t('noTemplates') }}
          </p>
          <p
            v-else-if="
              !templateLoading && templateId && !templateVersions.length
            "
            class="text-sm text-muted-foreground"
          >
            {{ t('noVersions') }}
          </p>
          <div class="flex gap-2">
            <Button
              type="primary"
              :disabled="
                disabled || canvasBusy || templateLoading || !templateRegion
              "
              @click="importRegion"
              >{{ t('applyRegion') }}</Button
            >
            <Button @click="importOpen = false">{{ t('closeImport') }}</Button>
          </div>
        </div>
        <p
          v-if="importedFrom"
          class="mb-3 text-xs text-muted-foreground"
          role="status"
        >
          {{ t('importedFrom') }} {{ importedFrom }}。{{ t('saveToApply') }}
        </p>
        <CameraPreviewPlayer
          v-if="preview && camera"
          ref="player"
          :camera="camera"
          :node-id="nodeId"
          :transport="previewTransport"
          :overlay-enabled="false"
          class="h-[320px]"
        />
        <RuleRegionCanvas
          v-else-if="canvasRegion"
          :key="regionIndex"
          ref="canvas"
          :region="canvasRegion"
          :background="still"
          :disabled="!!disabled"
          :can-undo="undoStack.length > 0"
          :can-redo="redoStack.length > 0"
          max-height="min(440px, 45vh)"
          @change="updatePoints"
          @undo="undo"
          @redo="redo"
          @busy-change="canvasBusy = $event"
        />
        <div class="mt-3 flex items-center gap-3 text-sm">
          <span>目标位置判断</span
          ><Select
            :value="region.pointMode"
            class="w-36"
            :disabled="disabled || canvasBusy"
            :options="[
              { label: '目标底部', value: 'FOOT' },
              { label: '目标中心', value: 'CENTROID' },
            ]"
            @change="
              (value) =>
                update((v) => {
                  const r = v.regions[regionIndex];
                  if (r) r.pointMode = value as typeof r.pointMode;
                })
            "
          />
        </div>
      </div>
      <Alert
        v-if="
          Number(valueOf('N_OF_M', 'n', 3)) > Number(valueOf('N_OF_M', 'm', 5))
        "
        type="error"
        message="命中帧数不能大于观察窗口帧数"
      />
    </template>
    <p v-else class="text-sm text-muted-foreground">
      仅展示识别结果，启用后按区域、持续时间和连续帧生成告警。
    </p>
  </section>
</template>
