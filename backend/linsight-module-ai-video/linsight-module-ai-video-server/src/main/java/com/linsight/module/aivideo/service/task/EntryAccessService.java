package com.linsight.module.aivideo.service.task;

import com.linsight.framework.common.util.json.JsonUtils;
import com.linsight.framework.common.util.object.BeanUtils;
import com.linsight.framework.mybatis.core.query.LambdaQueryWrapperX;
import com.linsight.module.aivideo.controller.admin.task.vo.*;
import com.linsight.module.aivideo.dal.dataobject.task.EntryAccessDO;
import com.linsight.module.aivideo.dal.dataobject.task.EntryScanDO;
import com.linsight.module.aivideo.dal.mysql.task.EntryAccessMapper;
import com.linsight.module.aivideo.dal.mysql.task.EntryScanMapper;
import com.linsight.module.aivideo.service.algorithm.FaceReferenceDTO;
import com.linsight.module.aivideo.service.algorithm.FaceReferenceService;
import com.linsight.module.aivideo.service.camera.CameraService;
import com.linsight.module.aivideo.service.model.ModelExecutionService;
import com.linsight.module.aivideo.service.node.NodeService;
import com.linsight.module.aivideo.service.node.NodeCommandService;
import com.linsight.module.aivideo.service.node.NodeCommandDTO;
import com.linsight.module.aivideo.service.event.EventService;
import com.linsight.module.aivideo.service.event.EntryAccessEventDTO;
import com.linsight.module.infra.api.file.FileApi;
import jakarta.annotation.Resource;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;
import java.time.*;
import java.util.*;
import java.io.IOException;
import static com.linsight.framework.common.exception.util.ServiceExceptionUtil.exception;
import static com.linsight.module.aivideo.enums.task.ErrorCodeConstants.*;

/** Explicit entrance sessions. Authorization is decided centrally against current configuration. */
@Service public class EntryAccessService {
    @Resource private EntryAccessMapper entryMapper;
    @Resource private EntryScanMapper scanMapper;
    @Resource private FaceReferenceService references;
    @Resource private CameraService cameras;
    @Resource private NodeService nodes;
    @Resource private ModelExecutionService models;
    @Resource private NodeCommandService commands;
    @Resource private EventService events;
    @Resource private FileApi files;
    @Resource private TransactionTemplate transactions;
    private final Map<Long,Map<String,Object>> stationHealth = new java.util.concurrent.ConcurrentHashMap<>();

