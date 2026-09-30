import asyncio
import json
import logging
import os
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

import httpx

from ai_runtime.app.gateway.platform_connection import read_platform_connection
from ai_runtime.app.stream.contracts import StreamProbeRequest, StreamProbeResult
from ai_runtime.app.stream.probe import StreamProbeService
from edge_agent.app.client.control_plane import (
    ControlPlaneClient,
    ControlPlaneRejectedError,
    StreamCheckAssignment,
)
from edge_agent.app.client.runtime import RuntimeClient
from edge_agent.app.command.executor import ModelCommandExecutor
from edge_agent.app.command.lifecycle import NodeLifecycleController
from edge_agent.app.core.config import AgentSettings
from edge_agent.app.core.identity import IdentityStore, NodeIdentity
from edge_agent.app.heartbeat.resources import collect_resources
from edge_agent.app.log_delivery.buffer import BufferedLogHandler, log_record
from edge_agent.app.preview_tunnel import preview_tunnel_loop
from edge_agent.app.upgrade.manager import UpgradeManager

LOGGER = logging.getLogger("linsight.edge_agent")


async def run(settings: AgentSettings, log_buffer: BufferedLogHandler) -> None:
    store = IdentityStore(settings.credential_file)
    identity = store.load()
    client = ControlPlaneClient(settings.control_plane_url, settings.request_timeout_seconds)
    runtime_client = RuntimeClient(
        settings.runtime_url, settings.runtime_api_key, settings.request_timeout_seconds
    )
    try:
        if identity is None:
            if settings.bootstrap_token is None:
                raise RuntimeError("Bootstrap token is required for first registration")
            identity = await client.register(
                settings.bootstrap_token,
                settings.node_code,
                settings.node_name,
                settings.agent_version,
                settings.host_name,
            )
            store.save(identity)
            LOGGER.info(
                "Edge Agent registered nodeId=%s tenantId=%s", identity.node_id, identity.tenant_id
            )
        async with asyncio.TaskGroup() as tasks:
            tasks.create_task(heartbeat_loop(settings, identity, store, client, runtime_client))
            tasks.create_task(stream_check_loop(settings, identity, client))
            tasks.create_task(command_loop(settings, identity, client, runtime_client))
            tasks.create_task(task_report_loop(settings, identity, client, runtime_client))
            tasks.create_task(overlay_delivery_loop(settings, identity, client, runtime_client))
            tasks.create_task(event_delivery_loop(settings, identity, client, runtime_client))
            from edge_agent.app.command.entry_evidence import entry_evidence_loop

            tasks.create_task(entry_evidence_loop(settings, identity, client))
            from edge_agent.app.command.entry_station import entry_station_loop

            tasks.create_task(entry_station_loop(identity, client, runtime_client))
            tasks.create_task(log_delivery_loop(settings, identity, client, log_buffer))
            tasks.create_task(preview_tunnel_loop(settings, identity, runtime_client))
    finally:
        await client.close()
        await runtime_client.close()


async def run_with_platform_reload(
    settings: AgentSettings,
    log_buffer: BufferedLogHandler,
    poll_interval_seconds: float = 1.0,
) -> None:
    """Restart Agent loops when the authenticated local console changes the platform URL."""
    deployed_url = settings.control_plane_url
    try:
        current_url = read_platform_connection(settings.runtime_data_root, deployed_url)[
            "platformUrl"
        ]
    except (KeyError, OSError, ValueError, json.JSONDecodeError):
        LOGGER.exception("Ignoring invalid local platform connection override")
        current_url = deployed_url

    while True:
        active_settings = settings.model_copy(update={"control_plane_url": current_url})
        worker = asyncio.create_task(run(active_settings, log_buffer), name="edge-agent-loops")
        try:
            while True:
                done, _pending = await asyncio.wait({worker}, timeout=poll_interval_seconds)
                if done:
                    await worker
                    return
                try:
                    next_url = read_platform_connection(settings.runtime_data_root, deployed_url)[
                        "platformUrl"
                    ]
                except (KeyError, OSError, ValueError, json.JSONDecodeError):
                    LOGGER.exception("Ignoring invalid local platform connection override")
                    continue
                if next_url == current_url:
                    continue
                LOGGER.warning(
                    "Platform connection changed; restarting Agent loops old=%s new=%s",
                    current_url,
                    next_url,
                )
                current_url = next_url
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker
                break
        finally:
            if not worker.done():
                worker.cancel()
                with suppress(asyncio.CancelledError):
                    await worker


