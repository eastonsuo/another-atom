from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import queue
import threading
import time
from collections.abc import AsyncIterator

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from another_atom.config import get_settings
from another_atom.contracts.schemas import ExecutionEvent, ExecutionRequest
from another_atom.executor.runner import ExecutorInputError, execute

app = FastAPI(title="Another Atom Runtime Executor")
_active_lock = threading.Lock()
_active_executions: dict[str, threading.Event] = {}


@app.get("/health")
def health() -> dict[str, str | int]:
    with _active_lock:
        active = len(_active_executions)
    return {"status": "ok", "adapter": "web-static-v1", "active_executions": active}


def _authenticate(
    authorization: str | None,
    timestamp_value: str | None,
) -> None:
    settings = get_settings()
    expected_auth = f"Bearer {settings.runtime_executor_shared_token}"
    if not hmac.compare_digest(authorization or "", expected_auth):
        raise HTTPException(status_code=401, detail="Invalid executor credential")
    try:
        timestamp = int(timestamp_value or "")
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="Invalid executor timestamp") from exc
    if abs(int(time.time()) - timestamp) > settings.runtime_executor_clock_skew_seconds:
        raise HTTPException(status_code=401, detail="Expired executor request")


@app.post("/v1/executions")
async def create_execution(
    request: Request,
    authorization: str | None = Header(default=None),
    x_executor_timestamp: str | None = Header(default=None),
    x_content_sha256: str | None = Header(default=None),
) -> StreamingResponse:
    settings = get_settings()
    _authenticate(authorization, x_executor_timestamp)
    body = await request.body()
    if len(body) > settings.runtime_executor_request_max_bytes:
        raise HTTPException(status_code=413, detail="Execution request is too large")
    digest = hashlib.sha256(body).hexdigest()
    if not hmac.compare_digest(x_content_sha256 or "", digest):
        raise HTTPException(status_code=400, detail="Execution body hash mismatch")
    try:
        execution_request = ExecutionRequest.model_validate_json(body)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    with _active_lock:
        if execution_request.execution_id in _active_executions:
            raise HTTPException(status_code=409, detail="Execution is already active")
        if len(_active_executions) >= settings.runtime_executor_max_concurrency:
            raise HTTPException(status_code=429, detail="Runtime Executor is at capacity")
        cancellation = threading.Event()
        _active_executions[execution_request.execution_id] = cancellation

    stream_queue: queue.Queue[tuple[str, object]] = queue.Queue()

    def event_handler(event: ExecutionEvent) -> None:
        stream_queue.put(("event", event))

    def run_execution() -> None:
        try:
            _, result = execute(
                execution_request,
                event_handler=event_handler,
                cancel_event=cancellation,
            )
            stream_queue.put(("result", result))
        except (ValueError, ExecutorInputError) as exc:
            stream_queue.put(("error", str(exc)))
        finally:
            with _active_lock:
                _active_executions.pop(execution_request.execution_id, None)
            stream_queue.put(("done", None))

    threading.Thread(target=run_execution, daemon=True).start()

    async def response_stream() -> AsyncIterator[bytes]:
        while True:
            kind, value = await asyncio.to_thread(stream_queue.get)
            if kind == "done":
                break
            if kind == "event":
                data = value.model_dump(mode="json")  # type: ignore[union-attr]
            elif kind == "result":
                data = value.model_dump(mode="json")  # type: ignore[union-attr]
            else:
                data = {"message": str(value)}
            yield (
                json.dumps({"kind": kind, "data": data}, ensure_ascii=False) + "\n"
            ).encode("utf-8")

    return StreamingResponse(response_stream(), media_type="application/x-ndjson")


@app.post("/v1/executions/{execution_id}/cancel")
def cancel_execution(
    execution_id: str,
    authorization: str | None = Header(default=None),
    x_executor_timestamp: str | None = Header(default=None),
) -> dict[str, str]:
    _authenticate(authorization, x_executor_timestamp)
    with _active_lock:
        cancellation = _active_executions.get(execution_id)
    if cancellation is None:
        raise HTTPException(status_code=404, detail="Active execution was not found")
    cancellation.set()
    return {"execution_id": execution_id, "status": "cancelling"}