    public List<Map<String,Object>> listEntries() { return listEntries(null); }
    public List<Map<String,Object>> listEntries(Long cameraId) { return listEntries(cameraId, null); }
    public List<Map<String,Object>> listEntries(Long cameraId, Long nodeId) {
        return entryMapper.selectList(new LambdaQueryWrapperX<EntryAccessDO>().eqIfPresent(EntryAccessDO::getCameraId,cameraId).eqIfPresent(EntryAccessDO::getNodeId,nodeId).orderByDesc(EntryAccessDO::getId).last("LIMIT 200"))
                .stream().map(this::entryView).toList();
    }
    private Map<String,Object> entryView(EntryAccessDO e) {
        var result = new LinkedHashMap<String,Object>(JsonUtils.parseMap(e.getParameters()));
        result.put("id",e.getId()); result.put("name",e.getName()); result.put("cameraId",e.getCameraId());
        result.put("nodeId",e.getNodeId()); result.put("libraryId",e.getLibraryId()); result.put("modelVersionId",e.getModelVersionId());
        result.put("enabled",e.getEnabled()); result.put("version",e.getVersion());
        result.putIfAbsent("triggerMode","MANUAL"); return result;
    }
    public Long save(EntryAccessSaveReqVO r) {
        // Editing parameters cannot move an existing entrance to another camera or gateway.
        if (r.getId() != null) {
            var existing = requireEntry(r.getId(), r.getNodeId());
            if (!Objects.equals(existing.getCameraId(), r.getCameraId())) throw exception(TASK_CONFIG_INVALID);
        }
        if (r.getTemporalN()>r.getTemporalM() || r.getRoiX()+r.getRoiWidth()>1 || r.getRoiY()+r.getRoiHeight()>1)
            throw exception(TASK_CONFIG_INVALID);
        cameras.getRuntimeStreamUrl(r.getCameraId(),"SUB");
        models.validateFaceVerificationReady(r.getModelVersionId(),r.getNodeId());
        var available = references.ready(r.getLibraryId(),r.getModelVersionId());
        var ids = available.stream().map(FaceReferenceDTO::getEntryId).collect(java.util.stream.Collectors.toSet());
        if (!ids.containsAll(r.getAllowedEntryIds())) throw exception(TASK_CONFIG_INVALID);
        if ("FACE_ZONE".equals(r.getTriggerMode()) && Boolean.TRUE.equals(r.getEnabled())) {
            if (r.getRoiWidth()*r.getRoiHeight()>.5 || available.isEmpty()) throw exception(TASK_CONFIG_INVALID);
            var other=listEntries().stream().filter(v->!Objects.equals(v.get("id"),r.getId())
                    && Objects.equals(v.get("nodeId"),r.getNodeId()) && Boolean.TRUE.equals(v.get("enabled"))
                    && "FACE_ZONE".equals(v.get("triggerMode"))).toList();
            if(other.size()>=2 || other.stream().anyMatch(v->Objects.equals(v.get("cameraId"),r.getCameraId()))) throw exception(TASK_CONFIG_INVALID);
        }
        var value = BeanUtils.toBean(r,EntryAccessDO.class);
        Map<String,Object> parameters = new LinkedHashMap<>();
        parameters.put("schemaVersion","1.0"); parameters.put("similarityThreshold",r.getSimilarityThreshold());
        parameters.put("triggerMode",r.getTriggerMode());
        parameters.put("ambiguityMargin",r.getAmbiguityMargin()); parameters.put("temporalN",r.getTemporalN());
        parameters.put("temporalM",r.getTemporalM()); parameters.put("allowedEntryIds",r.getAllowedEntryIds());
        parameters.put("roi",Map.of("x",r.getRoiX(),"y",r.getRoiY(),"width",r.getRoiWidth(),"height",r.getRoiHeight()));
        value.setParameters(JsonUtils.toJsonString(parameters));
        if (r.getId()==null) { value.setVersion(1);entryMapper.insert(value); }
        else {
            value.setVersion(r.getVersion()+1);
            if (entryMapper.update(value,new LambdaQueryWrapperX<EntryAccessDO>().eq(EntryAccessDO::getId,r.getId())
                    .eq(EntryAccessDO::getNodeId,r.getNodeId()).eq(EntryAccessDO::getCameraId,r.getCameraId())
                    .eq(EntryAccessDO::getVersion,r.getVersion()))!=1) throw exception(TASK_REPORT_STALE);
        }
        return value.getId();
    }
    @Transactional(rollbackFor=Exception.class)
    public void stop(Long id, Long nodeId) { requireEntry(id, nodeId); stop(id); }
    @Transactional(rollbackFor=Exception.class)
    public void stop(Long id) {
        var e=requireEntry(id); e.setEnabled(false);e.setVersion(e.getVersion()+1);entryMapper.updateById(e);
        for (var s:scanMapper.selectList(new LambdaQueryWrapperX<EntryScanDO>().eq(EntryScanDO::getEntryAccessId,id)
                .in(EntryScanDO::getStatus,List.of("QUEUED","RUNNING")))) {s.setStatus("CANCELLED");scanMapper.updateById(s);}
    }
    @Transactional(rollbackFor=Exception.class)
    public void delete(Long id, Long nodeId) { requireEntry(id, nodeId); delete(id); }
    @Transactional(rollbackFor=Exception.class)
    public void delete(Long id) {
        if (Boolean.TRUE.equals(requireEntry(id).getEnabled())) throw exception(TASK_STATUS_INVALID);
        entryMapper.deleteById(id);
    }
    public Long enroll(FaceEnrollmentReqVO r) throws IOException {
        if (!Boolean.TRUE.equals(r.getConsentConfirmed())) throw exception(TASK_CONFIG_INVALID);
        nodes.validateNodeAvailable(r.getNodeId());models.validateFaceVerificationReady(r.getModelVersionId(),r.getNodeId());
        var commandId=UUID.randomUUID().toString();
        var referenceId=references.register(r.getLibraryId(),r.getModelVersionId(),r.getName(),r.getExternalCode(),
                r.getValidUntil(),r.getFile().getBytes(),commandId);
        return transactions.execute(tx -> {
            var s=new EntryScanDO();s.setReferenceId(referenceId);s.setMode("ENROLL");s.setCameraId(0L);
            s.setNodeId(r.getNodeId());s.setModelVersionId(r.getModelVersionId());s.setCommandId(commandId);
            s.setSnapshot("{\"schemaVersion\":\"1.0\"}");return issue(s);
        });
    }
    public Map<String,Object> extractionStatus(Long id) {
        var s=requireScan(id);
        if(!"ENROLL".equals(s.getMode())) throw exception(TASK_CONFIG_INVALID);
        return get(id);
    }
    public Long extract(FaceExtractionReqVO r) {
        if (!Boolean.TRUE.equals(r.getConsentConfirmed())) throw exception(TASK_CONFIG_INVALID);
        nodes.validateNodeAvailable(r.getNodeId());models.validateFaceVerificationReady(r.getModelVersionId(),r.getNodeId());
        var photo=references.prepareExistingPhoto(r.getEntryId());
        var commandId=UUID.randomUUID().toString();
        return transactions.execute(tx -> {
            var referenceId=references.registerExisting(photo,r.getModelVersionId(),r.getValidUntil(),commandId);
            var s=new EntryScanDO();s.setReferenceId(referenceId);s.setMode("ENROLL");s.setCameraId(0L);
            s.setNodeId(r.getNodeId());s.setModelVersionId(r.getModelVersionId());s.setCommandId(commandId);
            s.setSnapshot("{\"schemaVersion\":\"1.0\"}");return issue(s);
        });
    }
    public Long start(EntryScanCreateReqVO r) {
        if (!Boolean.TRUE.equals(r.getConsentConfirmed())) throw exception(TASK_CONFIG_INVALID);
        var e=requireEntry(r.getEntryAccessId());
        if (!Boolean.TRUE.equals(e.getEnabled())) throw exception(TASK_STATUS_INVALID);
        nodes.validateNodeAvailable(e.getNodeId());models.validateFaceVerificationReady(e.getModelVersionId(),e.getNodeId());
        var roster=references.ready(e.getLibraryId(),e.getModelVersionId());
        if (roster.isEmpty()) throw exception(TASK_CONFIG_INVALID);
        return transactions.execute(tx -> {
            var s=new EntryScanDO();s.setEntryAccessId(e.getId());s.setMode("IDENTIFY");
            s.setCameraId(e.getCameraId());s.setNodeId(e.getNodeId());s.setModelVersionId(e.getModelVersionId());
            s.setCommandId(UUID.randomUUID().toString());
            var snapshot=entryView(e);snapshot.put("referenceIds",roster.stream().map(FaceReferenceDTO::getId).toList());
            s.setSnapshot(JsonUtils.toJsonString(snapshot));return issue(s);
        });
    }

