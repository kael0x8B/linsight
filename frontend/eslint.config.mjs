import { defineConfig } from '@vben/eslint-config';

// Oxfmt is the repository's canonical formatter. Keep ESLint focused on semantic
// Vue rules so the two quality-gate stages do not rewrite the same templates in
// opposite directions.
export default defineConfig([
  {
    rules: {
      'vue/html-closing-bracket-newline': 'off',
      'vue/html-quotes': 'off',
      'vue/multiline-html-element-content-newline': 'off',
    },
  },
]);
