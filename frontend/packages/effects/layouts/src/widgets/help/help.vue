<script lang="ts" setup>
import { $t } from '@vben/locales';

import { useVbenModal } from '@vben-core/popup-ui';

import { useMagicKeys, whenever } from '@vueuse/core';

defineOptions({
  name: 'Help',
});

const keys = useMagicKeys();
whenever(keys['Alt+KeyH']!, () => {
  modalApi.open();
});

const [Modal, modalApi] = useVbenModal({
  draggable: true,
  overlayBlur: 5,
  footer: false,
  onCancel() {
    modalApi.close();
  },
});
</script>
<template>
  <Modal class="w-1/3" :title="$t('ui.widgets.qa')">
    <div class="text-muted-foreground space-y-3 p-4 text-sm">
      <p class="text-foreground text-base font-medium">LInsight 平台帮助</p>
      <p>
        当前为视频智能分析平台基座版本，已启用系统管理、基础设施和运行总览。
      </p>
      <p>开发说明与页面需求请查看仓库根目录的 docs 目录。</p>
    </div>
  </Modal>
</template>
