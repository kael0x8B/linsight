import type {
  AlgorithmManifest,
  PackageResolution,
} from '#/api/ai-video/algorithm/package';

/** Keep existing tasks pinned; new configurations use the server's target-specific choice. */
export function packageBindings(
  resolution: PackageResolution,
  existing?: Record<string, number>,
): Record<string, number> {
  if (!existing) return { ...resolution.bindings };
  return Object.fromEntries(
    resolution.manifest.models.flatMap(({ slot }) => {
      const id = existing[slot];
      return id &&
        resolution.roles[slot]?.some(
          (option) => option.id === id && option.deployable !== false,
        )
        ? [[slot, id]]
        : [];
    }),
  );
}

export function packageDeploymentSummary(
  manifest: AlgorithmManifest,
  resolution: PackageResolution,
  bindings: Record<string, number>,
) {
  const missing = manifest.models.filter(
    ({ slot }) =>
      !resolution.roles[slot]?.some(
        (model) => model.id === bindings[slot] && model.deployable !== false,
      ),
  );
  const models = new Map(
    manifest.models.flatMap(({ slot }) => {
      const model = resolution.roles[slot]?.find(
        (option) => option.id === bindings[slot],
      );
      return model ? [[model.id, model] as const] : [];
    }),
  );
  return {
    missing,
    installed: [...models.values()].filter((model) => model.installed).length,
    toInstall: [...models.values()].filter((model) => !model.installed).length,
  };
}
