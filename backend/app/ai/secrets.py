from typing import Protocol


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
    """Stores secrets in Windows Credential Manager through keyring."""

    def __init__(self, service_name: str = "semiconductor-review-assistant"):
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
