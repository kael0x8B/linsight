import { fileURLToPath } from 'node:url';
import { mergeConfig } from 'vitest/config';
import base from './vitest.config';
const path = (value: string) => fileURLToPath(new URL(value, import.meta.url));
export default mergeConfig(base, {
  resolve: { alias: {
    '#': path('./apps/web-antd/src'),
    '@vben/common-ui': path('./packages/effects/common-ui/src/index.ts'),
    '@vben/icons': path('./packages/icons/src/index.ts'),
    'ant-design-vue': path('./apps/web-antd/node_modules/ant-design-vue'),
  } },
  test: { include: ['tests/node-*.test.ts'] },
});
