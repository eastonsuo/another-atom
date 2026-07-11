import asyncio
import fcntl
import json
import os
import pty
import secrets
import shutil
import struct
import subprocess
import termios
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import Depends, FastAPI, Header, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field

from another_atom.config import get_settings
from another_atom.repository.service import RepositoryError, repository_path
from another_atom.storage.models import now_utc


class HostSessionRequest(BaseModel):
    project_id: str = Field(pattern=r"^[0-9a-f-]{36}$")


@dataclass
class HostSession:
    id: str
    project_id: str
    token: str
    worktree: Path
    expires_at: datetime


SESSIONS: dict[str, HostSession] = {}


def require_internal_auth(authorization: str = Header(default="")) -> None:
    expected = get_settings().sandbox_shared_secret
    if not expected or not secrets.compare_digest(authorization, f"Bearer {expected}"):
        from fastapi import HTTPException

        raise HTTPException(status_code=401, detail="Invalid Sandbox Host credential")


def create_sandbox_host() -> FastAPI:
    app = FastAPI(title="Another Atom Sandbox Host", version="0.1.0")

    @app.post("/v1/sessions", dependencies=[Depends(require_internal_auth)])
    def create_session(request: HostSessionRequest) -> dict:
        settings = get_settings()
        source = repository_path(request.project_id)
        if not (source / ".git").is_dir():
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Project repository was not found")
        session_id = secrets.token_hex(16)
        token = secrets.token_urlsafe(32)
        worktree = (settings.sandbox_worktree_root / session_id).resolve()
        worktree.parent.mkdir(parents=True, exist_ok=True)
        _git_worktree(source, "add", "--detach", str(worktree), "HEAD")
        git_pointer = worktree / ".git"
        if git_pointer.is_file():
            git_pointer.unlink()
        expires_at = now_utc() + timedelta(minutes=settings.sandbox_session_minutes)
        SESSIONS[session_id] = HostSession(
            id=session_id,
            project_id=request.project_id,
            token=token,
            worktree=worktree,
            expires_at=expires_at,
        )
        return {
            "session_id": session_id,
            "terminal_token": token,
            "expires_at": expires_at.isoformat(),
        }

    @app.get(
        "/v1/sessions/{session_id}/app-spec",
        dependencies=[Depends(require_internal_auth)],
    )
    def read_app_spec(session_id: str) -> dict:
        host_session = _session(session_id)
        try:
            return json.loads((host_session.worktree / "app-spec.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            from fastapi import HTTPException

            raise HTTPException(status_code=422, detail=f"Invalid app-spec.json: {exc}") from exc

    @app.delete("/v1/sessions/{session_id}", dependencies=[Depends(require_internal_auth)])
    def close_session(session_id: str) -> dict:
        host_session = _session(session_id)
        _remove_worktree(host_session)
        SESSIONS.pop(session_id, None)
        return {"closed": True}

    @app.websocket("/v1/sessions/{session_id}/terminal")
    async def terminal(websocket: WebSocket, session_id: str, token: str = "") -> None:
        host_session = SESSIONS.get(session_id)
        if host_session is None or not secrets.compare_digest(host_session.token, token):
            await websocket.close(code=4401)
            return
        if host_session.expires_at <= now_utc():
            await websocket.close(code=4408)
            return
        await websocket.accept()
        await _run_restricted_vim(websocket, host_session)

    return app


def sandbox_command(host_session: HostSession) -> list[str]:
    settings = get_settings()
    return [
        "docker",
        "run",
        "--rm",
        "-i",
        "-t",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges",
        "--pids-limit=64",
        "--memory=256m",
        "--cpus=0.5",
        f"--user={os.getuid()}:{os.getgid()}",
        "--tmpfs=/tmp:rw,noexec,nosuid,size=16m",
        f"--volume={host_session.worktree}:/workspace:rw",
        settings.sandbox_image,
        "vim",
        "-Z",
        "-n",
        "-u",
        "/etc/another-atom/vimrc",
        "/workspace/app-spec.json",
    ]


async def _run_restricted_vim(websocket: WebSocket, host_session: HostSession) -> None:
    master, slave = pty.openpty()
    process = subprocess.Popen(
        sandbox_command(host_session),
        stdin=slave,
        stdout=slave,
        stderr=slave,
        close_fds=True,
    )
    os.close(slave)

    async def send_output() -> None:
        while process.poll() is None:
            data = await asyncio.to_thread(os.read, master, 4096)
            if not data:
                break
            await websocket.send_bytes(data)

    async def receive_input() -> None:
        while process.poll() is None:
            message = await websocket.receive()
            if message.get("bytes"):
                os.write(master, message["bytes"])
            elif message.get("text"):
                payload = json.loads(message["text"])
                if payload.get("type") == "input":
                    os.write(master, payload.get("data", "").encode())
                elif payload.get("type") == "resize":
                    size = struct.pack("HHHH", payload["rows"], payload["cols"], 0, 0)
                    fcntl.ioctl(master, termios.TIOCSWINSZ, size)

    async def expire_session() -> None:
        remaining = max(0.0, (host_session.expires_at - now_utc()).total_seconds())
        await asyncio.sleep(remaining)

    try:
        tasks = {
            asyncio.create_task(send_output()),
            asyncio.create_task(receive_input()),
            asyncio.create_task(expire_session()),
        }
        _, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    except (WebSocketDisconnect, OSError, json.JSONDecodeError):
        pass
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                await asyncio.to_thread(process.wait, 3)
            except subprocess.TimeoutExpired:
                process.kill()
        os.close(master)


def _session(session_id: str) -> HostSession:
    host_session = SESSIONS.get(session_id)
    if host_session is None or host_session.expires_at <= now_utc():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Sandbox session was not found")
    return host_session


def _git_worktree(repository: Path, *arguments: str) -> None:
    result = subprocess.run(
        ["git", "-C", str(repository), "worktree", *arguments],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        raise RepositoryError(result.stderr.strip() or "git worktree failed")


def _remove_worktree(host_session: HostSession) -> None:
    repository = repository_path(host_session.project_id)
    shutil.rmtree(host_session.worktree, ignore_errors=True)
    _git_worktree(repository, "prune", "--expire", "now")


app = create_sandbox_host()
