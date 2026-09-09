package com.linsight.module.aivideo.service.rule;

import com.linsight.framework.common.pojo.PageResult;
import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleDryRunRespVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RulePageReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleSaveReqVO;
import com.linsight.module.aivideo.controller.admin.rule.vo.RuleVersionSaveReqVO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleDO;
import com.linsight.module.aivideo.dal.dataobject.rule.RuleVersionDO;
import com.linsight.module.aivideo.dal.mysql.rule.RuleMapper;
import com.linsight.module.aivideo.dal.mysql.rule.RuleVersionMapper;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.rule.ErrorCodeConstants.*;

@Service
public class RuleServiceImpl implements RuleService {
    @Resource private RuleMapper ruleMapper;
    @Resource private RuleVersionMapper ruleVersionMapper;

    @Override
    public Long createRule(RuleSaveReqVO reqVO) {
        if (ruleMapper.selectByCode(reqVO.getCode()) != null) throw exception(RULE_CODE_DUPLICATE);
        RuleDO rule = toRule(reqVO);
        ruleMapper.insert(rule);
        return rule.getId();
    }

    @Override
    public void updateRule(RuleSaveReqVO reqVO) {
        RuleDO existing = requireRule(reqVO.getId());
        if (!Objects.equals(existing.getCode(), reqVO.getCode())) throw exception(RULE_CODE_IMMUTABLE);
        ruleMapper.updateById(toRule(reqVO));
    }

    @Override
    public RuleDO getRule(Long id) {
        return requireRule(id);
    }

    @Override
    public PageResult<RuleDO> getRulePage(RulePageReqVO reqVO) {
        return ruleMapper.selectPage(reqVO, reqVO.getName(), reqVO.getCode(),
                reqVO.getEventType(), reqVO.getStatus());
    }

    @Override
    public List<RuleDO> getPublishedRules() {
        return ruleMapper.selectPublishedList();
    }

    @Override
    public Long saveVersion(RuleVersionSaveReqVO reqVO) {
        RuleDO rule = requireRule(reqVO.getRuleId());
        List<String> errors = RuleAstValidator.validate(reqVO.getAst(), rule.getEventType());
        RuleVersionDO latest = ruleVersionMapper.selectLatestByRule(rule.getId());
        RuleVersionDO version = new RuleVersionDO();
        version.setRuleId(rule.getId());
        version.setVersion(latest == null ? 1 : latest.getVersion() + 1);
        version.setAst(JsonUtils.toJsonString(reqVO.getAst()));
        version.setNaturalSummary(RuleAstValidator.summarize(reqVO.getAst()));
        version.setValidationStatus(errors.isEmpty() ? "VALID" : "DRAFT");
        version.setValidationErrors(errors.isEmpty() ? null : JsonUtils.toJsonString(errors));
        ruleVersionMapper.insert(version);
        return version.getId();
    }

