from __future__ import annotations

import hashlib
import json
import time

import httpx

from another_atom.config import get_settings
from another_atom.contracts.schemas import ExecutionEvent, ExecutionRequest, ExecutionResult
from another_atom.executor.runner import execute


class RuntimeExecutorError(RuntimeError):
    pass


def _validate_result(request: ExecutionRequest, result: ExecutionResult) -> None:
    if result.execution_id != request.execution_id:
        raise RuntimeExecutorError("Runtime Executor returned the wrong execution_id")
    if result.request_hash != request.request_hash:
        raise RuntimeExecutorError("Runtime Executor returned the wrong request_hash")
    if result.adapter_id != request.adapter_id:
        raise RuntimeExecutorError("Runtime Executor returned the wrong adapter_id")
    expected_source_hash = request.source_manifest_hash.removeprefix("sha256:")
    if result.source_manifest_hash != expected_source_hash:
        raise RuntimeExecutorError("Runtime Executor returned the wrong source_manifest_hash")


def execute_request(
    request: ExecutionRequest,
) -> tuple[list[ExecutionEvent], ExecutionResult]:
    settings = get_settings()
    if settings.environment == "test":
        events, result = execute(request)
        _validate_result(request, result)
        return events, result
    body = json.dumps(request.model_dump(mode="json"), ensure_ascii=False).encode("utf-8")
    events: list[ExecutionEvent] = []
    result: ExecutionResult | None = None
    headers = {
        "Authorization": f"Bearer {settings.runtime_executor_shared_token}",
        "X-Executor-Timestamp": str(int(time.time())),
        "X-Content-SHA256": hashlib.sha256(body).hexdigest(),
        "Content-Type": "application/json",
        "Accept": "application/x-ndjson",
    }
    try:
        with httpx.stream(
            "POST",
            f"{settings.runtime_executor_url.rstrip('/')}/v1/executions",
            content=body,
            headers=headers,
            timeout=settings.runtime_executor_timeout_seconds,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                envelope = json.loads(line)
                if envelope.get("kind") == "event":
                    events.append(ExecutionEvent.model_validate(envelope["data"]))
                elif envelope.get("kind") == "result":
                    result = ExecutionResult.model_validate(envelope["data"])
                elif envelope.get("kind") == "error":
                    raise RuntimeExecutorError(str(envelope.get("data", {}).get("message")))
    except httpx.HTTPError as exc:
        raise RuntimeExecutorError(f"Runtime Executor unavailable: {exc}") from exc
    if result is None:
        raise RuntimeExecutorError("Runtime Executor ended without an ExecutionResult")
    _validate_result(request, result)
    return events, result