    /** A node may initiate a finite scan only for its enabled designated entrance zone. */
    @Transactional(rollbackFor=Exception.class)
    public Long autoStart(Long entryId,Integer version,String encounterId,Long observedAtMillis,Long nodeId) {
        var e=entryMapper.selectOne(new LambdaQueryWrapperX<EntryAccessDO>().eq(EntryAccessDO::getId,entryId).last("FOR UPDATE"));
        if(e==null || !Objects.equals(e.getNodeId(),nodeId)) throw exception(TASK_CONFIG_INVALID);
        var existing=scanMapper.selectOne(new LambdaQueryWrapperX<EntryScanDO>().eq(EntryScanDO::getCommandId,encounterId));
        if(existing!=null){
            if(!Objects.equals(existing.getEntryAccessId(),e.getId()) || !Objects.equals(existing.getNodeId(),nodeId)) throw exception(TASK_CONFIG_INVALID);
            return existing.getId();
        }
        long age=System.currentTimeMillis()-observedAtMillis;
        var snapshot=entryView(e);
        if(!Boolean.TRUE.equals(e.getEnabled()) || !Objects.equals(e.getVersion(),version)
                || !"FACE_ZONE".equals(snapshot.get("triggerMode")) || age < -2000 || age > 15000) throw exception(TASK_REPORT_STALE);
        var roster=references.ready(e.getLibraryId(),e.getModelVersionId());
        if(roster.isEmpty()) throw exception(TASK_CONFIG_INVALID);
        // An in-flight scan prevents an additional encounter from overlapping this entrance.
        if(scanMapper.selectCount(new LambdaQueryWrapperX<EntryScanDO>().eq(EntryScanDO::getEntryAccessId,e.getId())
                .in(EntryScanDO::getStatus,List.of("QUEUED","RUNNING")).gt(EntryScanDO::getExpiresTime,LocalDateTime.now()))>0) throw exception(TASK_STATUS_INVALID);
        var scan=new EntryScanDO();scan.setEntryAccessId(e.getId());scan.setMode("IDENTIFY");
        scan.setCameraId(e.getCameraId());scan.setNodeId(nodeId);scan.setModelVersionId(e.getModelVersionId());
        scan.setCreator("edge-agent:"+nodeId);scan.setUpdater("edge-agent:"+nodeId);
        scan.setCommandId(encounterId);snapshot.put("referenceIds",roster.stream().map(FaceReferenceDTO::getId).toList());
        snapshot.put("triggerSource","DESIGNATED_FACE_ZONE");scan.setSnapshot(JsonUtils.toJsonString(snapshot));
        return issue(scan);
    }

