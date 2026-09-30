import type { Ref } from 'vue';

import { computed, ref } from 'vue';

import { useAccessStore, useUserStore } from '@vben/stores';

import { useStorage } from '@vueuse/core';

import {
  DEFAULT_PREVIEW_BUFFER_MS,
  normalizePreviewBuffer,
} from './preview-buffer';

/** A viewer preference shared by previews, isolated by account and local gateway. */
export function usePreviewBuffer(local: Ref<boolean>) {
  const access = useAccessStore();
  const user = useUserStore();
  const storageError = ref(false);
  const key = computed(() =>
    local.value
      ? 'linsight:preview-buffer:edge'
      : `linsight:preview-buffer:${access.tenantId}:${user.userInfo?.id ?? 'anonymous'}`,
  );
  const saved = useStorage(key, DEFAULT_PREVIEW_BUFFER_MS, undefined, {
    flush: 'sync',
    onError: () => {
      storageError.value = true;
    },
    serializer: {
      read: (value) =>
        normalizePreviewBuffer(value.trim() ? Number(value) : undefined),
      write: (value) => String(normalizePreviewBuffer(value)),
    },
  });
  return {
    delayMs: computed(() => normalizePreviewBuffer(saved.value)),
    storageError,
    setDelay(value: number) {
      storageError.value = false;
      saved.value = normalizePreviewBuffer(value);
    },
  };
}
