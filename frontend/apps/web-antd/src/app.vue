<script lang="ts" setup>
import { computed } from 'vue';

import { useAntdDesignTokens } from '@vben/hooks';
import { preferences, usePreferences } from '@vben/preferences';

import { App, ConfigProvider, theme } from 'ant-design-vue';

import { antdLocale } from '#/locales';

defineOptions({ name: 'App' });

const { isDark } = usePreferences();
const { tokens } = useAntdDesignTokens();

const tokenTheme = computed(() => {
  const algorithm = isDark.value
    ? [theme.darkAlgorithm]
    : [theme.defaultAlgorithm];

  // antd 紧凑模式算法
  if (preferences.app.compact) {
    algorithm.push(theme.compactAlgorithm);
  }

  return {
    algorithm,
    token: {
      ...tokens,
      borderRadius: 8,
      borderRadiusLG: 12,
      colorPrimary: '#2563eb',
      controlHeight: 34,
      fontFamily:
        'Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif',
      fontSize: 14,
      lineHeight: 1.5,
    },
    components: {
      Button: { borderRadius: 7, controlHeight: 34 },
      Card: { borderRadiusLG: 12, headerFontSize: 14 },
      Drawer: { paddingLG: 20 },
      Input: { activeShadow: '0 0 0 2px rgb(37 99 235 / 12%)' },
      Modal: { borderRadiusLG: 12 },
      Table: { cellPaddingBlock: 12, cellPaddingInline: 14 },
    },
  };
});
</script>

<template>
  <ConfigProvider :locale="antdLocale" :theme="tokenTheme">
    <App>
      <RouterView />
    </App>
  </ConfigProvider>
</template>
