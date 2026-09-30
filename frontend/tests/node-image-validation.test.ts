import type { ValidationRun } from '../apps/web-antd/src/api/ai-video/node/validation';

import { describe, expect, it, vi } from 'vitest';

import { readValidationImage } from '../apps/web-antd/src/api/ai-video/node/validation';
import { validationReport } from '../apps/web-antd/src/views/ai-video/node/modules/validation-report';

const run = {
  id: 'run-1', createdAt: '2026-09-23T09:00:00Z', setName: '<script>alert(1)</script>', setRevision: 3,
  target: { modelBindings: { detector: 40 }, models: [{ modelVersionId: 40, sha256: 'a'.repeat(64) }], parameters: { confidence: 0.5 } },
  items: [{ id: 'image-1', name: '现场.png', note: '<img src=x onerror=alert(1)>', status: 'FAIL', actualCount: 1,
    expected: { category: 'person', count: 0, confidence: 0.5, text: '' },
    result: { sourceWidth: 640, sourceHeight: 480, totalMillis: 10, diagnosticId: 'diagnostic',
      objects: [{ class: 'person', confidence: 0.9, bbox: { x: 0.1, y: 0.2, width: 0.3, height: 0.4 } }] } }],
} as unknown as ValidationRun;

describe('validation report and media transport', () => {
  it('exports frozen expectations, precise normalized boxes, metadata and escaped user text', () => {
    const html = validationReport(run, { 'image-1': { mime: 'image/png', imageBase64: 'YWJj' } }, (key) => key);
    expect(html).toContain('data:image/png;base64,YWJj');
    expect(html).toContain('x="100" y="200" width="300" height="400"');
    expect(html).toContain('FAIL: 1');
    expect(html).toContain('diagnostic');
    expect(html).toContain('a'.repeat(64));
    expect(html).not.toContain('<script>');
    expect(html).not.toContain('<img src=x');
    expect(html).toContain('&lt;script&gt;');
  });
  it('rejects injected image URLs and invalid coordinates in report markup', () => {
    const copy = structuredClone(run);
    copy.items[0]!.result!.objects[0]!.bbox.x = Number.NaN;
    const html = validationReport(copy, { 'image-1': { mime: 'image/png', imageBase64: '" onload="alert(1)' } }, (key) => key);
    expect(html).not.toContain('<image');
    expect(html).not.toContain('<rect');
  });
  it('reassembles aligned base64 chunks without exceeding a single RPC response', async () => {
    const transport = vi.fn().mockResolvedValueOnce({ offset: 0, length: 3, size: 5, mime: 'image/png', imageBase64: btoa('abc') })
      .mockResolvedValueOnce({ offset: 3, length: 2, size: 5, mime: 'image/png', imageBase64: btoa('de') });
    expect((await readValidationImage(transport, 'set', 'sample')).imageBase64).toBe(btoa('abcde'));
    expect(transport).toHaveBeenLastCalledWith('validation.image', { id: 'set', sampleId: 'sample', offset: 3 });
  });
  it('does not fetch more chunks after closing and rejects mismatched offsets', async () => {
    const transport = vi.fn().mockResolvedValue({ offset: 1, length: 3, size: 3 });
    await expect(readValidationImage(transport, 'set', 'sample')).rejects.toThrow('Invalid image chunk');
    transport.mockClear();
    await expect(readValidationImage(transport, 'set', 'sample', () => false)).rejects.toThrow('Cancelled');
    expect(transport).not.toHaveBeenCalled();
  });
});
