import type { Ref } from 'vue';

import { computed, onScopeDispose, ref, watch } from 'vue';

import { useAccessStore, useUserStore } from '@vben/stores';

import { requestClient } from '#/api/request';

export function recognitionRegionKey(layerKey: string) {
  return `roi-${layerKey}`;
}

// Shared reactive state across platform preview, video wall and node workbench.
// Server owns platform persistence; Edge browser preferences are deliberately isolated.
const records = new Map<string, ReturnType<typeof makeRecord>>();
function makeRecord() {
  return {
    hidden: ref<string[]>([]),
    loaded: ref(false),
    saving: ref(false),
    error: ref(''),
    request: undefined as Promise<void> | undefined,
  };
}
export function useDisplayPreferences(
  cameraId: Ref<number | undefined>,
  local = false,
) {
  const access = useAccessStore();
  const user = useUserStore();
  const key = computed(() =>
    local
      ? `edge-display:${cameraId.value}`
      : `${access.tenantId}:${user.userInfo?.id}:${cameraId.value}`,
  );
  const record = computed(() => {
    if (!records.has(key.value)) records.set(key.value, makeRecord());
    return records.get(key.value)!;
  });
  async function load(force = false) {
    const id = cameraId.value;
    const row = record.value;
    if (!id || row.saving.value || row.request || (row.loaded.value && !force))
      return row.request;
    row.request = (async () => {
      try {
        const values = local
          ? JSON.parse(localStorage.getItem(key.value) || '[]')
          : await requestClient.get<string[]>(
              '/ai-video/camera/display-preference/get',
              { params: { cameraId: id } },
            );
        row.hidden.value = Array.isArray(values)
          ? // Retire the old camera-wide ROI switch. Each algorithm owns its ROI preference.
            values.filter(
              (v) => typeof v === 'string' && v !== 'recognition-regions',
            )
          : [];
        row.loaded.value = true;
        row.error.value = '';
      } catch {
        row.error.value = '图层偏好读取失败，暂按全部显示；请重试。';
      } finally {
        row.request = undefined;
      }
    })();
    return row.request;
  }
  async function setVisible(layerKey: string, visible: boolean) {
    const row = record.value;
    const id = cameraId.value;
    if (!id || row.saving.value || !row.loaded.value) return;
    const previous = row.hidden.value;
    const next = visible
      ? previous.filter((v) => v !== layerKey)
      : [...new Set([...previous, layerKey])];
    row.hidden.value = next;
    row.saving.value = true;
    try {
      if (local) localStorage.setItem(key.value, JSON.stringify(next));
      else
        await requestClient.put('/ai-video/camera/display-preference/update', {
          cameraId: id,
          hiddenLayers: next,
        });
      row.error.value = '';
    } catch {
      row.hidden.value = previous;
      row.error.value = '图层偏好保存失败，已恢复原设置。';
    } finally {
      row.saving.value = false;
    }
  }
  watch(key, () => void load(), { immediate: true });
  function onFocus() {
    void load(true);
  }
  function onVisible() {
    if (!document.hidden) onFocus();
  }
  document.addEventListener('visibilitychange', onVisible);
  onScopeDispose(() =>
    document.removeEventListener('visibilitychange', onVisible),
  );
  window.addEventListener('focus', onFocus);
  onScopeDispose(() => window.removeEventListener('focus', onFocus));
  return {
    hidden: computed(() => record.value.hidden.value),
    saving: computed(() => record.value.saving.value),
    ready: computed(() => record.value.loaded.value),
    error: computed(() => record.value.error.value),
    setVisible,
    reload: () => load(true),
  };
}
