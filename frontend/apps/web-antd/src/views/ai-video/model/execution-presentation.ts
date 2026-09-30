interface ModelExecutionView {
  executionProvider?: string;
  executionTarget?: string;
  format: string;
  manifest?: {
    decoder?: { type?: string };
    execution?: { provider?: string; target?: string };
    targetPlatform?: string;
  };
}

const providerNames: Record<string, string> = {
  'nvidia-tensorrt': 'NVIDIA TensorRT',
  onnxruntime: 'ONNX Runtime CPU',
  'python-cpu': '隔离 CPU 环境',
  rknpu2: 'Rockchip NPU',
};

/** Presentation uses declared metadata only; it never derives a target from a model name. */
export function modelExecutionDescription(model: ModelExecutionView) {
  const legacyRknpu =
    model.format === 'RKNN' ||
    model.manifest?.decoder?.type === 'FACE_PAIR_SFACE_RKNN';
  const provider =
    model.executionProvider ||
    model.manifest?.execution?.provider ||
    (legacyRknpu ? 'rknpu2' : undefined);
  const target =
    model.executionTarget ||
    model.manifest?.execution?.target ||
    model.manifest?.targetPlatform;
  if (provider) {
    return `${providerNames[provider] || provider}${target ? ` / ${target}` : ''}`;
  }
  if (['ARCHIVE', 'ONNX', 'PYTORCH', 'TORCHSCRIPT'].includes(model.format)) {
    return 'CPU 推理';
  }
  return '专用执行环境';
}

export function modelExecutionLabel(model: ModelExecutionView) {
  return `${modelExecutionDescription(model)} · ${model.format}`;
}
