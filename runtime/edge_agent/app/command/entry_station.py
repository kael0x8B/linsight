"""The edge drives visitor arrival sessions independently of any open management page."""
import asyncio
import logging

LOGGER = logging.getLogger("linsight.edge_agent")


async def synchronize_entry_stations(identity, client, runtime):
    stations = await client.get_entry_stations(identity)
    states = await runtime.sync_entry_stations(stations)
    for state in states:
        encounter = state.get("encounterId")
        if state["state"] == "TRIGGERED" and encounter:
            await client.start_entry_automatically(identity, {key:state[key] for key in ("entryId","version","encounterId","observedAtMillis")})
            await runtime.acknowledge_entry_station(state["entryId"],encounter,False)
        if state["state"] == "SCANNING" and encounter:
            result = await client.get_entry_command(identity,encounter,state=True)
            if result.get("cancelled") or result.get("status") in {"SUCCEEDED","FAILED","CANCELLED","EXPIRED"}:
                await runtime.acknowledge_entry_station(state["entryId"],encounter,True)
        await client.report_entry_station(identity,state)


async def entry_station_loop(identity, client, runtime):
    while True:
        try:
            await synchronize_entry_stations(identity,client,runtime)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            # Revoke the presence lease on lost authority; a resumed station first requires an empty zone.
            try:
                await runtime.sync_entry_stations([])
            except Exception:
                pass  # The Runtime also expires the 15-second lease without a successful refresh.
            LOGGER.warning("Entrance station synchronization failed nodeId=%s errorType=%s",identity.node_id,type(error).__name__)
        await asyncio.sleep(.4)
