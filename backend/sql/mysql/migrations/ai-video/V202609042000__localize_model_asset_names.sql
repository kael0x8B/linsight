-- Localize every preset model asset display name without changing stable codes or references.
-- Deleted/superseded rows are included so historical task, test and deployment pages stay consistent.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

UPDATE `ai_model`
SET `name` = CASE `code`
  WHEN 'safety-helmet' THEN '安全帽检测模型'
  WHEN 'sleeping-on-duty' THEN '睡岗检测模型'
  WHEN 'person-detection' THEN '人员检测模型'
  WHEN 'license-plate' THEN '车牌检测模型'
  WHEN 'reflective-vest' THEN '反光衣检测模型'
  WHEN 'flame' THEN '火焰检测模型'
  WHEN 'smoking-detection' THEN '吸烟检测模型'
  WHEN 'phone-call-detection' THEN '打电话检测模型'
  WHEN 'road-waterlogging' THEN '道路积水检测模型'
  WHEN 'face-mask' THEN '口罩检测模型'
  WHEN 'fall-detection' THEN '跌倒检测模型'
  WHEN 'face-detection' THEN '人脸检测模型'
  WHEN 'generic-coco-object-detection' THEN '通用 COCO 目标检测模型'
  WHEN 'unified-ppe-detection' THEN '统一 PPE 检测模型'
  WHEN 'human-pose-estimation' THEN '人体姿态估计模型'
  WHEN 'video-action-recognition' THEN '通用视频行为识别模型'
  WHEN 'vehicle-type-classification' THEN '车型分类模型'
  WHEN 'license-plate-ocr' THEN '车牌 OCR 模型'
  WHEN 'flame-smoke-detection' THEN '火焰烟雾联合检测模型'
  WHEN 'garbage-debris-detection' THEN '垃圾杂物检测模型'
  WHEN 'abandoned-removed-object' THEN '遗留物与移除物检测模型'
  WHEN 'face-recognition-embedding' THEN '人脸特征识别模型'
  WHEN 'face-liveness' THEN '人脸活体检测模型'
  WHEN 'general-ocr' THEN '通用 OCR 模型'
  WHEN 'meter-reading' THEN '仪表读数识别模型'
  WHEN 'open-vocabulary-detection' THEN '开放词汇目标检测模型'
  WHEN 'general-segmentation' THEN '通用图像视频分割模型'
  WHEN 'video-quality-assessment' THEN '视频图像质量评估模型'
  WHEN 'smoking-phone-detection' THEN '吸烟与手机行为联合检测模型'
  ELSE `name`
END,
`updater` = 'system'
WHERE `source_type` = 'PRESET'
  AND `code` IN (
    'safety-helmet', 'sleeping-on-duty', 'person-detection', 'license-plate',
    'reflective-vest', 'flame', 'smoking-detection', 'phone-call-detection',
    'road-waterlogging', 'face-mask', 'fall-detection', 'face-detection',
    'generic-coco-object-detection', 'unified-ppe-detection', 'human-pose-estimation',
    'video-action-recognition', 'vehicle-type-classification', 'license-plate-ocr',
    'flame-smoke-detection', 'garbage-debris-detection', 'abandoned-removed-object',
    'face-recognition-embedding', 'face-liveness', 'general-ocr', 'meter-reading',
    'open-vocabulary-detection', 'general-segmentation', 'video-quality-assessment',
    'smoking-phone-detection'
  );
