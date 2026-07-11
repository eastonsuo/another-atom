from dataclasses import dataclass
from datetime import datetime

import httpx

from another_atom.config import get_settings
from another_atom.contracts.schemas import AppSpec


class SandboxUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class RemoteSandboxSession:
    session_id: str
    terminal_token: str
    expires_at: datetime


class SandboxClient:
    def __init__(self) -> None:
        settings = get_settings()
        if not settings.sandbox_host_url or not settings.sandbox_shared_secret:
            raise SandboxUnavailable("SANDBOX_HOST_URL and SANDBOX_SHARED_SECRET are required")
        self.base_url = settings.sandbox_host_url.rstrip("/")
        self.secret = settings.sandbox_shared_secret

    @property
    def headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.secret}"}

    def create(self, project_id: str) -> RemoteSandboxSession:
        try:
            response = httpx.post(
                f"{self.base_url}/v1/sessions",
                headers=self.headers,
                json={"project_id": project_id},
                timeout=20,
            )
            response.raise_for_status()
            body = response.json()
            return RemoteSandboxSession(
                session_id=body["session_id"],
                terminal_token=body["terminal_token"],
                expires_at=datetime.fromisoformat(body["expires_at"]),
            )
        except (httpx.HTTPError, KeyError, ValueError) as exc:
            raise SandboxUnavailable(f"Sandbox Host session creation failed: {exc}") from exc

    def read_app_spec(self, session_id: str) -> AppSpec:
        try:
            response = httpx.get(
                f"{self.base_url}/v1/sessions/{session_id}/app-spec",
                headers=self.headers,
                timeout=20,
            )
            response.raise_for_status()
            return AppSpec.model_validate(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise SandboxUnavailable(f"Sandbox Host could not read AppSpec: {exc}") from exc

    def close(self, session_id: str) -> None:
        try:
            response = httpx.delete(
                f"{self.base_url}/v1/sessions/{session_id}",
                headers=self.headers,
                timeout=20,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SandboxUnavailable(f"Sandbox Host cleanup failed: {exc}") from exc

    def websocket_url(self, session_id: str, terminal_token: str) -> str:
        scheme = "wss" if self.base_url.startswith("https://") else "ws"
        host = self.base_url.split("://", 1)[-1]
        return f"{scheme}://{host}/v1/sessions/{session_id}/terminal?token={terminal_token}"


def get_sandbox_client() -> SandboxClient:
    try:
        return SandboxClient()
    except SandboxUnavailable as exc:
        from another_atom.domain.errors import AppError

        raise AppError("SANDBOX_NOT_CONFIGURED", str(exc), 503) from exc
