package com.linsight.module.aivideo.convert.rule;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleVersionRespVO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleDO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleVersionDO;

import java.util.List;

public final class RuleConvert {
    private RuleConvert() {}

    public static RuleRespVO convert(RuleDO source) {
        RuleRespVO target = new RuleRespVO();
        target.setId(source.getId());
        target.setName(source.getName());
        target.setCode(source.getCode());
        target.setDescription(source.getDescription());
        target.setEventType(source.getEventType());
        target.setCurrentVersionId(source.getCurrentVersionId());
        target.setStatus(source.getStatus());
        target.setCreateTime(source.getCreateTime());
        return target;
    }

    public static PageResult<RuleRespVO> convertPage(PageResult<RuleDO> page) {
        return new PageResult<>(page.getList().stream().map(RuleConvert::convert).toList(), page.getTotal());
    }

    public static RuleVersionRespVO convert(RuleVersionDO source) {
        RuleVersionRespVO target = new RuleVersionRespVO();
        target.setId(source.getId());
        target.setRuleId(source.getRuleId());
        target.setVersion(source.getVersion());
        target.setAst(JsonUtils.parseMap(source.getAst()));
        target.setNaturalSummary(source.getNaturalSummary());
        target.setValidationStatus(source.getValidationStatus());
        target.setValidationErrors(JsonUtils.parseArray(source.getValidationErrors(), String.class));
        target.setPublishedTime(source.getPublishedTime());
        target.setCreateTime(source.getCreateTime());
        return target;
    }

    public static List<RuleVersionRespVO> convertVersions(List<RuleVersionDO> source) {
        return source.stream().map(RuleConvert::convert).toList();
    }
}