    public List<Map<String,Object>> nodeStations(Long nodeId) {
        var result=new ArrayList<Map<String,Object>>();
        for(var e:entryMapper.selectList(new LambdaQueryWrapperX<EntryAccessDO>().eq(EntryAccessDO::getNodeId,nodeId).eq(EntryAccessDO::getEnabled,true))){
            var config=entryView(e);
            if(!"FACE_ZONE".equals(config.get("triggerMode"))) continue;
            try {if(references.ready(e.getLibraryId(),e.getModelVersionId()).isEmpty()) {
                stationHealth.put(e.getId(),Map.of("state","NO_REFERENCE","updatedAt",System.currentTimeMillis(),"version",e.getVersion()));continue;
            }}
            catch(com.linsight.framework.common.exception.ServiceException unavailable){
                stationHealth.put(e.getId(),Map.of("state","NO_REFERENCE","updatedAt",System.currentTimeMillis(),"version",e.getVersion()));continue;
            }
            result.add(Map.of("entryId",e.getId(),"version",e.getVersion(),"cameraId",e.getCameraId(),
                    "modelVersionId",e.getModelVersionId(),"sourceUrl",cameras.getRuntimeStreamUrl(e.getCameraId(),"SUB"),
                    "roi",config.get("roi"),"triggerMode","FACE_ZONE"));
        }
        return result;
    }

    public void reportStation(Long nodeId,Long entryId,Integer version,String state) {
        reportStation(nodeId,entryId,version,state,null);
    }
    public void reportStation(Long nodeId,Long entryId,Integer version,String state,
            com.linsight.module.aivideo.controller.node.task.vo.EntryStationFrameReqVO frame) {
        var e=requireEntry(entryId);
        if(!Objects.equals(e.getNodeId(),nodeId) || !Objects.equals(e.getVersion(),version)) throw exception(TASK_REPORT_STALE);
        if(!Set.of("WAIT_CLEAR","READY","POSITIONING","TRIGGERED","SCANNING","NO_FRESH_FRAME","MULTIPLE_FACES","STATION_UNAVAILABLE","OFFLINE").contains(state)) throw exception(TASK_CONFIG_INVALID);
        if(stationHealth.size()>1000) stationHealth.entrySet().removeIf(v->System.currentTimeMillis()-((Number)v.getValue().get("updatedAt")).longValue()>60000);
        var health=new LinkedHashMap<String,Object>();
        health.put("state",state);health.put("updatedAt",System.currentTimeMillis());health.put("version",version);
        if(frame!=null){
            if(!Objects.equals(frame.getCameraId(),e.getCameraId()) || Math.abs(System.currentTimeMillis()-frame.getTimestamp())>15000) throw exception(TASK_REPORT_STALE);
            health.put("frame",JsonUtils.parseMap(JsonUtils.toJsonString(frame)));
        }
        stationHealth.put(entryId,health);
    }