    @Override
    public List<String> validateVersion(Long id) {
        RuleVersionDO version = requireVersion(id);
        RuleDO rule = requireRule(version.getRuleId());
        Map<String, Object> ast = JsonUtils.parseMap(version.getAst());
        List<String> errors = RuleAstValidator.validate(ast, rule.getEventType());
        version.setNaturalSummary(errors.isEmpty() ? RuleAstValidator.summarize(ast) : version.getNaturalSummary());
        version.setValidationStatus(errors.isEmpty() ? "VALID" : "DRAFT");
        version.setValidationErrors(errors.isEmpty() ? null : JsonUtils.toJsonString(errors));
        ruleVersionMapper.updateById(version);
        return errors;
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void publishVersion(Long id) {
        RuleVersionDO version = requireVersion(id);
        RuleDO rule = requireRule(version.getRuleId());
        Map<String, Object> ast = JsonUtils.parseMap(version.getAst());
        List<String> errors = RuleAstValidator.validate(ast, rule.getEventType());
        if (!errors.isEmpty()) throw exception(RULE_AST_INVALID);
        version.setValidationStatus("PUBLISHED");
        version.setValidationErrors(null);
        version.setNaturalSummary(RuleAstValidator.summarize(ast));
        version.setPublishedTime(LocalDateTime.now());
        ruleVersionMapper.updateById(version);
        rule.setCurrentVersionId(version.getId());
        ruleMapper.updateById(rule);
    }

    @Override
    public List<RuleVersionDO> getVersions(Long ruleId) {
        requireRule(ruleId);
        return ruleVersionMapper.selectListByRule(ruleId);
    }

    @Override
    public RuleVersionConfigDTO getPublishedRuleConfig(Long ruleId, Long ruleVersionId) {
        RuleDO rule = requireRule(ruleId);
        Long selectedId = ruleVersionId == null ? rule.getCurrentVersionId() : ruleVersionId;
        RuleVersionDO version = requireVersion(selectedId);
        if (!Objects.equals(version.getRuleId(), ruleId) || !"PUBLISHED".equals(version.getValidationStatus())) {
            throw exception(RULE_VERSION_NOT_PUBLISHED);
        }
        return new RuleVersionConfigDTO(ruleId, version.getId(), version.getVersion(),
                rule.getEventType(), JsonUtils.parseMap(version.getAst()));
    }

    @Resource private com.linsight.module.aivideo.service.node.NodeService nodeService;
    @Resource private com.linsight.module.aivideo.service.camera.CameraService cameraService;
    @Resource private com.linsight.module.aivideo.integration.runtime.RuntimePreviewClient runtimePreviewClient;

    @Override
    public Map<String, Object> runtimeDryRun(RuleDryRunReqVO reqVO) {
        if (reqVO.getNodeId() == null || reqVO.getCameraId() == null) throw exception(RULE_AST_INVALID);
        nodeService.validateNodeAvailable(reqVO.getNodeId());
        if (!cameraService.getCameraNames(List.of(reqVO.getCameraId())).containsKey(reqVO.getCameraId()))
            throw exception(RULE_AST_INVALID);
        RuleVersionDO version = requireVersion(reqVO.getRuleVersionId());
        RuleDO rule = requireRule(version.getRuleId());
        Map<String, Object> ast = JsonUtils.parseMap(version.getAst());
        if (!RuleAstValidator.validate(ast, rule.getEventType()).isEmpty()) throw exception(RULE_AST_INVALID);
        Map<String, Object> payload = Map.of("taskId", 1, "cameraId", reqVO.getCameraId(),
                "ast", ast, "frames", reqVO.getFrames());
        // Leave headroom for the tunnel envelope and reject oversized input before websocket send.
        if (JsonUtils.toJsonString(payload).getBytes(java.nio.charset.StandardCharsets.UTF_8).length > 56 * 1024)
            throw exception(RULE_AST_INVALID);
        try {
            return runtimePreviewClient.dryRunRule(reqVO.getNodeId(),
                    com.linsight.framework.tenant.core.context.TenantContextHolder.getRequiredTenantId(), payload);
        } catch (com.linsight.module.aivideo.integration.runtime.RuntimePreviewClient.RuntimePreviewException failure) {
            throw exception(RULE_RUNTIME_UNAVAILABLE, failure.getDiagnosticId());
        }
    }

    @Override
    public RuleDryRunRespVO dryRun(RuleDryRunReqVO reqVO) {
        RuleVersionDO version = requireVersion(reqVO.getRuleVersionId());
        RuleDO rule = requireRule(version.getRuleId());
        Map<String, Object> ast = JsonUtils.parseMap(version.getAst());
        if (!RuleAstValidator.validate(ast, rule.getEventType()).isEmpty()) throw exception(RULE_AST_INVALID);
        return RuleDryRunEngine.run(ast, reqVO.getFrames());
    }

    private RuleDO requireRule(Long id) {
        RuleDO rule = id == null ? null : ruleMapper.selectById(id);
        if (rule == null) throw exception(RULE_NOT_FOUND);
        return rule;
    }

    private RuleVersionDO requireVersion(Long id) {
        RuleVersionDO version = id == null ? null : ruleVersionMapper.selectById(id);
        if (version == null) throw exception(RULE_VERSION_NOT_FOUND);
        return version;
    }

    private static RuleDO toRule(RuleSaveReqVO reqVO) {
        RuleDO rule = new RuleDO();
        rule.setId(reqVO.getId());
        rule.setName(reqVO.getName());
        rule.setCode(reqVO.getCode());
        rule.setDescription(reqVO.getDescription());
        rule.setEventType(reqVO.getEventType());
        rule.setStatus(reqVO.getStatus());
        return rule;
    }
}
