from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class CameraCredentials:
    username: str = ""
    password: str = ""


@dataclass(frozen=True)
class WifiCredentials:
    ssid: str = ""
    password: str = ""


class CredentialsStore(ABC):
    @property
    @abstractmethod
    def is_available(self) -> bool:
        raise NotImplementedError

    @abstractmethod
    def get_camera_credentials(self, camera_id: str) -> CameraCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def set_camera_credentials(self, camera_id: str, credentials: CameraCredentials) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_camera_credentials(self, camera_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def get_wifi_credentials(self, profile_id: str) -> WifiCredentials | None:
        raise NotImplementedError

    @abstractmethod
    def set_wifi_credentials(self, profile_id: str, credentials: WifiCredentials) -> bool:
        raise NotImplementedError

    @abstractmethod
    def delete_wifi_credentials(self, profile_id: str) -> None:
        raise NotImplementedError


class DisabledCredentialsStore(CredentialsStore):
    @property
    def is_available(self) -> bool:
        return False

    def get_camera_credentials(self, camera_id: str) -> CameraCredentials | None:
        return None

    def set_camera_credentials(self, camera_id: str, credentials: CameraCredentials) -> bool:
        return False

    def delete_camera_credentials(self, camera_id: str) -> None:
        return None

    def get_wifi_credentials(self, profile_id: str) -> WifiCredentials | None:
        return None

    def set_wifi_credentials(self, profile_id: str, credentials: WifiCredentials) -> bool:
        return False

    def delete_wifi_credentials(self, profile_id: str) -> None:
        return None


class KeyringCredentialsStore(CredentialsStore):
    def __init__(self, service_name: str = "arcane-eyes"):
        self.service_name = service_name
        try:
            import keyring
        except Exception:
            self._keyring = None
        else:
            self._keyring = keyring

    @property
    def is_available(self) -> bool:
        if self._keyring is None:
            return False
        try:
            backend = self._keyring.get_keyring()
            return backend is not None and backend.priority > 0
        except Exception:
            return False

    def _get(self, key: str) -> str | None:
        if not self.is_available:
            return None
        try:
            return self._keyring.get_password(self.service_name, key)
        except Exception:
            return None

    def _set(self, key: str, value: str) -> bool:
        if not self.is_available:
            return False
        try:
            self._keyring.set_password(self.service_name, key, value)
        except Exception:
            return False
        return True

    def _delete(self, key: str) -> None:
        if not self.is_available:
            return
        try:
            self._keyring.delete_password(self.service_name, key)
        except Exception:
            return

    def get_camera_credentials(self, camera_id: str) -> CameraCredentials | None:
        username = self._get(f"camera:{camera_id}:username")
        password = self._get(f"camera:{camera_id}:password")
        if username is None and password is None:
            return None
        return CameraCredentials(username=username or "", password=password or "")

    def set_camera_credentials(self, camera_id: str, credentials: CameraCredentials) -> bool:
        username_ok = self._set(f"camera:{camera_id}:username", credentials.username)
        password_ok = self._set(f"camera:{camera_id}:password", credentials.password)
        return username_ok and password_ok

    def delete_camera_credentials(self, camera_id: str) -> None:
        self._delete(f"camera:{camera_id}:username")
        self._delete(f"camera:{camera_id}:password")

    def get_wifi_credentials(self, profile_id: str) -> WifiCredentials | None:
        ssid = self._get(f"wifi:{profile_id}:ssid")
        password = self._get(f"wifi:{profile_id}:password")
        if ssid is None and password is None:
            return None
        return WifiCredentials(ssid=ssid or "", password=password or "")

    def set_wifi_credentials(self, profile_id: str, credentials: WifiCredentials) -> bool:
        ssid_ok = self._set(f"wifi:{profile_id}:ssid", credentials.ssid)
        password_ok = self._set(f"wifi:{profile_id}:password", credentials.password)
        return ssid_ok and password_ok

    def delete_wifi_credentials(self, profile_id: str) -> None:
        self._delete(f"wifi:{profile_id}:ssid")
        self._delete(f"wifi:{profile_id}:password")


class AndroidCredentialsStore(DisabledCredentialsStore):
    pass