    public Map<String,Object> stationStatus(Long entryId, Long nodeId) { requireEntry(entryId, nodeId); return stationStatus(entryId); }
    public Map<String,Object> stationStatus(Long entryId) {
        var e=requireEntry(entryId);var config=entryView(e);var value=new LinkedHashMap<String,Object>();
        String state=stationState(e);value.put("state",state);
        value.put("nodeId",e.getNodeId());value.put("entryAccessId",e.getId());
        value.put("roi",config.get("roi"));value.put("cameraId",e.getCameraId());value.put("version",e.getVersion());
        var health=stationHealth.get(entryId);
        if(health!=null && !Set.of("DISABLED","OFFLINE","MANUAL","NO_REFERENCE").contains(state)) value.put("frame",health.get("frame"));
        var latest=scanMapper.selectList(new LambdaQueryWrapperX<EntryScanDO>().eq(EntryScanDO::getEntryAccessId,entryId)
                .eq(EntryScanDO::getMode,"IDENTIFY").orderByDesc(EntryScanDO::getId).last("LIMIT 1"));
        value.put("latestScan",latest.isEmpty()?null:get(latest.get(0).getId()));return value;
    }
    private String stationState(EntryAccessDO entry) {
        if (!Boolean.TRUE.equals(entry.getEnabled())) return "DISABLED";
        if (!"FACE_ZONE".equals(entryView(entry).get("triggerMode"))) return "MANUAL";
        var health=stationHealth.get(entry.getId());
        return health!=null && Objects.equals(health.get("version"),entry.getVersion())
                && System.currentTimeMillis()-((Number)health.get("updatedAt")).longValue()<15000
                ? String.valueOf(health.get("state")):"OFFLINE";
    }

    public List<EntryCameraCapabilityDTO> getCameraCapabilities(Collection<Long> cameraIds) {
        if (cameraIds.isEmpty()) return List.of();
        return entryMapper.selectList(new LambdaQueryWrapperX<EntryAccessDO>().in(EntryAccessDO::getCameraId,cameraIds))
                .stream().map(e -> new EntryCameraCapabilityDTO(e.getId(),e.getCameraId(),e.getNodeId(),
                        e.getName(),Boolean.TRUE.equals(e.getEnabled()),stationState(e))).toList();
    }

    /** Resume the saved camera binding through the same model/reference/ROI validation as configuration. */
    public void enable(Long id, Long nodeId) { requireEntry(id, nodeId); enable(id); }
    public void enable(Long id) {
        var entry=requireEntry(id);
        var values=entryView(entry);
        var roi=(Map<?,?>)values.get("roi");
        for (String key:List.of("x","y","width","height"))
            values.put("roi"+Character.toUpperCase(key.charAt(0))+key.substring(1),roi.get(key));
        values.put("enabled",true);values.put("triggerMode","FACE_ZONE");
        save(JsonUtils.parseObject(JsonUtils.toJsonString(values),EntryAccessSaveReqVO.class));
    }

