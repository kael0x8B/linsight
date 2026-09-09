import os
from pathlib import Path

import pytest
from pydantic import SecretStr

from edge_agent.app.core.identity import IdentityStore, NodeIdentity


def test_identity_store_round_trip_uses_owner_only_permissions(tmp_path: Path) -> None:
    path = tmp_path / "identity.json"
    store = IdentityStore(path)
    identity = NodeIdentity(
        node_id=10,
        tenant_id=2,
        credential=SecretStr("long-term-secret"),
        heartbeat_sequence=7,
    )

    store.save(identity)
    loaded = store.load()

    assert loaded is not None
    assert loaded.credential.get_secret_value() == "long-term-secret"
    assert loaded.heartbeat_sequence == 7
    assert path.stat().st_mode & 0o777 == 0o600


def test_identity_store_rejects_overly_permissive_file(tmp_path: Path) -> None:
    path = tmp_path / "identity.json"
    store = IdentityStore(path)
    store.save(
        NodeIdentity(
            node_id=10,
            tenant_id=2,
            credential=SecretStr("long-term-secret"),
        )
    )
    os.chmod(path, 0o644)

    with pytest.raises(PermissionError):
        store.load()
