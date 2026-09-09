import type { AiVideoCameraApi } from '#/api/ai-video/camera';

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