    private Long issue(EntryScanDO s) {
        s.setStatus("QUEUED");s.setExpiresTime(LocalDateTime.now().plusSeconds(120));scanMapper.insert(s);
        commands.createCommand(s.getCommandId(),s.getNodeId(),"ENTRY_FACE",s.getId(),1,"entry-face:"+s.getId());return s.getId();
    }
    public Map<String,Object> get(Long id) {
        var s=requireScan(id);var value=new LinkedHashMap<String,Object>();
        value.put("id",s.getId());value.put("mode",s.getMode());value.put("entryAccessId",s.getEntryAccessId());
        value.put("status",Set.of("QUEUED","RUNNING").contains(s.getStatus())&&s.getExpiresTime().isBefore(LocalDateTime.now())?"EXPIRED":s.getStatus());
        value.put("result",s.getResult()==null?Map.of():JsonUtils.parseMap(s.getResult()));
        value.put("eventId",s.getEventId());value.put("createTime",s.getCreateTime());return value;
    }
    public List<Map<String,Object>> history(Long entryId) {
        if (entryId!=null) requireEntry(entryId);
        return scanMapper.selectList(new LambdaQueryWrapperX<EntryScanDO>().eqIfPresent(EntryScanDO::getEntryAccessId,entryId)
                .orderByDesc(EntryScanDO::getId).last("LIMIT 50")).stream().map(s->get(s.getId())).toList();
    }
    @Transactional(rollbackFor=Exception.class)
    public void cancel(Long id) {
        var s=requireScan(id);if (Set.of("QUEUED","RUNNING","SENT").contains(s.getStatus())) {
            s.setStatus("CANCELLED");scanMapper.updateById(s);
            if ("ENROLL".equals(s.getMode())) references.applyValidation(s.getReferenceId(),s.getCommandId(),false,Map.of("reason","CANCELLED"));
        }
    }
    public Map<String,Object> commandState(String commandId,Long nodeId) {
        var s=nodeScan(commandId,nodeId);
        boolean cancelled="CANCELLED".equals(s.getStatus())||s.getExpiresTime().isBefore(LocalDateTime.now());
        if (s.getEntryAccessId()!=null) {
            var e=entryMapper.selectById(s.getEntryAccessId());
            cancelled|=e==null||!Boolean.TRUE.equals(e.getEnabled())
                    ||((Number)JsonUtils.parseMap(s.getSnapshot()).get("version")).intValue()!=e.getVersion();
            if (!cancelled) {
                var snapshot=JsonUtils.parseMap(s.getSnapshot());
                try {
                var active=references.ready(((Number)snapshot.get("libraryId")).longValue(),s.getModelVersionId())
                        .stream().map(FaceReferenceDTO::getId).collect(java.util.stream.Collectors.toSet());
                cancelled=!active.containsAll(numberIds(snapshot.get("referenceIds")));
                } catch (com.linsight.framework.common.exception.ServiceException unavailable) {
                    // A disabled/deleted library revokes outstanding sessions.
                    cancelled=true;
                }
            }
        }
        var r=new LinkedHashMap<String,Object>();r.put("cancelled",cancelled);r.put("status",s.getExpiresTime().isBefore(LocalDateTime.now())&&Set.of("QUEUED","RUNNING").contains(s.getStatus())?"EXPIRED":s.getStatus());r.put("eventId",s.getEventId());return r;
    }
    public Map<String,Object> command(String commandId,Long nodeId) {
        var s=nodeScan(commandId,nodeId);
        if (Boolean.TRUE.equals(commandState(commandId,nodeId).get("cancelled"))) throw exception(TASK_STATUS_INVALID);
        var snapshot=JsonUtils.parseMap(s.getSnapshot());
        var roster="ENROLL".equals(s.getMode())?List.of(references.get(s.getReferenceId())):
                references.ready(((Number)snapshot.get("libraryId")).longValue(),s.getModelVersionId()).stream()
                .filter(v->numberIds(snapshot.get("referenceIds")).contains(v.getId())).toList();
        if (roster.isEmpty()) throw exception(TASK_CONFIG_INVALID);
        var r=new LinkedHashMap<String,Object>();r.put("schemaVersion","1.0");r.put("mode",s.getMode());
        r.put("sessionId",commandId);r.put("consentConfirmed",true);r.put("cameraId",s.getCameraId());
        r.put("modelVersionId",s.getModelVersionId());r.put("expiresAtMillis",millis(s.getExpiresTime()));
        r.put("similarityThreshold",snapshot.getOrDefault("similarityThreshold",.6));
        r.put("ambiguityMargin",snapshot.getOrDefault("ambiguityMargin",.08));
        r.put("temporalN",snapshot.getOrDefault("temporalN",3));r.put("temporalM",snapshot.getOrDefault("temporalM",5));
        r.put("roi",snapshot.getOrDefault("roi",Map.of("x",0,"y",0,"width",1,"height",1)));
        if (s.getCameraId()>0) r.put("sourceUrl",cameras.getRuntimeStreamUrl(s.getCameraId(),"SUB"));
        r.put("references",roster.stream().map(v->Map.of("entryId",v.getEntryId(),"sha256",v.getSha256(),
                "url",files.presignGetUrl(v.getObjectRef(),180).getCheckedData())).toList());return r;
    }
    @Transactional(rollbackFor=Exception.class)
    public void applyReport(NodeCommandDTO report) {
        if (!"ENTRY_FACE".equals(report.getCommandType())) return;
        var s=scanMapper.selectOne(new LambdaQueryWrapperX<EntryScanDO>().eq(EntryScanDO::getId,report.getAggregateId()).last("FOR UPDATE"));
        if(s==null||!s.getNodeId().equals(report.getNodeId())||!s.getCommandId().equals(report.getCommandId())) throw exception(TASK_REPORT_STALE);
        if (Set.of("SUCCEEDED","FAILED","CANCELLED").contains(s.getStatus())) return;
        if (!"SUCCEEDED".equals(report.getStatus())) {
            if ("FAILED".equals(report.getStatus())&&"ENROLL".equals(s.getMode())) references.applyValidation(s.getReferenceId(),s.getCommandId(),false,Map.of("reason","EXECUTION_FAILED"));
            s.setStatus(report.getStatus());scanMapper.updateById(s);return;
        }
        Map<String,Object> result=new LinkedHashMap<>();
        var raw=report.getResult()==null?Map.<String,Object>of():report.getResult();
        for(var key:Set.of("status","reason","entryId","similarity","sampledFrames","matchedFrames","backend","device","liveness",
                "bbox","sourceWidth","sourceHeight","firstSeenMillis","lastSeenMillis","durationMs")) if(raw.containsKey(key))result.put(key,raw.get(key));
        if ("ENROLL".equals(s.getMode())) references.applyValidation(s.getReferenceId(),s.getCommandId(),"REFERENCE_READY".equals(result.get("status")),result);
        else if (Boolean.TRUE.equals(commandState(s.getCommandId(),s.getNodeId()).get("cancelled"))) result.put("decision","CANCELLED");
        else {
            var snap=JsonUtils.parseMap(s.getSnapshot());
            int required=((Number)snap.get("temporalN")).intValue();
            int matched=raw.get("matchedFrames") instanceof Number n?n.intValue():0;
            int sampled=raw.get("sampledFrames") instanceof Number n?n.intValue():0;
            String decision="QUALITY_RETRY";
            if (matched>=required&&sampled>=((Number)snap.get("temporalM")).intValue()) {
                if ("MATCH".equals(result.get("status"))&&result.get("entryId") instanceof Number id) {
                    var valid=references.ready(((Number)snap.get("libraryId")).longValue(),s.getModelVersionId()).stream()
                            .filter(v->id.longValue()==v.getEntryId()&&numberIds(snap.get("referenceIds")).contains(v.getId())).findFirst();
                    if(valid.isPresent()) {
                        result.put("personName",valid.get().getName());result.put("externalCode",valid.get().getExternalCode());
                        decision=numberIds(snap.get("allowedEntryIds")).contains(id.longValue())?"AUTHORIZED":"PERMISSION_DENIED";
                    } else decision="REFERENCE_REVOKED";
                } else if ("IDENTITY_UNCONFIRMED".equals(result.get("status"))) decision="IDENTITY_UNCONFIRMED";
            }
            result.put("decision",decision);
            if(Set.of("PERMISSION_DENIED","IDENTITY_UNCONFIRMED").contains(decision)) {
                var event=new EntryAccessEventDTO();event.setSessionId(s.getCommandId());event.setEntryId(s.getEntryAccessId());
                event.setCameraId(s.getCameraId());event.setNodeId(s.getNodeId());event.setModelVersionId(s.getModelVersionId());
                event.setResult(result);event.setConfiguration(snap);s.setEventId(events.createEntryAccessEvent(event));
            }
        }
        s.setResult(JsonUtils.toJsonString(result));s.setStatus("SUCCEEDED");scanMapper.updateById(s);
    }
    private EntryScanDO nodeScan(String id,Long nodeId) {
        var command=commands.getCommandForNode(id,nodeId);
        if(!"ENTRY_FACE".equals(command.getCommandType()))throw exception(TASK_NOT_FOUND);
        var s=requireScan(command.getAggregateId());
        if(!s.getNodeId().equals(nodeId)||!s.getCommandId().equals(id))throw exception(TASK_REPORT_STALE);return s;
    }
    private EntryScanDO requireScan(Long id) {var s=scanMapper.selectById(id);if(s==null)throw exception(TASK_NOT_FOUND);return s;}
    private EntryAccessDO requireEntry(Long id, Long nodeId) {
        var entry = requireEntry(id);
        if (nodeId != null && !Objects.equals(entry.getNodeId(), nodeId)) throw exception(TASK_CONFIG_INVALID);
        return entry;
    }
    private EntryAccessDO requireEntry(Long id) {var e=entryMapper.selectById(id);if(e==null)throw exception(TASK_NOT_FOUND);return e;}
    private static Set<Long> numberIds(Object v) {
        if(!(v instanceof List<?> values))return Set.of();return values.stream().filter(Number.class::isInstance).map(n->((Number)n).longValue()).collect(java.util.stream.Collectors.toSet());
    }
    private static long millis(LocalDateTime v) {return v.atZone(ZoneId.systemDefault()).toInstant().toEpochMilli();}
}
