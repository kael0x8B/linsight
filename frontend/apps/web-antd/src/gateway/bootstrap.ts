import { createApp } from 'vue';
import { createRouter, createWebHashHistory } from 'vue-router';

import { registerLoadingDirective } from '@vben/common-ui/es/loading';
import { initStores } from '@vben/stores';
import '@vben/styles';
import '@vben/styles/antd';

import { initComponentAdapter } from '#/adapter/component';
import { initSetupVbenForm } from '#/adapter/form';
import Root from '#/app.vue';
import { setupI18n } from '#/locales';

import GatewayApp from './gateway-app.vue';

import '#/styles/linsight.css';

export async function bootstrapGateway() {
  await initComponentAdapter();
  await initSetupVbenForm();
  const app = createApp(Root);
  registerLoadingDirective(app, { loading: 'loading', spinning: 'spinning' });
  await setupI18n(app);
  await initStores(app, { namespace: 'linsight-gateway' });
  const router = createRouter({ history: createWebHashHistory(), routes: [{ path: '/:pathMatch(.*)*', component: GatewayApp }] });
  app.use(router);
  app.mount('#app');
}
