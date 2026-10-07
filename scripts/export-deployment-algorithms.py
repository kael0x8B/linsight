#!/usr/bin/env python3
"""Export the currently enabled algorithm catalog and its published package ZIPs."""
import argparse
import importlib.util
from pathlib import Path

from deployment_algorithm_assets import export_catalog

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("asset_sync", ROOT / "scripts/sync-builtin-model-assets.py")
sync = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sync)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    parser.add_argument("--output", type=Path, default=ROOT / "deploy/algorithm-assets")
    parser.add_argument("--tenant-id", type=int, default=1)
    parser.add_argument("--catalog-version", required=True)
    args = parser.parse_args()
    registry = sync.LocalRegistry(sync.load_env(args.env_file), args.tenant_id)
    registry.preflight()
    export_catalog(registry, args.output, args.catalog_version)


if __name__ == "__main__":
    main()
