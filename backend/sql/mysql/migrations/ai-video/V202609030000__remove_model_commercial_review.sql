-- Remove the model commercial-review gate after the product decision to treat license terms as metadata only.
-- Preconditions: V202609011900 created ai_model_version.commercial_approved.
-- Data impact: the review flag is intentionally discarded; model artifacts and all supply-chain metadata remain.
-- Lock risk: MySQL may briefly take a metadata lock on ai_model_version; schedule away from long transactions.
-- Forward repair: add a new nullable policy field in a later migration if a different approval workflow is introduced.
-- Rollback: ALTER TABLE ai_model_version ADD COLUMN commercial_approved bit(1) NOT NULL DEFAULT b'0'
--           COMMENT '商业使用审核是否通过' AFTER license_spdx;

ALTER TABLE `ai_model_version`
  DROP COLUMN `commercial_approved`;
