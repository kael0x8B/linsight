import { $t } from '#/locales';

const stages = new Set([
  'CHECKING_ENV',
  'DOWNLOADING',
  'DOWNLOADING_DEPS',
  'ENV_READY',
  'FAILED',
  'INSTALLING_DEPS',
  'LOADING',
  'QUEUED',
  'READY',
  'RETRYING_DEPS',
  'RUNNING',
  'VERIFYING',
  'VERIFYING_ENV',
]);

export function deploymentStatusText(status?: string) {
  return status && stages.has(status)
    ? $t(`model-deployment.${status}`)
    : (status ?? '未部署');
}

export function isDeploymentPending(status?: string) {
  return (
    !!status && stages.has(status) && !['FAILED', 'READY'].includes(status)
  );
}
