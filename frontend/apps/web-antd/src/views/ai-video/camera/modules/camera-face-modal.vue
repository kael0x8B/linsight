<script setup lang="ts">
import { ref } from 'vue';

import { useVbenModal } from '@vben/common-ui';

import { $t } from '#/locales';

import FaceConfig from './camera-face-config.vue';
const emit = defineEmits(['success']);
const data = ref<{
  cameraId: number;
  entryAccessId?: number;
  nodeId: number;
}>();
const [Modal, modalApi] = useVbenModal({
  showConfirmButton: false,
  onOpenChange(open) {
    data.value = open ? modalApi.getData() : undefined;
  },
});
</script>
<template>
  <Modal
    class="ai-dialog w-[760px]"
    :title="$t('camera-face.algorithm')"
    content-class="ai-dialog-content"
    footer-class="ai-dialog-footer"
  >
    <FaceConfig
      v-if="data"
      :camera-id="data.cameraId"
      :node-id="data.nodeId"
      :entry-access-id="data.entryAccessId"
      @success="emit('success')"
    />
  </Modal>
</template>
