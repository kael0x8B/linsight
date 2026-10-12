<script lang="ts" setup>
import type { AiVideoCameraApi } from '#/api/ai-video/camera';

import { onBeforeUnmount, ref } from 'vue';
import { useRouter } from 'vue-router';

import { useAccess } from '@vben/access';
import { useVbenDrawer, useVbenModal } from '@vben/common-ui';

import { Alert, Button, Space, Spin } from 'ant-design-vue';

import { getCamera } from '#/api/ai-video/camera';
import CameraCapabilities from '#/components/ai-video/camera-capabilities.vue';
import { $t } from '#/locales';
import { gatewayLocation } from '#/views/ai-video/node/presentation';

import AlgorithmAssignment from './camera-algorithm-modal.vue';
const emit = defineEmits(['success']);

const router = useRouter();

const { hasAccessByCodes } = useAccess();
const camera = ref<AiVideoCameraApi.Camera>();
const loading = ref(false);
const failed = ref(false);
let generation = 0;
let opened = false;
let timer: ReturnType<typeof setTimeout> | undefined;
const [AssignmentModal, assignmentApi] = useVbenModal({
  connectedComponent: AlgorithmAssignment,
  destroyOnClose: true,
});
function addAlgorithm() {
  if (camera.value) assignmentApi.setData({ cameras: [camera.value] }).open();
}
async function refresh(quiet = false) {
  const id = camera.value?.id;
  if (!id || !opened) return;
  if (timer) clearTimeout(timer);
  const request = ++generation;
  if (!quiet) loading.value = true;
  try {
    const result = await getCamera(id);
    if (request === generation) {
      camera.value = result;
      failed.value = false;
    }
  } catch {
    if (request === generation) failed.value = true;
  } finally {
    if (request === generation) {
      loading.value = false;
      if (opened) timer = setTimeout(() => void refresh(true), 5000);
    }
  }
}
async function changed() {
  emit('success');
  await refresh();
}
const [Drawer, drawerApi] = useVbenDrawer({
  showConfirmButton: false,
  onOpenChange(open) {
    opened = open;
    if (open) {
      camera.value = drawerApi.getData<AiVideoCameraApi.Camera>();
      void refresh();
    } else {
      generation += 1;
      if (timer) clearTimeout(timer);
    }
  },
});
onBeforeUnmount(() => {
  opened = false;
  generation += 1;
  if (timer) clearTimeout(timer);
});
</script>
<template>
  <Drawer
    :title="$t('page.aiVideo.cameraAlgorithms.title')"
    class="ai-dialog w-[560px]"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <AssignmentModal @success="changed" />
    <h3 class="mb-2 text-base font-semibold">{{ camera?.name }}</h3>
    <p class="mb-4 text-sm text-muted-foreground">
      查看此摄像头在各网关上的识别状态，启停和参数在所属网关统一管理。
    </p>
    <Space class="mb-4">
      <Button
        v-if="hasAccessByCodes(['ai-video:task:create'])"
        type="primary"
        :disabled="camera?.status !== 0"
        @click="addAlgorithm"
      >
        {{ $t('page.aiVideo.cameraAlgorithms.add') }}
      </Button>
      <Button :loading="loading" @click="refresh(false)">
        {{ $t('page.aiVideo.recognition.refresh') }}
      </Button>
    </Space>
    <Alert
      v-if="failed"
      class="mb-3"
      show-icon
      type="error"
      :message="$t('page.aiVideo.recognition.loadFailed')"
    />
    <Spin :spinning="loading">
      <CameraCapabilities :capabilities="camera?.recognitionCapabilities">
        <template #actions="{ capability }">
          <div class="mt-3 border-t pt-3">
            <Button
              v-if="hasAccessByCodes(['ai-video:node:query'])"
              size="small"
              type="primary"
              @click="
                drawerApi.close();
                router.push(
                  gatewayLocation(capability.nodeId, 'algorithms', camera?.id),
                );
              "
            >
              管理此网关的算法
            </Button>
          </div>
        </template>
      </CameraCapabilities>
    </Spin>
    <p
      class="mt-5 rounded-lg bg-muted p-3 text-xs leading-6 text-muted-foreground"
    >
      同一摄像头可分配给不同网关，进入对应网关可独立启停，不影响其他网关。
    </p>
  </Drawer>
</template>
