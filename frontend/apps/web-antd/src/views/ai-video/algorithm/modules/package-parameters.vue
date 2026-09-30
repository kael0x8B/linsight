<script setup lang="ts">
import type { VbenFormSchema as FormSchema } from '#/adapter/form';
import type {
  AlgorithmManifest,
  ParameterField,
} from '#/api/ai-video/algorithm/package';
import type { AiVideoCameraApi } from '#/api/ai-video/camera';
import type { AiVideoRecognitionLibraryApi } from '#/api/ai-video/recognition-library';
import type { PreviewTransport } from '#/components/ai-video/preview-transport';

import { computed, ref, watch } from 'vue';

import { Alert, Button, message, Select } from 'ant-design-vue';

import { useVbenForm } from '#/adapter/form';
import {
  getRecognitionEntryPage,
  getRecognitionLibraryPage,
} from '#/api/ai-video/recognition-library';
import CameraPreviewPlayer from '#/components/ai-video/camera-preview-player.vue';

const props = defineProps<{
  camera?: Pick<
    AiVideoCameraApi.Camera,
    'code' | 'id' | 'name' | 'onlineStatus' | 'status'
  >;
  gatewayResources?: boolean;
  initial?: Record<string, unknown>;
  local?: boolean;
  manifest: Pick<AlgorithmManifest, 'defaultParameters' | 'parameterSchema'>;
  nodeId?: number;
  options?: Record<string, { label: string; value: number }[]>;
  previewTransport?: PreviewTransport;
  snapshotImage?: string;
}>();
const error = ref('');
const localResources = computed(() => props.local || props.gatewayResources);
const player = ref<InstanceType<typeof CameraPreviewPlayer>>();
const image = ref('');
const preview = ref(false);
const selectedRoi = ref('');
const rectangle = ref({ x: 0, y: 0, width: 1, height: 1 });
let anchor: undefined | { x: number; y: number };
let generation = 0;
const roiFields = computed(() =>
  Object.entries(props.manifest.parameterSchema.properties).filter(
    ([, field]) => field['x-widget'] === 'roi',
  ),
);
const [Form, form] = useVbenForm({
  showDefaultActions: false,
  layout: 'vertical',
  wrapperClass: 'grid-cols-1 sm:grid-cols-2',
  schema: [],
});
function fields(
  properties: Record<string, ParameterField>,
  required: string[],
  prefix = '',
): FormSchema[] {
  return Object.entries(properties).flatMap(([key, field]) => {
    const name = prefix + key;
    if (field.type === 'object')
      return fields(
        field.properties ?? {},
        (field as ParameterField & { required?: string[] }).required ?? [],
        `${name}__`,
      );
    let component: FormSchema['component'] = 'Input';
    if (field.type === 'boolean') component = 'Switch';
    else if (['integer', 'number'].includes(field.type))
      component = 'InputNumber';
    const componentProps: Record<string, unknown> = {};
    if (field.enum) {
      component = 'Select';
      componentProps.options = field.enum.map((value) => ({
        label: String(value),
        value,
      }));
    }
    if (field.type === 'number' || field.type === 'integer')
      Object.assign(componentProps, {
        min: field.minimum,
        max: field.maximum,
        step: field.type === 'integer' ? 1 : 0.01,
      });
    if (field['x-widget'] === 'person-library') {
      component = 'Select';
      Object.assign(componentProps, {
        options: props.options?.[name] ?? [],
        disabled: localResources.value,
        onChange: (id: number) => void loadPeople(name, id),
      });
    } else if (field['x-widget'] === 'people') {
      component = 'Select';
      Object.assign(componentProps, {
        options: props.options?.[name] ?? [],
        mode: 'multiple',
        placeholder: field.minItems
          ? '请选择指定人员'
          : '不选择表示库内全部有效人员',
      });
    } else if (field.type === 'array') {
      component = 'Select';
      Object.assign(componentProps, { mode: 'tags', tokenSeparators: [','] });
    }
    componentProps.class = component === 'Switch' ? 'w-auto' : 'w-full';
    return [
      {
        fieldName: name,
        label: field.title || name,
        component,
        componentProps,
        help:
          field['x-widget'] === 'person-library' && localResources.value
            ? '使用当前网关已同步的人员库。'
            : field.description,
        rules:
          required.includes(key) && field.type !== 'boolean'
            ? 'required'
            : undefined,
      },
    ];
  });
}
function flatten(
  values: Record<string, unknown>,
  prefix = '',
): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(values).flatMap(([key, value]) =>
      value && typeof value === 'object' && !Array.isArray(value)
        ? Object.entries(
            flatten(value as Record<string, unknown>, `${prefix}${key}__`),
          )
        : [[prefix + key, value]],
    ),
  );
}
async function loadPeople(
  libraryField: string,
  libraryId: number,
  reset = true,
) {
  if (localResources.value) return;
  const peopleFields = Object.entries(
    props.manifest.parameterSchema.properties,
  ).filter(
    ([, field]) =>
      field['x-widget'] === 'people' &&
      field['x-library-field'] === libraryField,
  );
  if (peopleFields.length === 0 || !libraryId) return;
  try {
    const people: AiVideoRecognitionLibraryApi.Entry[] = [];
    let pageNo = 1;
    while (true) {
      const page = await getRecognitionEntryPage({
        libraryId,
        status: 0,
        featureStatus: 'READY',
        pageNo,
        pageSize: 100,
      });
      people.push(...page.list);
      if (people.length >= page.total || page.list.length === 0) break;
      pageNo++;
    }
    await form.updateSchema(
      peopleFields.map(([fieldName]) => ({
        fieldName,
        componentProps: {
          options: people.map((p) => ({ label: p.name, value: p.id })),
        },
      })),
    );
    if (reset)
      await form.setValues(
        Object.fromEntries(peopleFields.map(([key]) => [key, []])),
      );
  } catch {
    error.value = '参与比对人员加载失败，请重新选择人员库。';
  }
}
watch(
  () => props.manifest,
  async (manifest) => {
    const current = ++generation;
    error.value = '';
    image.value = props.snapshotImage
      ? `data:image/jpeg;base64,${props.snapshotImage}`
      : '';
    preview.value = false;
    selectedRoi.value = roiFields.value[0]?.[0] ?? '';
    const schema = fields(
      manifest.parameterSchema.properties,
      manifest.parameterSchema.required ?? [],
    );
    await form.setState({ schema });
    await form.resetForm();
    const values = { ...manifest.defaultParameters, ...props.initial };
    const names = new Set(schema.map((field) => field.fieldName));
    await form.setValues(
      Object.fromEntries(
        Object.entries(flatten(values)).filter(([key]) => names.has(key)),
      ),
    );
    if (values[selectedRoi.value])
      rectangle.value = values[selectedRoi.value] as typeof rectangle.value;
    const libraryFields = Object.entries(
      manifest.parameterSchema.properties,
    ).filter(([, field]) => field['x-widget'] === 'person-library');
    if (libraryFields.length > 0 && !localResources.value) {
      try {
        const libraries: AiVideoRecognitionLibraryApi.Library[] = [];
        for (let pageNo = 1; ; pageNo++) {
          const page = await getRecognitionLibraryPage({
            libraryType: 'FACE',
            status: 0,
            pageNo,
            pageSize: 100,
          });
          libraries.push(...page.list);
          if (libraries.length >= page.total || page.list.length === 0) break;
        }
        if (current !== generation) return;
        await form.updateSchema(
          libraryFields.map(([fieldName]) => ({
            fieldName,
            componentProps: {
              options: libraries.map((l) => ({ label: l.name, value: l.id })),
            },
          })),
        );
        for (const [key] of libraryFields)
          if (values[key]) await loadPeople(key, Number(values[key]), false);
      } catch {
        error.value = '人员库加载失败，请检查权限后重试。';
      }
    }
  },
  { immediate: true },
);
function capture() {
  const frame = player.value?.captureFrame();
  if (!frame) {
    message.warning('请等待视频画面');
    return;
  }
  image.value = frame.dataUrl;
  preview.value = false;
}
function point(event: PointerEvent) {
  const box = (event.currentTarget as SVGSVGElement).getBoundingClientRect();
  return {
    x: Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)),
    y: Math.max(0, Math.min(1, (event.clientY - box.top) / box.height)),
  };
}
function begin(event: PointerEvent) {
  if (event.button !== 0) return;
  anchor = point(event);
  (event.currentTarget as SVGSVGElement).setPointerCapture(event.pointerId);
}
function move(event: PointerEvent) {
  if (!anchor) return;
  const p = point(event);
  rectangle.value = {
    x: Math.min(anchor.x, p.x),
    y: Math.min(anchor.y, p.y),
    width: Math.abs(p.x - anchor.x),
    height: Math.abs(p.y - anchor.y),
  };
}
function end(event: PointerEvent) {
  move(event);
  anchor = undefined;
  void form.setValues(flatten({ [selectedRoi.value]: rectangle.value }));
}
async function values() {
  const validation = await form.validate();
  if (error.value || !validation.valid) return;
  const result: Record<string, unknown> = {};
  const names = new Set(
    fields(
      props.manifest.parameterSchema.properties,
      props.manifest.parameterSchema.required ?? [],
    ).map((field) => field.fieldName),
  );
  for (const [key, value] of Object.entries(await form.getValues())) {
    if (!names.has(key) || value === undefined || value === null) continue;
    const parts = key.split('__');
    let target = result;
    for (const part of parts.slice(0, -1)) {
      target[part] ??= {};
      target = target[part] as Record<string, unknown>;
    }
    target[parts.at(-1)!] = value;
  }
  for (const [key, field] of Object.entries(
    props.manifest.parameterSchema.properties,
  )) {
    if (field.type !== 'array') continue;
    const selected = Array.isArray(result[key])
      ? (result[key] as unknown[])
      : [];
    if (
      selected.length < (field.minItems ?? 0) ||
      selected.length > (field.maxItems ?? 4096)
    ) {
      message.warning(
        `${field.title || key}的选择数量应为 ${field.minItems ?? 0} 至 ${field.maxItems ?? 4096} 项`,
      );
      return;
    }
  }
  return result;
}
defineExpose({ values });
</script>
<template>
  <div class="space-y-4">
    <Alert v-if="error" :message="error" type="error" show-icon />
    <div
      v-if="roiFields.length && (camera || image)"
      class="rounded-lg border p-3"
    >
      <div class="mb-3 flex items-center gap-2">
        <Select
          v-model:value="selectedRoi"
          class="w-48"
          :options="
            roiFields.map(([value, field]) => ({
              value,
              label: field.title || value,
            }))
          "
        /><Button
          @click="
            preview = true;
            image = '';
          "
        >
          从摄像头画面设置区域
        </Button>
      </div>
      <template v-if="preview">
        <div class="h-64">
          <CameraPreviewPlayer
            ref="player"
            :camera="camera"
            :node-id="nodeId"
            :transport="previewTransport"
            :overlay-enabled="false"
            compact
          />
        </div>
        <Button class="mt-2" @click="capture">截取画面并框选</Button>
      </template>
      <div v-if="image" class="relative">
        <img :src="image" alt="区域配置参考画面" class="block w-full" /><svg
          class="absolute inset-0 h-full w-full touch-none"
          viewBox="0 0 1 1"
          preserveAspectRatio="none"
          @pointerdown="begin"
          @pointermove="move"
          @pointerup="end"
        >
          <rect
            :x="rectangle.x"
            :y="rectangle.y"
            :width="rectangle.width"
            :height="rectangle.height"
            fill="#1677ff33"
            stroke="#1677ff"
            stroke-width=".006"
          />
        </svg>
      </div>
    </div>
    <Form />
  </div>
</template>
