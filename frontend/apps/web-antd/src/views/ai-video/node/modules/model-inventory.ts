export interface ModelDeploymentState {
  actualStatus: string;
  modelVersionId: number;
}

const VISIBLE_WITHOUT_LIVE_INVENTORY = new Set([
  'DOWNLOADING',
  'FAILED',
  'LOADING',
  'QUEUED',
  'REMOVING',
  'RUNNING',
  'VERIFYING',
]);

export function visibleModelVersionIds(
  installedIds: number[],
  deployments: ModelDeploymentState[],
  liveInventoryAvailable: boolean,
) {
  const deploymentIds = deployments
    .filter((deployment) =>
      liveInventoryAvailable
        ? VISIBLE_WITHOUT_LIVE_INVENTORY.has(deployment.actualStatus)
        : deployment.actualStatus !== 'REMOVED',
    )
    .map((deployment) => deployment.modelVersionId);
  return [...new Set([...installedIds, ...deploymentIds])];
}
