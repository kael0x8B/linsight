<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue';

import { Button, InputNumber, Popover } from 'ant-design-vue';

import { $t } from '#/locales';

import {
  DEFAULT_PREVIEW_BUFFER_MS,
  MAX_PREVIEW_BUFFER_MS,
} from './preview-buffer';

const props = defineProps<{
  actualMs?: number;
  disabled?: boolean;
  modelValue: number;
  storageError: boolean;
}>();
const emit = defineEmits<{ 'update:modelValue': [value: number] }>();
const open = ref(false);
const draft = ref<number | undefined>(props.modelValue);
const valid = computed(
  () =>
    typeof draft.value === 'number' &&
    Number.isInteger(draft.value) &&
    draft.value >= 0 &&
    draft.value <= MAX_PREVIEW_BUFFER_MS,
);
watch(open, (value) => {
  if (value) draft.value = props.modelValue;
});
async function apply() {
  if (!valid.value || typeof draft.value !== 'number') return;
  emit('update:modelValue', draft.value);
  await nextTick();
  if (!props.storageError) open.value = false;
}
function popupContainer() {
  // Avoid clipping inside small wall tiles, and stay within the fullscreen root.
  return document.fullscreenElement instanceof HTMLElement
    ? document.fullscreenElement
    : document.body;
}
</script>

<template>
  <span class="preview-buffer-control" @click.stop @dblclick.stop>
    <Popover
      v-model:open="open"
      trigger="click"
      placement="topRight"
      :title="$t('page.aiVideo.recognition.syncBuffer')"
      :get-popup-container="popupContainer"
    >
      <template #content>
        <div class="preview-buffer-settings" @click.stop @dblclick.stop>
          <InputNumber
            v-model:value="draft"
            class="w-full"
            :min="0"
            :max="MAX_PREVIEW_BUFFER_MS"
            :step="100"
            :precision="0"
            addon-after="ms"
            :aria-label="$t('page.aiVideo.recognition.syncBuffer')"
            @press-enter="apply"
          />
          <p class="mt-2 text-xs text-muted-foreground">
            {{ $t('page.aiVideo.recognition.syncBufferHint') }}
          </p>
          <p class="mt-2 text-xs text-muted-foreground">
            {{ $t('page.aiVideo.recognition.syncBufferSavedLocally') }}
          </p>
          <p
            v-if="actualMs !== undefined"
            class="mt-2 text-xs text-muted-foreground"
          >
            {{ $t('page.aiVideo.recognition.syncBufferActual', [actualMs]) }}
          </p>
          <p
            v-if="storageError"
            role="alert"
            class="mt-2 text-xs text-destructive"
          >
            {{ $t('page.aiVideo.recognition.syncBufferSaveFailed') }}
          </p>
          <div class="mt-3 flex justify-end gap-2">
            <Button size="small" @click="draft = DEFAULT_PREVIEW_BUFFER_MS">{{
              $t('page.aiVideo.recognition.syncBufferReset')
            }}</Button>
            <Button
              size="small"
              type="primary"
              :disabled="!valid"
              @click="apply"
            >
              {{ $t('page.aiVideo.recognition.syncBufferApply') }}
            </Button>
          </div>
        </div>
      </template>
      <button
        type="button"
        class="preview-buffer-button"
        :disabled="disabled"
        :aria-label="$t('page.aiVideo.recognition.syncBufferSettings')"
        :aria-expanded="open"
      >
        {{ $t('page.aiVideo.recognition.syncBufferValue', [modelValue]) }}
        <span aria-hidden="true">⚙</span>
      </button>
    </Popover>
  </span>
</template>

<style scoped>
.preview-buffer-control {
  pointer-events: auto;
}

.preview-buffer-settings {
  width: 280px;
  max-width: calc(100vw - 48px);
}

.preview-buffer-button {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 2px 6px;
  color: inherit;
  cursor: pointer;
  background: rgb(255 255 255 / 8%);
  border: 1px solid rgb(255 255 255 / 25%);
  border-radius: 4px;
}

.preview-buffer-button:hover,
.preview-buffer-button:focus-visible {
  background: rgb(255 255 255 / 18%);
  outline: 2px solid #60a5fa;
  outline-offset: 2px;
}

.preview-buffer-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}
</style>
