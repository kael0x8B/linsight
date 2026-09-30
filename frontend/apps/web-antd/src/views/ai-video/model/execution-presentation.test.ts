import { describe, expect, it } from 'vitest';

import {
  modelExecutionDescription,
  modelExecutionLabel,
} from './execution-presentation';

describe('model execution presentation', () => {
  it('shows an explicitly declared future provider and target', () => {
    expect(
      modelExecutionLabel({
        format: 'TENSORRT',
        manifest: {
          execution: { provider: 'nvidia-tensorrt', target: 'sm_87' },
        },
      }),
    ).toBe('NVIDIA TensorRT / sm_87 · TENSORRT');
  });

  it('keeps the legacy RKNN target visible', () => {
    expect(
      modelExecutionDescription({
        format: 'RKNN',
        manifest: { targetPlatform: 'rk3588' },
      }),
    ).toBe('Rockchip NPU / rk3588');
  });

  it('labels portable ONNX models as CPU inference', () => {
    expect(modelExecutionDescription({ format: 'ONNX' })).toBe('CPU 推理');
  });
});
