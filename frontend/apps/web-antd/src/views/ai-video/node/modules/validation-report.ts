import type {
  ValidationImage,
  ValidationRun,
} from '#/api/ai-video/node/validation';

const escape = (value: unknown) =>
  String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');

/** Static, self-contained report; all user/model strings are escaped, with no script execution. */
export function validationReport(
  run: ValidationRun,
  images: Record<string, ValidationImage>,
  t: (key: string) => string,
) {
  const rows = run.items
    .map((item) => {
      const image = images[item.id];
      const safeImage =
        image &&
        /^image\/(jpeg|png|webp)$/.test(image.mime) &&
        /^[\d+/=a-z]+$/i.test(image.imageBase64)
          ? `<image href="data:${image.mime};base64,${image.imageBase64}" width="1000" height="1000" preserveAspectRatio="none"/>`
          : '';
      const visibleObjects = (item.result?.objects ?? []).filter(
        (obj) => obj.attributes?.visibleByDefault !== false,
      );
      const recognizedTexts = visibleObjects
        .map((obj) => obj.attributes?.plateNumber ?? obj.attributes?.plateText)
        .filter(
          (value): value is string =>
            typeof value === 'string' && Boolean(value.trim()),
        );
      const boxes = visibleObjects
        .map((obj) => {
          const { x, y, width, height } = obj.bbox;
          if (
            ![x, y, width, height].every(
              (v) => Number.isFinite(v) && v >= 0 && v <= 1,
            )
          )
            return '';
          const text = obj.attributes?.plateNumber ?? obj.attributes?.plateText;
          const label =
            typeof text === 'string' && text.trim() ? text : obj.class;
          return `<rect x="${x * 1000}" y="${y * 1000}" width="${width * 1000}" height="${height * 1000}" fill="none" stroke="#22c55e" stroke-width="3"/><text x="${x * 1000}" y="${Math.max(20, y * 1000)}" fill="white" stroke="#111" stroke-width=".4" font-size="20">${escape(label)} ${Math.round(obj.confidence * 100)}%</text>`;
        })
        .join('');
      const ratio = item.result
        ? item.result.sourceWidth / item.result.sourceHeight
        : 16 / 9;
      return `<section><h2>${escape(item.name)} · ${escape(t(item.status))}</h2><svg viewBox="0 0 1000 1000" preserveAspectRatio="none" role="img" aria-label="${escape(item.name)}" style="aspect-ratio:${ratio}">${safeImage}${boxes}</svg><p>${escape(t('expected'))}: ${escape(JSON.stringify(item.expected))}</p><p>${escape(t('actual'))}: ${escape(item.actualCount ?? '—')} · ${escape(item.result?.totalMillis ?? '—')} ms</p><p>${escape(t('recognizedText'))}: ${escape(recognizedTexts.join('、') || '—')}</p><p>${escape(t('note'))}: ${escape(item.note)}</p><p>${escape(item.error)} ${escape(item.diagnosticId ?? item.result?.diagnosticId)}</p><pre>${escape(JSON.stringify(item.result?.objects ?? [], null, 2))}</pre></section>`;
    })
    .join('');
  const counts = ['PASS', 'FAIL', 'INCONCLUSIVE', 'ERROR', 'PENDING', 'RUNNING']
    .map(
      (status) =>
        `${escape(t(status))}: ${run.items.filter((item) => item.status === status).length}`,
    )
    .join(' · ');
  return `<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>${escape(run.setName)}</title><style>body{font:14px system-ui;max-width:1100px;margin:32px auto;padding:0 24px;color:#172033}section{border-top:1px solid #ddd;padding:20px 0;break-inside:avoid}svg{display:block;width:min(100%,800px);background:#111}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f9;padding:16px}p{overflow-wrap:anywhere}</style></head><body><h1>${escape(t('report'))} · ${escape(run.setName)}</h1><p>${escape(run.createdAt)} · ${escape(run.id)} · ${escape(t('revision'))} ${run.setRevision}</p><p>${counts}</p><p>${escape(t('scope'))}</p><pre>${escape(JSON.stringify(run.target, null, 2))}</pre>${rows}</body></html>`;
}

export function downloadValidationReport(html: string, id: string) {
  const url = URL.createObjectURL(
    new Blob([html], { type: 'text/html;charset=utf-8' }),
  );
  const link = document.createElement('a');
  link.href = url;
  link.download = `linsight-validation-${id}.html`;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
