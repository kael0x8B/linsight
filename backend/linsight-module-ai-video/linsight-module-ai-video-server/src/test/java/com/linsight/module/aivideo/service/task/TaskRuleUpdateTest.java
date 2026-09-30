package com.linsight.module.aivideo.service.task;

import com.linsight.module.aivideo.controller.admin.task.vo.TaskRuleUpdateReqVO;
import com.linsight.module.aivideo.dal.dataobject.task.TaskDO;
import com.linsight.module.aivideo.dal.mysql.task.TaskMapper;
import com.linsight.module.aivideo.service.algorithm.AlgorithmService;
import com.linsight.module.aivideo.service.algorithm.AlgorithmSummaryDTO;
import com.linsight.module.aivideo.service.algorithm.AlgorithmPackageService;
import com.linsight.module.aivideo.service.rule.RuleService;
import com.linsight.module.aivideo.service.rule.RuleVersionConfigDTO;
import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;
import java.util.List;
import java.util.Map;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class TaskRuleUpdateTest {
    final TaskMapper tasks=mock(TaskMapper.class);
    final RuleService rules=mock(RuleService.class);
    final AlgorithmService algorithms=mock(AlgorithmService.class);
    final AlgorithmPackageService algorithmPackages=mock(AlgorithmPackageService.class);
    final TaskServiceImpl service=new TaskServiceImpl();
    final TaskDO task=new TaskDO();
    final TaskRuleUpdateReqVO request=new TaskRuleUpdateReqVO();
    TaskRuleUpdateTest(){
        ReflectionTestUtils.setField(service,"taskMapper",tasks);
        ReflectionTestUtils.setField(service,"ruleService",rules);
        ReflectionTestUtils.setField(service,"algorithmService",algorithms);
        ReflectionTestUtils.setField(service,"algorithmPackageService",algorithmPackages);
        task.setId(1L);task.setAlgorithmId(2L);task.setActualStatus("STOPPED");task.setDesiredStatus("STOPPED");task.setConfigVersion(3);
        task.setPipelineVersionId(20L);task.setModelVersionId(30L);task.setParameters("{\"sampleFps\":2}");
        request.setId(1L);request.setExpectedConfigVersion(3);request.setRuleId(4L);request.setRuleVersionId(5L);
        when(tasks.selectById(1L)).thenReturn(task);
        when(algorithms.getSummaries(List.of(2L))).thenReturn(List.of(new AlgorithmSummaryDTO(2L,"反光衣","ppe.reflective-vest","REFLECTIVE_VEST")));
        when(algorithmPackages.eventType(20L,"REFLECTIVE_VEST")).thenReturn("REFLECTIVE_VEST");
        when(rules.getPublishedRuleConfig(4L,5L)).thenReturn(new RuleVersionConfigDTO(4L,5L,2,"REFLECTIVE_VEST",Map.of()));
        when(tasks.updateRuleVersion(1L,3,4L,5L)).thenReturn(1);
    }
    @Test void switchesOnlyRuleThroughConditionalWrite(){
        service.updateTaskRule(request);
        verify(tasks).updateRuleVersion(1L,3,4L,5L);
        assertThat(task.getPipelineVersionId()).isEqualTo(20L);
        assertThat(task.getModelVersionId()).isEqualTo(30L);
        assertThat(task.getParameters()).isEqualTo("{\"sampleFps\":2}");
    }
    @Test void runningTaskCannotBeMutated(){task.setActualStatus("RUNNING");assertThatThrownBy(()->service.updateTaskRule(request));verifyNoInteractions(rules);}
    @Test void mismatchingEventIsRejected(){when(rules.getPublishedRuleConfig(4L,5L)).thenReturn(new RuleVersionConfigDTO(4L,5L,1,"SAFETY_HELMET",Map.of()));assertThatThrownBy(()->service.updateTaskRule(request));verify(tasks,never()).updateRuleVersion(1L,3,4L,5L);}
    @Test void concurrentConfigChangeIsRejected(){when(tasks.updateRuleVersion(1L,3,4L,5L)).thenReturn(0);assertThatThrownBy(()->service.updateTaskRule(request));}
    @Test void responseLostRetryDoesNotIncrementAgain(){task.setRuleId(4L);task.setRuleVersionId(5L);task.setConfigVersion(4);service.updateTaskRule(request);verify(tasks,never()).updateRuleVersion(1L,3,4L,5L);}
}
