package com.linsight.module.aivideo.controller.node.task;
import com.linsight.framework.common.pojo.CommonResult;
import com.linsight.module.aivideo.service.task.EntryAccessService;
import jakarta.annotation.Resource;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.*;
import java.util.Map;
import java.util.List;
import jakarta.validation.Valid;
import com.linsight.module.aivideo.controller.node.task.vo.EntryAutoStartReqVO;
import static com.linsight.framework.common.pojo.CommonResult.success;
@RestController @RequestMapping("/ai-video/task/entry-access")
public class EntryAccessCommandController {
    @Resource private EntryAccessService service;
    @GetMapping("/command") public CommonResult<Map<String,Object>> command(@RequestParam String commandId,Authentication auth){
        return success(service.command(commandId,(Long)auth.getPrincipal()));}
    @GetMapping("/state") public CommonResult<Map<String,Object>> state(@RequestParam String commandId,Authentication auth){
        return success(service.commandState(commandId,(Long)auth.getPrincipal()));}
    @GetMapping("/stations") public CommonResult<List<Map<String,Object>>> stations(Authentication auth){
        return success(service.nodeStations((Long)auth.getPrincipal()));}
    @PostMapping("/auto-start") public CommonResult<Long> autoStart(@Valid @RequestBody EntryAutoStartReqVO request,Authentication auth){
        return success(service.autoStart(request.getEntryId(),request.getVersion(),request.getEncounterId(),request.getObservedAtMillis(),(Long)auth.getPrincipal()));}
    @PostMapping("/station-report") public CommonResult<Boolean> report(@RequestParam Long entryId,@RequestParam Integer version,@RequestParam String state,@Valid @RequestBody(required=false) com.linsight.module.aivideo.controller.node.task.vo.EntryStationFrameReqVO frame,Authentication auth){
        service.reportStation((Long)auth.getPrincipal(),entryId,version,state,frame);return success(true);}
}
