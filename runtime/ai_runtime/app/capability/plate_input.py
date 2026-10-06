"""Versioned plate observations for independently deployed algorithm packages."""

PLATE_EVIDENCE_CAPABILITY = "plate-ocr-evidence-v1"


def package_plate_input(pipeline: dict) -> dict | None:
    descriptor = pipeline.get("algorithmPackage") or {}
    return (descriptor.get("manifest") or {}).get("frameInput")


def plate_capabilities(pipeline: dict) -> dict[str, str]:
    capabilities = {
        node["id"]: node["capabilityKey"]
        for node in pipeline.get("nodes", [])
        if isinstance(node, dict) and "id" in node and "capabilityKey" in node
    }
    if inputs := package_plate_input(pipeline):
        capabilities = {
            inputs["detectorSlot"]: "detector.license-plate",
            inputs["ocrSlot"]: "ocr.license-plate",
        }
    return capabilities
