from pathlib import Path

from app.providers.credentials import MemorySecretStore, credential_key
from app.providers.schemas import ProviderProfileCreate, ProviderProfileUpdate
from app.providers.service import ProviderProfileService
from app.shared.database import create_database


def test_profiles_keep_only_secret_reference_in_database(tmp_path: Path):
    secrets = MemorySecretStore()
    service = ProviderProfileService(create_database(tmp_path), secrets)

    profile = service.create(
        ProviderProfileCreate(
            name="主力服务",
            protocol="openai_compatible",
            base_url="https://example.test/v1",
            api_key="sk-secret-value",
        )
    )

    assert profile.api_key_configured is True
    assert secrets.get(credential_key(profile.id)) == "sk-secret-value"
    assert "sk-secret-value" not in (tmp_path / "shiyao.db").read_bytes().decode("latin1")


def test_replacing_and_deleting_key_updates_credential_namespace(tmp_path: Path):
    secrets = MemorySecretStore()
    service = ProviderProfileService(create_database(tmp_path), secrets)
    profile = service.create(ProviderProfileCreate(name="服务", protocol="anthropic", base_url="https://api.anthropic.com", api_key="first"))

    updated = service.replace_key(profile.id, "second")
    assert updated.credential_generation == 2
    assert secrets.get(credential_key(profile.id)) == "second"

    service.delete(profile.id)
    assert secrets.get(credential_key(profile.id)) is None


def test_endpoint_edit_increments_generation_for_future_cache_keys(tmp_path: Path):
    service = ProviderProfileService(create_database(tmp_path), MemorySecretStore())
    profile = service.create(
        ProviderProfileCreate(
            name="服务",
            protocol="openai_compatible",
            base_url="https://first.test/v1",
        )
    )

    updated = service.update(
        profile.id,
        ProviderProfileUpdate(base_url="https://second.test/v1"),
    )

    assert updated.credential_generation == profile.credential_generation + 1
