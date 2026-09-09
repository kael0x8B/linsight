import {
  defineOverridesPreferences,
  definePreferencesExtension,
} from '@vben/preferences';

interface WebAntdPreferencesExtension {
  defaultTableSize: number;
  enableFormFullscreen: boolean;
  reportTitle: string;
  tenantMode: 'multi' | 'single';
}

/**
 * @description 项目配置文件
 * 只需要覆盖项目中的一部分配置，不需要的配置不用覆盖，会自动使用默认配置
 * !!! 更改配置后请清空缓存，否则可能不生效
 */
export const overridesPreferences = defineOverridesPreferences({
  // overrides
  app: {
    /** 后端路由模式 */
    accessMode: 'backend',
    contentCompact: 'wide',
    contentCompactWidth: 1680,
    defaultHomePath: '/dashboard/analytics',
    enableCheckUpdates: false,
    enableRefreshToken: true,
    name: import.meta.env.VITE_APP_TITLE,
  },
  breadcrumb: {
    enable: true,
    showIcon: false,
    styleType: 'normal',
  },
  footer: {
    /** 默认关闭 footer 页脚，因为有一定遮挡 */
    enable: false,
    fixed: false,
  },
  copyright: {
    companyName: import.meta.env.VITE_APP_TITLE,
    companySiteLink: '',
    enable: false,
  },
  header: {
    height: 52,
  },
  logo: {
    fit: 'contain',
    logoMode: 'icon',
    showText: true,
    source: '/linsight-mark.svg',
    sourceDark: '/linsight-mark.svg',
  },
  navigation: {
    accordion: true,
    split: true,
    styleType: 'rounded',
  },
  sidebar: {
    collapseWidth: 60,
    width: 232,
  },
  tabbar: {
    height: 38,
    showIcon: false,
    styleType: 'plain',
  },
  theme: {
    colorDestructive: 'hsl(0 72% 51%)',
    colorPrimary: 'hsl(217 91% 60%)',
    colorSuccess: 'hsl(142 71% 45%)',
    colorWarning: 'hsl(32 95% 44%)',
    mode: 'light',
    radius: '0.5',
  },
  transition: {
    enable: true,
    loading: true,
    name: 'fade',
    progress: true,
  },
  widget: {
    languageToggle: false,
    lockScreen: false,
    timezone: false,
  },
});

export const preferencesExtension =
  definePreferencesExtension<WebAntdPreferencesExtension>({
    tabLabel: 'preferences.antd.tabLabel',
    title: 'preferences.antd.title',
    fields: [
      {
        component: 'switch',
        defaultValue: true,
        key: 'enableFormFullscreen',
        label: 'preferences.antd.fields.enableFormFullscreen.label',
        tip: 'preferences.antd.fields.enableFormFullscreen.tip',
      },
      {
        component: 'select',
        defaultValue: 'single',
        key: 'tenantMode',
        label: 'preferences.antd.fields.tenantMode.label',
        options: [
          {
            label: 'preferences.antd.fields.tenantMode.options.single.label',
            value: 'single',
          },
          {
            label: 'preferences.antd.fields.tenantMode.options.multi.label',
            value: 'multi',
          },
        ],
      },
      {
        component: 'number',
        componentProps: {
          max: 200,
          min: 10,
          step: 10,
        },
        defaultValue: 20,
        key: 'defaultTableSize',
        label: 'preferences.antd.fields.defaultTableSize.label',
      },
      {
        component: 'input',
        defaultValue: '',
        key: 'reportTitle',
        label: 'preferences.antd.fields.reportTitle.label',
        placeholder: 'preferences.antd.fields.reportTitle.placeholder',
      },
    ],
  });
