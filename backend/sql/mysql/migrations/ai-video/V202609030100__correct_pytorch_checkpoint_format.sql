-- Correct .pt artifacts that were previously classified as TorchScript by file extension alone.
-- Preconditions: V202609011900 created ai_model_version.artifact_format and artifact_name.
-- Data impact: existing .pt rows change format metadata only; artifact bytes and hashes are unchanged.
-- Lock risk: row updates take short-lived locks on matching model-version records.
-- Forward repair: inspect the artifact container before assigning TORCHSCRIPT to legacy .pt rows.
-- Rollback: UPDATE ai_model_version SET artifact_format = 'TORCHSCRIPT'
--           WHERE artifact_format = 'PYTORCH' AND LOWER(artifact_name) LIKE '%.pt';

SET NAMES utf8mb4;

UPDATE `ai_model_version`
SET `artifact_format` = 'PYTORCH'
WHERE `artifact_format` = 'TORCHSCRIPT'
  AND LOWER(`artifact_name`) LIKE '%.pt';
