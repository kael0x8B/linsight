import secrets
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import FileResponse, PlainTextResponse

from ai_runtime.app.core.config import RuntimeSettings
from ai_runtime.app.event.store import PendingDeliveryBatch
from ai_runtime.app.gateway.api import build_gateway_router
from ai_runtime.app.gateway.service import GatewayConflict
from ai_runtime.app.model.contracts import (
    DeployModelRequest,
    DeployModelResponse,
    DetectionObject,
    ModelTestRequest,
    ModelTestResult,
)
from ai_runtime.app.model.dependencies import DependencyRequest, DependencyStatus
from ai_runtime.app.model.pool import ModelPool
from ai_runtime.app.observability.contracts import RuntimeObservabilitySnapshot
from ai_runtime.app.observability.snapshot import RuntimeObservabilityService
from ai_runtime.app.rule.contracts import RuleDryRunRequest, RuleDryRunResponse
from ai_runtime.app.rule.engine import RuleEngine
from ai_runtime.app.stream.contracts import StreamProbeRequest, StreamProbeResult
from ai_runtime.app.stream.preview import (
    PreviewCreateRequest,
    PreviewManager,
    PreviewSessionResponse,
    PreviewUnavailableError,
)
from ai_runtime.app.stream.probe import StreamProbeService
from ai_runtime.app.stream.webrtc import (
    WebRtcManager,
    WebRtcOfferRequest,
    WebRtcSessionResponse,
    WebRtcUnavailableError,
)
from ai_runtime.app.task.contracts import (
    TaskOverlayFrame,
    TaskSettingsApplyRequest,
    TaskStartRequest,
    TaskStatus,
)
from ai_runtime.app.task.entry_access import EntryAccessRuntime, EntryRequest
from ai_runtime.app.task.entry_station import EntryStationManager, StationAck, StationSyncRequest
from ai_runtime.app.task.face_verification import (
    FaceVerificationRequest,
    FaceVerificationResult,
    FaceVerificationService,
)
from ai_runtime.app.task.manager import TaskManager


