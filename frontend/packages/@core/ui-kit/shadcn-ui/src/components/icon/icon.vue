<script setup lang="ts">
import type { Component } from 'vue';

import { computed } from 'vue';

import {
  Blocks,
  BrainCircuit,
  Cctv,
  ClipboardCheck,
  IconDefault,
  IconifyIcon,
  LayoutDashboard,
  LayoutGrid,
  LibraryBig,
  MonitorCog,
  MonitorPlay,
  PlayCircle,
  ScanLine,
  ScanSearch,
  ScrollText,
  Server,
  ServerCog,
  Settings2,
  Siren,
  Video,
  Webhook,
  Workflow,
  Wrench,
} from '@vben-core/icons';
import {
  isFunction,
  isHttpUrl,
  isObject,
  isString,
} from '@vben-core/shared/utils';

const props = defineProps<{
  // 没有是否显示默认图标
  fallback?: boolean;
  icon?: Component | Function | string;
}>();

/**
 * 核心导航图标必须随控制台产物本地发布，不能依赖浏览器访问 Iconify CDN。
 * key 与后端 system_menu.icon 保持一致；其他非导航图标仍沿用 Iconify。
 */
const localMenuIcons: Record<string, Component> = {
  'ep:monitor': MonitorCog,
  'ep:tools': Wrench,
  'lucide:blocks': Blocks,
  'lucide:brain-circuit': BrainCircuit,
  'lucide:cctv': Cctv,
  'lucide:clipboard-check': ClipboardCheck,
  'lucide:layout-dashboard': LayoutDashboard,
  'lucide:layout-grid': LayoutGrid,
  'lucide:library-big': LibraryBig,
  'lucide:monitor-play': MonitorPlay,
  'lucide:play-circle': PlayCircle,
  'lucide:scan-line': ScanLine,
  'lucide:scan-search': ScanSearch,
  'lucide:scroll-text': ScrollText,
  'lucide:server': Server,
  'lucide:server-cog': ServerCog,
  'lucide:settings-2': Settings2,
  'lucide:siren': Siren,
  'lucide:video': Video,
  'lucide:webhook': Webhook,
  'lucide:workflow': Workflow,
};

const isRemoteIcon = computed(() => {
  return isString(props.icon) && isHttpUrl(props.icon);
});

const isComponent = computed(() => {
  const { icon } = props;
  return !isString(icon) && (isObject(icon) || isFunction(icon));
});

const localMenuIcon = computed(() => {
  return isString(props.icon) ? localMenuIcons[props.icon] : undefined;
});
</script>

<template>
  <component :is="icon as Component" v-if="isComponent" v-bind="$attrs" />
  <component :is="localMenuIcon" v-else-if="localMenuIcon" v-bind="$attrs" />
  <img v-else-if="isRemoteIcon" :src="icon as string" v-bind="$attrs" />
  <IconifyIcon v-else-if="icon" v-bind="$attrs" :icon="icon as string" />
  <IconDefault v-else-if="fallback" v-bind="$attrs" />
</template>
