import asyncio

import pytest

from edge_agent.app.command.entry_evidence import deliver_pending, save_pending


def setup(tmp_path):
    key = "00000000-0000-0000-0000-000000000001"
    folder = tmp_path / "entry-evidence" / key
    folder.mkdir(parents=True)
    image = folder / "snapshot.jpg"
    image.write_bytes(b"fixture-image")
    save_pending(tmp_path, key, {"snapshotPath": str(image)})
    return image, tmp_path / "entry-evidence-outbox" / (key + ".json")


def test_failed_delivery_is_retained_and_retry_cleans(tmp_path):
    image, path = setup(tmp_path)

    class Client:
        fail = True

        async def get_entry_command(self, *args, **kwargs):
            return {"status": "SUCCEEDED", "eventId": 8}

        async def upload_event_media(self, *args):
            if self.fail:
                raise RuntimeError("offline")
            return 9

    async def run():
        client = Client()
        with pytest.raises(RuntimeError):
            await deliver_pending(tmp_path, None, client, path)
        assert path.exists() and image.exists()
        client.fail = False
        await deliver_pending(tmp_path, None, client, path)
        assert not path.exists() and not image.exists()

    asyncio.run(run())


def test_cancelled_without_event_does_not_upload(tmp_path):
    image, path = setup(tmp_path)

    class Client:
        async def get_entry_command(self, *args, **kwargs):
            return {"status": "CANCELLED", "eventId": None}

        async def upload_event_media(self, *args):
            raise AssertionError("unexpected upload")

    asyncio.run(deliver_pending(tmp_path, None, Client(), path))
    assert not image.exists() and not path.exists()


def test_tampered_file_is_not_sent_or_deleted(tmp_path):
    image, path = setup(tmp_path)
    image.write_bytes(b"tampered")

    class Client:
        async def get_entry_command(self, *args, **kwargs):
            return {"status": "SUCCEEDED", "eventId": 8}

        async def upload_event_media(self, *args):
            raise AssertionError("unexpected upload")

    with pytest.raises(ValueError, match="SHA256"):
        asyncio.run(deliver_pending(tmp_path, None, Client(), path))
    assert image.exists() and path.exists()
