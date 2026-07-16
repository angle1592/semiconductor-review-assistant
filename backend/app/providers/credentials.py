from typing import Protocol

from app.runtime.identity import CREDENTIAL_SERVICE_NAME


class SecretStore(Protocol):
    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class MemorySecretStore:
    def __init__(self):
        self._values: dict[str, str] = {}

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def delete(self, key: str) -> None:
        self._values.pop(key, None)


class WindowsKeyringSecretStore:
    def __init__(self, service_name: str = CREDENTIAL_SERVICE_NAME):
        self.service_name = service_name

    def get(self, key: str) -> str | None:
        import keyring
        return keyring.get_password(self.service_name, key)

    def set(self, key: str, value: str) -> None:
        import keyring
        keyring.set_password(self.service_name, key, value)

    def delete(self, key: str) -> None:
        import keyring
        from keyring.errors import PasswordDeleteError
        try:
            keyring.delete_password(self.service_name, key)
        except PasswordDeleteError:
            pass


def credential_key(profile_id: str) -> str:
    return f"provider:{profile_id}:api_key"
