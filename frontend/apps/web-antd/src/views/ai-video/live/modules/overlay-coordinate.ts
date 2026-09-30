import type { AiVideoCameraApi } from '#/api/ai-video/camera';

export type PreviewRegion = (
  | { bbox: AiVideoCameraApi.OverlayBoundingBox; points?: never }
  | { bbox?: never; points: { x: number; y: number }[] }
) & { color: string; title: string };

export function mapNormalizedPolygon(
  points: { x: number; y: number }[],
  sourceWidth: number,
  sourceHeight: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const image = mapNormalizedBox(
    { x: 0, y: 0, width: 1, height: 1 },
    sourceWidth,
    sourceHeight,
    viewportWidth,
    viewportHeight,
  );
  return points.map((point) => ({
    x: image.x + point.x * image.width,
    y: image.y + point.y * image.height,
  }));
}

export function mapNormalizedBox(
  bbox: AiVideoCameraApi.OverlayBoundingBox,
  sourceWidth: number,
  sourceHeight: number,
  viewportWidth: number,
  viewportHeight: number,
) {
  const scale = Math.min(
    viewportWidth / sourceWidth,
    viewportHeight / sourceHeight,
  );
  const videoWidth = sourceWidth * scale;
  const videoHeight = sourceHeight * scale;
  const offsetX = (viewportWidth - videoWidth) / 2;
  const offsetY = (viewportHeight - videoHeight) / 2;
  return {
    height: bbox.height * videoHeight,
    width: bbox.width * videoWidth,
    x: offsetX + bbox.x * videoWidth,
    y: offsetY + bbox.y * videoHeight,
  };
}
