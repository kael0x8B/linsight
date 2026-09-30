import process from 'node:process';

import { defineConfig } from '@vben/vite-config';

export default defineConfig(async () => {
  const backendTarget =
    process.env.LINSIGHT_DEV_PROXY_TARGET ?? 'http://127.0.0.1:48888';

  return {
    application: {},
    vite: {
      // The form designer imports CodeMirror's CommonJS entry from a Vue file.
      optimizeDeps: {
        include: [
          '@form-create/antd-designer > js-beautify',
          '@form-create/antd-designer > codemirror/lib/codemirror',
          '@form-create/antd-designer > codemirror/mode/javascript/javascript',
          '@form-create/antd-designer > codemirror/addon/hint/show-hint',
          '@form-create/antd-designer > codemirror/addon/hint/javascript-hint',
        ],
      },
      build: {
        rollupOptions: {
          input: { index: 'index.html', gateway: 'gateway.html' },
        },
      },
      server: {
        allowedHosts: true,
        proxy: {
          '/gateway-api': {
            target:
              process.env.LINSIGHT_GATEWAY_PROXY_TARGET ??
              'http://127.0.0.1:48901',
          },
          '/admin-api': {
            changeOrigin: true,
            // 本地开发统一转发到 LInsight 后端，保留 /admin-api 前缀。
            target: backendTarget,
            ws: true,
          },
          '/infra/ws': {
            changeOrigin: true,
            // Overlay WebSocket 与管理 API 保持同源，避免浏览器拦截跨端口连接。
            target: backendTarget,
            ws: true,
          },
        },
      },
    },
  };
});
