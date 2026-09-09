import asyncio
from types import SimpleNamespace
import numpy as np
import pytest
from pydantic import ValidationError
from ai_runtime.app.rule.face_zone import FaceZoneTrigger
from ai_runtime.app.task.entry_station import EntryStationConfig, StationSyncRequest, EntryStationManager, is_positioned
from edge_agent.app.command.entry_station import synchronize_entry_stations


def test_requires_empty_zone_then_voluntary_position_and_leave_before_next_scan():
    g=FaceZoneTrigger()
    for t in range(0,5000,400):g.observe(t,True,True)
    assert g.state=='WAIT_CLEAR' and g.encounter_id is None
    g.observe(5000,False,False);g.observe(6000,False,False)
    assert g.state=='READY'
    g.observe(6500,True,True);g.observe(7600,True,True)
    encounter=g.encounter_id;assert encounter and g.state=='TRIGGERED'
    for t in range(8000,18000,400):g.observe(t,True,True)
    assert g.encounter_id==encounter
    g.acknowledge(encounter,False);assert g.state=='SCANNING'
    g.acknowledge(encounter,True)
    for t in range(18000,23000,400):g.observe(t,True,True)
    assert g.state=='WAIT_CLEAR' and g.encounter_id is None
    g.observe(24000,False,False);g.observe(25000,False,False)
    g.observe(26000,True,True);g.observe(27000,True,True)
    assert g.encounter_id!=encounter and g.encounter_id


def test_transient_or_multiple_faces_do_not_confirm_position():
    g=FaceZoneTrigger();g.observe(0,False,False);g.observe(1000,False,False)
    g.observe(1100,True,True);g.observe(1400,True,False);g.observe(2200,True,True)
    assert g.encounter_id is None
    g.observe(3300,True,False);assert g.state=='READY'


def test_unacknowledged_encounter_expires_without_retrying_stationary_person():
    g=FaceZoneTrigger();g.observe(0,False,False);g.observe(1000,False,False)
    g.observe(2000,True,True);g.observe(3000,True,True);old=g.encounter_id
    g.observe(24000,True,True);g.acknowledge(old,False)
    assert g.state=='WAIT_CLEAR' and g.encounter_id is None


def config(**change):
    value=dict(entryId=1,version=1,cameraId=2,modelVersionId=131,sourceUrl='rtsp://example/entry',roi=dict(x=.15,y=.1,width=.7,height=.7),triggerMode='FACE_ZONE')
    value.update(change);return EntryStationConfig.model_validate(value)


def test_auto_zone_cannot_cover_entire_monitoring_frame_or_duplicate_camera():
    with pytest.raises(ValidationError):config(roi=dict(x=0,y=0,width=1,height=1))
    with pytest.raises(ValidationError):StationSyncRequest(stations=[config(),config(entryId=2)])


def test_position_requires_large_complete_frontal_face():
    face=SimpleNamespace(box=np.array([10,10,140,150]),landmarks=np.array([[40,50],[100,50],[70,80],[50,110],[90,110]]))
    assert is_positioned(face,200,200)
    face.landmarks[2,0]=110;assert not is_positioned(face,200,200)
    face.box=np.array([0,0,20,20]);assert not is_positioned(face,200,200)


def test_configuration_removal_cancels_presence_worker():
    async def run():
        manager=EntryStationManager(None,None)
        # Presence worker failure is bounded; removing config still cancels it promptly.
        await manager.sync(StationSyncRequest(stations=[config()]))
        job=manager.entries[1]['job']
        await manager.sync(StationSyncRequest(stations=[]))
        assert job.done() and manager.snapshot()==[]
        await manager.close()
    asyncio.run(run())


def test_agent_starts_from_edge_encounter_without_browser_and_acks_once():
    class Client:
        async def get_entry_stations(self,identity):return []
        async def start_entry_automatically(self,identity,payload):self.payload=payload;return 9
        async def report_entry_station(self,identity,state):pass
        async def get_entry_command(self,*args,**kwargs):return dict(status='SUCCEEDED')
    class Runtime:
        phase='TRIGGERED'
        async def sync_entry_stations(self,stations):return [dict(entryId=1,version=1,state=self.phase,encounterId='encounter',observedAtMillis=1000)]
        async def acknowledge_entry_station(self,*args):self.ack=args;self.phase='SCANNING'
    async def run():
        c,r=Client(),Runtime();await synchronize_entry_stations(None,c,r)
        assert c.payload['encounterId']=='encounter' and r.ack==(1,'encounter',False)
        await synchronize_entry_stations(None,c,r);assert r.ack==(1,'encounter',True)
    asyncio.run(run())


def test_station_control_plane_envelope_shapes():
    async def run():
        import httpx
        from edge_agent.app.client.control_plane import ControlPlaneClient
        from edge_agent.app.core.identity import NodeIdentity
        from pydantic import SecretStr
        identity = NodeIdentity(node_id=1, tenant_id=1, credential=SecretStr("test-only"))
        def handler(request):
            data = [] if request.url.path.endswith("/stations") else (12 if request.url.path.endswith("/auto-start") else True)
            return httpx.Response(200, json={"code": 0, "data": data})
        client = ControlPlaneClient("http://test", 5)
        await client._client.aclose()
        client._client = httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handler))
        try:
            assert await client.get_entry_stations(identity) == []
            assert await client.start_entry_automatically(identity, {}) == 12
            assert await client.report_entry_station(identity, {"entryId":1,"version":1,"state":"READY"}) is True
        finally:
            await client._client.aclose()
    asyncio.run(run())


def test_preview_coordinates_are_full_frame_and_keep_source_clock_without_identity():
    import io,time
    from contextlib import asynccontextmanager
    from PIL import Image
    image=Image.new('RGB',(640,480));encoded=io.BytesIO();image.save(encoded,format='JPEG')
    captured=SimpleNamespace(data=encoded.getvalue(),timestamp_millis=int(time.time()*1000),source_pts=90000,stream_id='source-1')
    class Tasks:
        @asynccontextmanager
        async def camera_samples(self,*args):
            queue=asyncio.Queue();await queue.put(captured);yield queue
    class Pool:
        async def locate_faces(self,*args):
            return [SimpleNamespace(box=np.array([10,20,110,140]),score=.95,landmarks=np.array([[30,50],[90,50],[60,80],[35,110],[85,110]]))]
    async def run():
        manager=EntryStationManager(Tasks(),Pool())
        try:
            await manager.sync(StationSyncRequest(stations=[config()]))
            for _ in range(50):
                await asyncio.sleep(.002)
                frame=manager.snapshot()[0]['frame']
                if frame:break
            assert frame['sourcePts']==90000 and frame['streamId']=='source-1'
            assert frame['timestamp']==captured.timestamp_millis
            assert frame['faces'][0]['x']==pytest.approx((96+10)/640)
            assert frame['faces'][0]['y']==pytest.approx((48+20)/480)
            assert frame['faces'][0]['trackId']
            assert 'personName' not in str(frame) and 'imageBase64' not in frame
        finally:await manager.close()
    asyncio.run(run())
