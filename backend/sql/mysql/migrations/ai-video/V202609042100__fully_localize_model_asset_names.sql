-- Replace technical acronyms in display names so every preset model name is fully Chinese.

SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

UPDATE `ai_model`
SET `name` = CASE `code`
  WHEN 'generic-coco-object-detection' THEN '通用目标检测模型'
  WHEN 'unified-ppe-detection' THEN '统一个人防护装备检测模型'
  WHEN 'license-plate-ocr' THEN '车牌文字识别模型'
  WHEN 'general-ocr' THEN '通用文字识别模型'
  ELSE `name`
END,
`updater` = 'system'
WHERE `source_type` = 'PRESET'
  AND `code` IN (
    'generic-coco-object-detection',
    'unified-ppe-detection',
    'license-plate-ocr',
    'general-ocr'
  );
