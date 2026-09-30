import { oxlintConfig } from '@vben/oxlint-config';

import { defineConfig } from 'oxlint';

export default defineConfig({
  ...oxlintConfig,
  rules: {
    ...oxlintConfig.rules,
    // Vue modules commonly expose an `error` ref; requiring the same identifier
    // for catch parameters creates accidental shadowing and defeats type narrowing.
    'unicorn/catch-error-name': 'off',
  },
});
