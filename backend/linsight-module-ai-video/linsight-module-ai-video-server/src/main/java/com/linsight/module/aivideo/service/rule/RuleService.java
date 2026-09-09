package com.linsight.module.aivideo.service.rule;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RulePageReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleSaveReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleVersionSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleDO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleVersionDO;

import java.util.List;

public interface RuleService {
    Long createRule(RuleSaveReqVO reqVO);
    void updateRule(RuleSaveReqVO reqVO);
    RuleDO getRule(Long id);
    PageResult<RuleDO> getRulePage(RulePageReqVO reqVO);
    List<RuleDO> getPublishedRules();
    Long saveVersion(RuleVersionSaveReqVO reqVO);
    List<String> validateVersion(Long id);
    void publishVersion(Long id);
    List<RuleVersionDO> getVersions(Long ruleId);
    RuleVersionConfigDTO getPublishedRuleConfig(Long ruleId, Long ruleVersionId);
    RuleDryRunRespVO dryRun(RuleDryRunReqVO reqVO);

    java.util.Map<String, Object> runtimeDryRun(RuleDryRunReqVO reqVO);
}
