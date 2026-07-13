import json
from pathlib import Path

from app.desktop.instance import (
    APPLICATION_ID,
    PROTOCOL_VERSION,
    InstanceMetadata,
    InstanceStore,
    find_free_port,
    validate_instance,
)


def test_instance_store_round_trips_metadata_atomically(tmp_path: Path):
    store = InstanceStore(tmp_path)
    metadata = InstanceMetadata(pid=1234, port=45678)

    store.write(metadata)

    payload = json.loads((tmp_path / "instance.json").read_text(encoding="utf-8"))
    assert payload["application"] == APPLICATION_ID
    assert payload["protocol_version"] == PROTOCOL_VERSION
    assert store.read() == metadata


def test_instance_store_only_removes_metadata_owned_by_pid(tmp_path: Path):
    store = InstanceStore(tmp_path)
    store.write(InstanceMetadata(pid=100, port=45678))

    store.remove_if_owned_by(200)
    assert store.read() is not None
    store.remove_if_owned_by(100)
    assert store.read() is None


def test_validate_instance_rejects_generic_ready_response():
    metadata = InstanceMetadata(pid=1234, port=45678)

    assert not validate_instance(metadata, fetch_json=lambda _url: {"status": "ok"})
    assert validate_instance(
        metadata,
        fetch_json=lambda _url: {
            "application": APPLICATION_ID,
            "protocol_version": PROTOCOL_VERSION,
            "status": "ok",
        },
    )


def test_find_free_port_returns_bindable_ephemeral_port():
    port = find_free_port()
    assert 1024 < port < 65536
