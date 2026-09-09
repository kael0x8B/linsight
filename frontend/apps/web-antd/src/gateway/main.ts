import { initPreferences } from '@vben/preferences';
import { unmountGlobalLoading } from '@vben/utils';

async function start() {
  await initPreferences({ namespace: 'linsight-gateway', overrides: { app: { name: 'LInsight 网关管理' }, theme: { mode: 'light' } } });
  const { bootstrapGateway } = await import('./bootstrap');
  await bootstrapGateway();
  unmountGlobalLoading();
}
void start();
