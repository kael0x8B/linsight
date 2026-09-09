import asyncio
from types import SimpleNamespace

import pytest

from edge_agent.app import main


def test_overlay_upload_time_does_not_add_another_poll_interval(monkeypatch):
    async def scenario():
        sleeps = []
        # Local fetch + upload already took longer than the 100 ms cadence.
        times = iter([10.0, 10.23])
        monkeypatch.setattr(main.time, 'monotonic', lambda: next(times))

        async def sleep(delay):
            sleeps.append(delay)
            raise asyncio.CancelledError

        class Runtime:
            async def pending_overlays(self): return [{'frameId': 'run:1'}]

        class Control:
            async def report_overlay(self, identity, frame):
                assert frame['frameId'] == 'run:1'

        monkeypatch.setattr(main.asyncio, 'sleep', sleep)
        with pytest.raises(asyncio.CancelledError):
            await main.overlay_delivery_loop(SimpleNamespace(overlay_poll_interval_seconds=.1),
                SimpleNamespace(node_id=1), Control(), Runtime())
        assert sleeps == [0]
    # Patching main.time also affects asyncio's clock; construct the loop first.
    loop = asyncio.new_event_loop()
    try:
        with monkeypatch.context() as patch:
            # Replace only the module's time binding, not the shared time module.
            patch.setattr(main, 'time', SimpleNamespace(monotonic=lambda: 0))
            loop.run_until_complete(scenario())
    finally:
        loop.close()


def test_multiple_tasks_upload_concurrently_with_bounded_failure_isolation(monkeypatch):
    async def scenario():
        entered = []
        completed = []
        release = asyncio.Event()
        full = asyncio.Event()
        active = 0
        peak = 0

        class Runtime:
            async def pending_overlays(self):
                return [{'taskId': task_id} for task_id in range(6)]

        class Control:
            async def report_overlay(self, identity, frame):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                entered.append(frame['taskId'])
                if active == 4:
                    full.set()
                try:
                    await release.wait()
                    if frame['taskId'] == 0:
                        raise RuntimeError('one task upload failed')
                    completed.append(frame['taskId'])
                finally:
                    active -= 1

        async def finish_iteration(delay):
            raise asyncio.CancelledError

        monkeypatch.setattr(main.asyncio, 'sleep', finish_iteration)
        loop = asyncio.create_task(main.overlay_delivery_loop(
            SimpleNamespace(overlay_poll_interval_seconds=.1),
            SimpleNamespace(node_id=1), Control(), Runtime()))
        try:
            await asyncio.wait_for(full.wait(), timeout=1)
            assert entered == [0, 1, 2, 3]
            release.set()
            with pytest.raises(asyncio.CancelledError):
                await loop
            assert peak == 4
            assert completed == [1, 2, 3, 4, 5]
        finally:
            loop.cancel()
            await asyncio.gather(loop, return_exceptions=True)

    asyncio.run(scenario())