def build_router(
    settings: RuntimeSettings,
    probe_service: StreamProbeService,
    preview_manager: PreviewManager,
    webrtc_manager: WebRtcManager,
    model_pool: ModelPool,
    task_manager: TaskManager,
    gateway=None,
) -> APIRouter:
    router = APIRouter(prefix="/v1")
    observability = RuntimeObservabilityService(task_manager, model_pool)
    face_verification = FaceVerificationService(task_manager, model_pool)
    entry_access = EntryAccessRuntime(task_manager, model_pool, settings.runtime_data_root)
    entry_stations = EntryStationManager(task_manager, model_pool)
    if gateway:
        gateway.external_model_in_use = lambda model_id: (
            any(
                row["config"].model_version_id == model_id
                for row in entry_stations.entries.values()
            )
            or bool(entry_access._active)
        )
    router.add_event_handler("shutdown", entry_stations.close)

    def authenticate_runtime(
        runtime_key: Annotated[str | None, Header(alias="X-Runtime-Key")] = None,
        authorization: Annotated[str | None, Header(alias="Authorization")] = None,
    ) -> None:
        bearer = (
            authorization.removeprefix("Bearer ")
            if authorization is not None and authorization.startswith("Bearer ")
            else None
        )
        supplied = runtime_key or bearer or ""
        if not secrets.compare_digest(supplied, settings.api_key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")

    @router.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "UP", "version": "v1"}

    @router.get(
        "/observability/snapshot",
        response_model=RuntimeObservabilitySnapshot,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def observability_snapshot() -> RuntimeObservabilitySnapshot:
        return observability.snapshot()

    @router.get(
        "/observability/prometheus",
        response_class=PlainTextResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def observability_prometheus() -> PlainTextResponse:
        return PlainTextResponse(
            observability.prometheus(),
            media_type="text/plain; version=0.0.4; charset=utf-8",
        )

    @router.post(
        "/stream/probe",
        response_model=StreamProbeResult,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def probe_stream(request: StreamProbeRequest) -> StreamProbeResult:
        return await probe_service.probe(request)

    @router.post(
        "/preview/sessions",
        response_model=PreviewSessionResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def create_preview_session(request: PreviewCreateRequest) -> PreviewSessionResponse:
        try:
            return await preview_manager.create_session(request)
        except PreviewUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"errorCode": error.error_code, "diagnosticId": error.diagnostic_id},
            ) from error

    @router.get(
        "/preview/sessions/{session_id}",
        response_model=PreviewSessionResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def get_preview_session(session_id: str) -> PreviewSessionResponse:
        try:
            return await preview_manager.get_session(session_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            ) from error

    @router.delete(
        "/preview/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def release_preview_session(session_id: str) -> None:
        await preview_manager.release_session(session_id)

    @router.post(
        "/webrtc/sessions/offer",
        response_model=WebRtcSessionResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def create_webrtc_session(request: WebRtcOfferRequest) -> WebRtcSessionResponse:
        try:
            return await webrtc_manager.create_session(request)
        except WebRtcUnavailableError as error:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail={"errorCode": error.error_code, "diagnosticId": error.diagnostic_id},
            ) from error

    @router.get(
        "/webrtc/sessions/{session_id}",
        response_model=WebRtcSessionResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def get_webrtc_session(session_id: str) -> WebRtcSessionResponse:
        try:
            return await webrtc_manager.get_session(session_id)
        except KeyError as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found"
            ) from error

    @router.delete(
        "/webrtc/sessions/{session_id}",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def release_webrtc_session(session_id: str) -> None:
        await webrtc_manager.release_session(session_id)

    @router.post(
        "/models/dependencies/prepare",
        response_model=DependencyStatus,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def prepare_dependencies(request: DependencyRequest) -> DependencyStatus:
        if model_pool.dependencies is None:
            raise HTTPException(status_code=503, detail="Dependency preparation is unavailable")
        return model_pool.dependencies.start(request)

    @router.get(
        "/models/dependencies/{profile}",
        response_model=DependencyStatus,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def dependency_status(profile: str) -> DependencyStatus:
        if model_pool.dependencies is None:
            raise HTTPException(status_code=503, detail="Dependency preparation is unavailable")
        try:
            return model_pool.dependencies.status(profile)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Unknown dependency profile") from error

    @router.post(
        "/models/deploy",
        response_model=DeployModelResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def deploy_model(request: DeployModelRequest) -> DeployModelResponse:
        _require_runtime_path(request.artifact_path, settings.runtime_data_root)
        try:
            if gateway:
                return await gateway.deploy_model(request)
            return await model_pool.deploy(request)
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error

    @router.post(
        "/models/test",
        response_model=ModelTestResult,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def test_model(request: ModelTestRequest) -> ModelTestResult:
        _require_runtime_path(request.image_path, settings.runtime_data_root)
        try:
            return await model_pool.test(request)
        except (KeyError, GatewayConflict) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=type(error).__name__
            ) from error
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error

    @router.post("/tasks/entry-stations/sync", dependencies=[Depends(authenticate_runtime)])
    async def sync_entry_stations(request: StationSyncRequest):
        return await entry_stations.sync(request)

    @router.post("/tasks/entry-stations/ack", dependencies=[Depends(authenticate_runtime)])
    async def acknowledge_entry_station(request: StationAck):
        entry_stations.acknowledge(request)
        return {"accepted": True}

    @router.post("/tasks/entry-access", dependencies=[Depends(authenticate_runtime)])
    async def run_entry(request: EntryRequest) -> dict:
        for reference in request.references:
            _require_runtime_path(reference.path, settings.runtime_data_root)
        try:
            return await entry_access.run(request)
        except (ValueError, OSError, KeyError) as error:
            raise HTTPException(status_code=422, detail=type(error).__name__) from error

    @router.post(
        "/tasks/entry-access/{session_id}/cancel", dependencies=[Depends(authenticate_runtime)]
    )
    async def cancel_entry(session_id: UUID) -> dict:
        entry_access.cancel(session_id)
        return {"accepted": True}

    @router.post(
        "/tasks/face-verification",
        response_model=FaceVerificationResult,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def verify_face(request: FaceVerificationRequest) -> FaceVerificationResult:
        _require_runtime_path(request.reference_path, settings.runtime_data_root)
        try:
            return await face_verification.verify(request)
        except (ValueError, OSError, KeyError) as error:
            raise HTTPException(status_code=422, detail=type(error).__name__) from error

    @router.post(
        "/tasks/start",
        response_model=TaskStatus,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def start_task(
        request: TaskStartRequest,
        expected_revision: int | None = Header(default=None, alias="X-Gateway-Revision"),
    ) -> TaskStatus:
        try:
            if gateway:
                return await gateway.platform_start(request, expected_revision)
            return await task_manager.start_task(request)
        except (KeyError, GatewayConflict) as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=type(error).__name__
            ) from error
        except (OSError, ValueError) as error:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(error)
            ) from error

    @router.post(
        "/tasks/settings/apply",
        response_model=TaskStatus,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def apply_task_settings(request: TaskSettingsApplyRequest) -> TaskStatus:
        try:
            if gateway:
                return await gateway.apply_settings(request)
            return await task_manager.apply_task_settings(request.task_id, request.settings)
        except KeyError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.post(
        "/rules/dry-run",
        response_model=RuleDryRunResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def dry_run_rule(request: RuleDryRunRequest) -> RuleDryRunResponse:
        engine = RuleEngine(request.task_id, request.camera_id, request.ast)
        transitions = [
            transition
            for frame in sorted(request.frames, key=lambda value: value.timestamp_millis)
            for transition in engine.evaluate(
                [DetectionObject.model_validate(value) for value in frame.objects],
                frame.timestamp_millis,
            )
        ]
        return RuleDryRunResponse(
            confirmed=any(value.state == "ALARM" for value in transitions),
            transitions=transitions,
        )

    @router.delete(
        "/tasks/{task_id}",
        response_model=TaskStatus,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def stop_task(
        task_id: int,
        run_id: str = Query(alias="runId"),
        expected_revision: int | None = Header(default=None, alias="X-Gateway-Revision"),
    ) -> TaskStatus:
        try:
            if gateway:
                return await gateway.platform_stop(task_id, run_id, expected_revision)
            return await task_manager.stop_task(task_id, run_id)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get(
        "/tasks/statuses",
        response_model=list[TaskStatus],
        dependencies=[Depends(authenticate_runtime)],
    )
    async def task_statuses() -> list[TaskStatus]:
        return gateway.statuses() if gateway else task_manager.statuses()

    @router.get(
        "/overlays/pending",
        response_model=list[TaskOverlayFrame],
        dependencies=[Depends(authenticate_runtime)],
    )
    async def pending_overlays() -> list[TaskOverlayFrame]:
        return task_manager.drain_overlay_frames()

    @router.get(
        "/events/pending",
        response_model=PendingDeliveryBatch,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def pending_events() -> PendingDeliveryBatch:
        return task_manager.pending_event_deliveries()

    @router.post(
        "/events/{source_event_id}/ack",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def acknowledge_event(source_event_id: str) -> None:
        task_manager.acknowledge_event(source_event_id)

    @router.post(
        "/events/{source_event_id}/defer",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def defer_event(source_event_id: str) -> None:
        task_manager.defer_event(source_event_id)

    @router.post(
        "/event-transitions/ack",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def acknowledge_transition(delivery_key: str = Query(alias="deliveryKey")) -> None:
        task_manager.acknowledge_transition(delivery_key)

    @router.post(
        "/event-transitions/defer",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def defer_transition(delivery_key: str = Query(alias="deliveryKey")) -> None:
        task_manager.defer_transition(delivery_key)

    @router.post(
        "/event-transitions/dead-letter",
        status_code=status.HTTP_204_NO_CONTENT,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def dead_letter_transition(
        delivery_key: str = Query(alias="deliveryKey"),
        reason: str = Query(min_length=1, max_length=100),
    ) -> None:
        try:
            task_manager.dead_letter_transition(delivery_key, reason)
        except ValueError as error:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    @router.get(
        "/preview/sessions/{session_id}/media/{file_name}",
        response_class=FileResponse,
        dependencies=[Depends(authenticate_runtime)],
    )
    async def get_preview_media(session_id: str, file_name: str) -> FileResponse:
        try:
            path, media_type = await preview_manager.get_media(session_id, file_name)
        except (KeyError, FileNotFoundError) as error:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Media not found"
            ) from error
        return FileResponse(path, media_type=media_type, headers={"Cache-Control": "no-store"})

    if gateway:
        from ai_runtime.app.gateway.preview import GatewayPreview

        gateway.preview = GatewayPreview(gateway, webrtc_manager)
        router.include_router(build_gateway_router(gateway, authenticate_runtime))
    return router


def _require_runtime_path(path, root) -> None:
    resolved_root = root.resolve()
    try:
        path.resolve(strict=True).relative_to(resolved_root)
    except (OSError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Path is outside runtime data root or does not exist",
        ) from error
