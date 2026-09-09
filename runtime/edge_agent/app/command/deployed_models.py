"""Compatibility import for the gateway-owned local model registry."""

from ai_runtime.app.model.deployed import (
    DeployedModel,
    DeployedModelDocument,
    DeployedModelRegistry,
    _sha256,
)

__all__ = ["DeployedModel", "DeployedModelDocument", "DeployedModelRegistry", "_sha256"]