async def heartbeat_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    store: IdentityStore,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
) -> None:
    retry_seconds = 1.0
    while True:
        sequence = identity.heartbeat_sequence + 1
        runtime_health = await collect_runtime_health(runtime_client)
        payload = build_heartbeat_payload(sequence, settings, runtime_health)
        try:
            result = await client.heartbeat(identity, payload)
            identity = identity.model_copy(update={"heartbeat_sequence": sequence})
            store.save(identity)
            if runtime_health.get("runtimeStatus") == "UP":
                from edge_agent.app.upgrade.activation import acknowledge

                acknowledge(settings.upgrade_root, settings.agent_version)
            LOGGER.debug(
                "Heartbeat accepted nodeId=%s sequence=%s clockOffsetMillis=%s",
                identity.node_id,
                sequence,
                result.get("clockOffsetMillis"),
            )
            retry_seconds = 1.0
            await asyncio.sleep(settings.heartbeat_interval_seconds)
        except (httpx.HTTPError, RuntimeError, OSError) as error:
            LOGGER.warning(
                "Heartbeat failed nodeId=%s errorType=%s", identity.node_id, type(error).__name__
            )
            await asyncio.sleep(retry_seconds)
            retry_seconds = min(retry_seconds * 2, 30.0)


async def stream_check_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
) -> None:
    probe_service = StreamProbeService(ffprobe_binary=settings.ffprobe_binary)
    while True:
        try:
            assignment = await client.pull_stream_check(identity)
            if assignment is None:
                await asyncio.sleep(settings.check_poll_interval_seconds)
                continue
            result = await probe_service.probe(build_stream_probe_request(settings, assignment))
            await client.report_stream_check(
                identity,
                build_stream_check_report(assignment.check_id, result),
            )
            LOGGER.info(
                "Stream check reported nodeId=%s cameraId=%s checkId=%s online=%s diagnosticId=%s",
                identity.node_id,
                assignment.camera_id,
                assignment.check_id,
                result.online,
                result.diagnostic_id,
            )
        except (httpx.HTTPError, RuntimeError, OSError, ValueError) as error:
            LOGGER.warning(
                "Stream check loop failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.check_poll_interval_seconds)


def build_stream_probe_request(
    settings: AgentSettings, assignment: StreamCheckAssignment
) -> StreamProbeRequest:
    return StreamProbeRequest(
        camera_id=assignment.camera_id,
        protocol=assignment.protocol,
        host=assignment.host,
        port=assignment.port,
        stream_uri=assignment.stream_uri,
        username=assignment.username,
        password=assignment.password,
        timeout_seconds=settings.stream_probe_timeout_seconds,
    )


async def command_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
) -> None:
    upgrade_manager = None
    if settings.upgrade_signing_key is not None:
        upgrade_manager = UpgradeManager(
            settings.upgrade_root,
            settings.upgrade_signing_key.get_secret_value().encode(),
        )
    executor = ModelCommandExecutor(
        client,
        runtime_client,
        identity,
        settings.runtime_data_root,
        upgrade_manager,
        NodeLifecycleController(
            settings.lifecycle_request_path, settings.runtime_data_root / "lifecycle-journal"
        ),
    )
    while True:
        try:
            # Runtime owns model residency; only check reachability and the
            # local registry here, without warming all historical versions.
            await runtime_client.observability_snapshot()
            restored = await executor.rehydrate_models()
            LOGGER.info(
                "Runtime model registry ready nodeId=%s registered=%s loading=on-demand",
                identity.node_id,
                restored,
            )
            break
        except (httpx.HTTPError, RuntimeError, OSError, ValueError) as error:
            LOGGER.warning(
                "Runtime model rehydration deferred nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.command_poll_interval_seconds)
    while True:
        try:
            command = await client.pull_command(identity)
            if command is None:
                await asyncio.sleep(settings.command_poll_interval_seconds)
                continue
            await executor.execute(command)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError) as error:
            LOGGER.warning(
                "Command loop failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.command_poll_interval_seconds)


async def sync_task_removals(identity, client, runtime_client) -> None:
    try:
        response = await runtime_client.gateway_rpc({"action": "task-removal.list"})
        if not response.get("ok"):
            return  # Older runtimes do not implement the removal journal.
        for removal in response["data"]:
            try:
                await client.report_task_removal(identity, removal)
                await runtime_client.gateway_rpc({"action": "task-removal.ack", "payload": removal})
            except (httpx.HTTPError, RuntimeError, OSError, ValueError):
                LOGGER.warning("Task removal report deferred taskId=%s", removal.get("taskId"))
    except (httpx.HTTPError, RuntimeError, OSError, ValueError):
        LOGGER.warning("Task removal synchronization deferred nodeId=%s", identity.node_id)


async def task_report_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
) -> None:
    previous_states: dict[int, tuple] = {}
    while True:
        try:
            await sync_task_removals(identity, client, runtime_client)
            current_states: dict[int, tuple] = {}
            for status in await runtime_client.task_statuses():
                if status.get("metrics", {}).get("gatewayPlatformManaged") is False:
                    continue
                try:
                    await client.report_task_runtime(identity, status)
                except (httpx.HTTPError, RuntimeError, OSError, ValueError):
                    LOGGER.warning("Task report deferred taskId=%s", status.get("taskId"))
                    continue
                task_id = status.get("taskId")
                state = (status.get("status"), status.get("runId"), status.get("errorCode"))
                current_states[task_id] = state
                if previous_states.get(task_id) == state:
                    continue
                log_record(
                    LOGGER,
                    logging.ERROR if status.get("status") == "FAILED" else logging.INFO,
                    f"Task runtime status reported status={status.get('status')}",
                    component="TASK",
                    task_id=status.get("taskId"),
                    run_id=status.get("runId"),
                    diagnostic_id=status.get("diagnosticId"),
                    error_type=status.get("errorCode"),
                )
            previous_states = current_states
            await asyncio.sleep(settings.task_report_interval_seconds)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError) as error:
            LOGGER.warning(
                "Task report loop failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.task_report_interval_seconds)


async def event_delivery_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
) -> None:
    while True:
        try:
            batch = await runtime_client.pending_events()
            for event in batch.get("events", []):
                try:
                    await _deliver_event(settings, identity, client, runtime_client, event)
                except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                    LOGGER.warning(
                        "Event item delivery deferred nodeId=%s sourceEventId=%s attempts=%s",
                        identity.node_id,
                        event.get("sourceEventId"),
                        event.get("deliveryAttempts", 0),
                    )
                    try:
                        await runtime_client.defer_event(event["sourceEventId"])
                    except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                        LOGGER.warning(
                            "Event defer marker failed nodeId=%s sourceEventId=%s",
                            identity.node_id,
                            event.get("sourceEventId"),
                        )
            for transition in batch.get("transitions", []):
                try:
                    await client.report_event_transition(identity, transition["payload"])
                    await runtime_client.acknowledge_transition(transition["deliveryKey"])
                except ControlPlaneRejectedError as error:
                    if error.code == 1_020_005_000:
                        try:
                            await runtime_client.dead_letter_transition(
                                transition["deliveryKey"], "CONTROL_PLANE_EVENT_NOT_FOUND"
                            )
                            LOGGER.error(
                                "Transition quarantined nodeId=%s deliveryKey=%s reason=%s",
                                identity.node_id,
                                transition.get("deliveryKey"),
                                "CONTROL_PLANE_EVENT_NOT_FOUND",
                            )
                            continue
                        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                            # The Runtime refuses quarantine while the source event is still
                            # pending. In that case retain the transition and retry normally.
                            pass
                    LOGGER.warning(
                        "Transition item delivery deferred nodeId=%s deliveryKey=%s attempts=%s",
                        identity.node_id,
                        transition.get("deliveryKey"),
                        transition.get("deliveryAttempts", 0),
                    )
                    try:
                        await runtime_client.defer_transition(transition["deliveryKey"])
                    except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                        LOGGER.warning(
                            "Transition defer marker failed nodeId=%s deliveryKey=%s",
                            identity.node_id,
                            transition.get("deliveryKey"),
                        )
                except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                    LOGGER.warning(
                        "Transition item delivery deferred nodeId=%s deliveryKey=%s attempts=%s",
                        identity.node_id,
                        transition.get("deliveryKey"),
                        transition.get("deliveryAttempts", 0),
                    )
                    try:
                        await runtime_client.defer_transition(transition["deliveryKey"])
                    except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError):
                        LOGGER.warning(
                            "Transition defer marker failed nodeId=%s deliveryKey=%s",
                            identity.node_id,
                            transition.get("deliveryKey"),
                        )
            await asyncio.sleep(settings.event_poll_interval_seconds)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError) as error:
            LOGGER.warning(
                "Event delivery failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.event_poll_interval_seconds)


async def overlay_delivery_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
) -> None:
    """Forward latest frames only; overlays are intentionally not durable evidence."""
    uploads = asyncio.Semaphore(4)

    async def forward(frame: dict[str, Any]) -> None:
        async with uploads:
            try:
                await client.report_overlay(identity, frame)
            except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError) as error:
                LOGGER.warning(
                    "Overlay delivery failed nodeId=%s taskId=%s errorType=%s",
                    identity.node_id,
                    frame.get("taskId"),
                    type(error).__name__,
                )

    while True:
        started = time.monotonic()
        try:
            # Independent tasks must not serialize their network latency. Finish
            # this bounded batch before fetching another to preserve per-task order.
            frames = await runtime_client.pending_overlays()
            await asyncio.gather(*(forward(frame) for frame in frames))
            # The interval is a cadence, not an extra delay after an HTTP upload.
            # A 200 ms upload plus 100 ms sleep otherwise drops fast NPU results.
            await asyncio.sleep(
                max(0, settings.overlay_poll_interval_seconds - (time.monotonic() - started))
            )
        except (httpx.HTTPError, RuntimeError, OSError, ValueError, KeyError) as error:
            LOGGER.warning(
                "Overlay delivery failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
            await asyncio.sleep(settings.overlay_poll_interval_seconds)


async def log_delivery_loop(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    log_buffer: BufferedLogHandler,
) -> None:
    while True:
        entries = log_buffer.peek(100)
        if not entries:
            await asyncio.sleep(settings.log_report_interval_seconds)
            continue
        try:
            await client.report_logs(identity, entries)
            log_buffer.acknowledge(entries)
        except (httpx.HTTPError, RuntimeError, OSError, ValueError) as error:
            LOGGER.warning(
                "Log delivery failed nodeId=%s errorType=%s",
                identity.node_id,
                type(error).__name__,
            )
        await asyncio.sleep(settings.log_report_interval_seconds)


async def _deliver_event(
    settings: AgentSettings,
    identity: NodeIdentity,
    client: ControlPlaneClient,
    runtime_client: RuntimeClient,
    event: dict,
) -> None:
    event_id = await client.ingest_event(identity, event["payload"])
    snapshot = _runtime_media_path(settings.runtime_data_root, event["snapshotPath"])
    if not snapshot.is_file() or not snapshot.stat().st_size:
        raise ValueError("event snapshot is missing or empty")
    await client.upload_event_media(identity, event_id, "SNAPSHOT", snapshot, "image/jpeg")
    video_value = event.get("videoPath")
    if video_value:
        video = _runtime_media_path(settings.runtime_data_root, video_value)
        if not video.is_file() or not video.stat().st_size:
            raise ValueError("event video is missing or empty")
        await client.upload_event_media(identity, event_id, "VIDEO", video, "video/mp4")
    if event.get("finalized"):
        await runtime_client.acknowledge_event(event["sourceEventId"])


def _runtime_media_path(root: Path, value: str) -> Path:
    """Resolve Runtime evidence while rejecting traversal and symlink escapes."""
    resolved_root = root.resolve()
    resolved_path = Path(value).resolve(strict=True)
    resolved_path.relative_to(resolved_root)
    return resolved_path


async def collect_runtime_health(runtime_client: RuntimeClient) -> dict[str, object]:
    try:
        snapshot = await asyncio.wait_for(runtime_client.observability_snapshot(), timeout=2.0)
        return {
            "runtimeStatus": "UP",
            "runtimeDiagnosticId": None,
            "modelEnvironment": snapshot.get("modelEnvironment"),
        }
    except (TimeoutError, httpx.HTTPError, RuntimeError, OSError, ValueError):
        return {"runtimeStatus": "DOWN", "runtimeDiagnosticId": None}


def build_heartbeat_payload(
    sequence: int,
    settings: AgentSettings,
    runtime_health: dict[str, object] | None = None,
) -> dict[str, object]:
    from edge_agent.app.upgrade.activation import failed_version

    return {
        "sequence": sequence,
        # 控制面沿用项目基座的 LocalDateTime 毫秒时间戳协议。
        "agentTime": time.time_ns() // 1_000_000,
        "agentVersion": settings.agent_version,
        "modelUninstall": "v1",
        "algorithmPackageSdk": "1.0",
        "activationGuard": os.environ.get("LINSIGHT_AGENT_ACTIVATION_GUARD"),
        "agentRollbackAvailable": (settings.upgrade_root / "previous").is_symlink(),
        "failedAgentVersion": failed_version(settings.upgrade_root),
        "hostName": settings.host_name,
        **collect_resources(settings.disk_cleanup_status_file),
        **(runtime_health or {}),
    }


def build_stream_check_report(check_id: int, result: StreamProbeResult) -> dict[str, object]:
    return {
        "checkId": check_id,
        "online": result.online,
        "diagnosticId": result.diagnostic_id,
        "stages": [
            {
                "name": stage.name.value,
                "status": stage.status.value,
                "durationMs": stage.duration_ms,
                "message": stage.message,
            }
            for stage in result.stages
        ],
        "stream": None
        if result.stream is None
        else {
            "codec": result.stream.codec,
            "width": result.stream.width,
            "height": result.stream.height,
            "averageFrameRate": result.stream.average_frame_rate,
        },
        "errorCode": result.error_code,
        "errorMessage": result.error_message,
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    settings = AgentSettings()  # type: ignore[call-arg]
    log_buffer = BufferedLogHandler(
        settings.log_buffer_capacity, settings.log_repeat_window_seconds
    )
    logging.getLogger().addHandler(log_buffer)
    asyncio.run(run_with_platform_reload(settings, log_buffer))


if __name__ == "__main__":
    main()
