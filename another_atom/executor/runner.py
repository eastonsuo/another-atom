from __future__ import annotations

import hashlib
import json
import os
import subprocess
import tempfile
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from another_atom.build.renderer import validate_app_spec
from another_atom.contracts.schemas import (
    BuildArtifact,
    BuildArtifactFile,
    CommandExecution,
    ExecutionEvent,
    ExecutionReport,
    ExecutionRequest,
    ExecutionResult,
    ValidationCheck,
    ValidationReport,
)


class ExecutorInputError(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(UTC)


def _manifest_hash(request: ExecutionRequest) -> str:
    payload = [
        {"path": item.path, "role": item.role, "content_hash": item.content_hash}
        for item in sorted(request.source_bundle.files, key=lambda item: item.path)
    ]
    value = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return f"sha256:{hashlib.sha256(value.encode('utf-8')).hexdigest()}"


def _verify_request(request: ExecutionRequest) -> None:
    request_payload = request.model_dump(
        mode="json", exclude={"schema_version", "request_hash"}
    )
    request_digest = hashlib.sha256(
        json.dumps(
            request_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    if request_digest != request.request_hash:
        raise ExecutorInputError("ExecutionRequest hash is invalid")
    if request.product_spec_hash != request.architecture_design.product_spec_hash:
        raise ExecutorInputError("ArchitectureDesign does not match ProductSpec")
    if request.architecture_design_hash != request.architecture_design.content_hash:
        raise ExecutorInputError("ArchitectureDesign hash is invalid")
    if request.source_manifest_hash != request.source_bundle.manifest_hash:
        raise ExecutorInputError("ExecutionRequest source hash does not match SourceBundle")
    if _manifest_hash(request) != request.source_bundle.manifest_hash:
        raise ExecutorInputError("SourceBundle manifest hash is invalid")
    for item in request.source_bundle.files:
        digest = f"sha256:{hashlib.sha256(item.content.encode('utf-8')).hexdigest()}"
        if digest != item.content_hash:
            raise ExecutorInputError(f"Source file hash is invalid: {item.path}")


def _run_command(
    arguments: list[str],
    cwd: Path,
    timeout_seconds: float,
    cancel_event: threading.Event,
) -> CommandExecution:
    started = time.monotonic()
    if timeout_seconds <= 0:
        return CommandExecution(
            status="timeout",
            duration_ms=0,
            stderr="Execution deadline expired before the command started.",
        )
    environment = {
        "PATH": os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin"),
        "HOME": str(cwd),
        "LANG": "C.UTF-8",
        "NO_COLOR": "1",
    }
    process = subprocess.Popen(
        arguments,
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    status = "passed"
    while process.poll() is None:
        if cancel_event.is_set():
            process.kill()
            status = "cancelled"
            break
        if time.monotonic() - started >= timeout_seconds:
            process.kill()
            status = "timeout"
            break
        time.sleep(0.05)
    stdout, stderr = process.communicate()
    if status == "passed" and process.returncode != 0:
        status = "failed"
    return CommandExecution(
        status=status,
        exit_code=process.returncode,
        duration_ms=int((time.monotonic() - started) * 1000),
        stdout=stdout[-20_000:],
        stderr=stderr[-20_000:],
    )


def _artifact(workspace: Path) -> BuildArtifact:
    files: list[BuildArtifactFile] = []
    for path in ("index.html", "styles.css", "app.js"):
        content = (workspace / path).read_text(encoding="utf-8")
        encoded = content.encode("utf-8")
        files.append(
            BuildArtifactFile(
                path=path,
                content=content,
                size_bytes=len(encoded),
                content_hash=hashlib.sha256(encoded).hexdigest(),
            )
        )
    manifest = "\n".join(f"{item.path}\0{item.content_hash}" for item in files)
    return BuildArtifact(
        files=files,
        manifest_hash=hashlib.sha256(manifest.encode("utf-8")).hexdigest(),
    )


def execute(
    request: ExecutionRequest,
    *,
    event_handler: Callable[[ExecutionEvent], None] | None = None,
    cancel_event: threading.Event | None = None,
) -> tuple[list[ExecutionEvent], ExecutionResult]:
    _verify_request(request)
    cancellation = cancel_event or threading.Event()
    started_at = _now()
    deadline = time.monotonic() + (request.deadline_ms / 1000)
    events: list[ExecutionEvent] = []

    def event(event_type: str, **payload: object) -> None:
        execution_event = ExecutionEvent(
            execution_id=request.execution_id,
            sequence=len(events) + 1,
            type=event_type,
            timestamp=_now(),
            payload=payload,
        )
        events.append(execution_event)
        if event_handler is not None:
            event_handler(execution_event)

    event("execution.accepted", adapter_id=request.adapter_id)
    with tempfile.TemporaryDirectory(prefix="another-atom-execution-") as temp:
        workspace = Path(temp)
        event("source.materializing")
        for item in request.source_bundle.files:
            candidate = workspace / item.path
            candidate.parent.mkdir(parents=True, exist_ok=True)
            candidate.write_text(item.content, encoding="utf-8")
        event("source.materialized", files=len(request.source_bundle.files))

        event("build.started")
        build = _run_command(
            ["node", "--check", "app.js"],
            workspace,
            min(30, deadline - time.monotonic()),
            cancellation,
        )
        event("build.completed", status=build.status, exit_code=build.exit_code)

        test_files = sorted(
            item.path for item in request.source_bundle.files if item.role == "test"
        )
        if build.status == "passed" and not cancellation.is_set():
            event("test.started", tests=len(test_files))
            test = _run_command(
                ["node", "--test", *test_files],
                workspace,
                min(60, deadline - time.monotonic()),
                cancellation,
            )
            event("test.completed", status=test.status, exit_code=test.exit_code)
        else:
            test = CommandExecution(status="not_run", duration_ms=0)

        if cancellation.is_set():
            validation = ValidationReport(
                passed=False,
                checks=[
                    ValidationCheck(
                        check_id="runtime.cancelled",
                        label="Runtime execution cancelled",
                        status="fail",
                        root_cause="platform",
                        detail="Execution was cancelled by the Control Plane.",
                    )
                ],
            )
            event("execution.cancelled")
            report = ExecutionReport(
                execution_id=request.execution_id,
                adapter_id=request.adapter_id,
                source_manifest_hash=request.source_bundle.manifest_hash.removeprefix(
                    "sha256:"
                ),
                status="cancelled",
                build=build,
                test=test,
                tests_collected=len(test_files),
                tests_passed=0,
                tests_failed=0,
                started_at=started_at,
                finished_at=_now(),
                error_code="EXECUTION_CANCELLED",
                error_message="执行已由主服务取消。",
            )
            return events, ExecutionResult(
                execution_id=request.execution_id,
                request_hash=request.request_hash,
                adapter_id=request.adapter_id,
                source_manifest_hash=request.source_bundle.manifest_hash.removeprefix(
                    "sha256:"
                ),
                status="cancelled",
                execution_report=report,
                validation_report=validation,
            )

        event("validation.started")
        validation = validate_app_spec(
            request.app_spec,
            request.prompt,
            blueprint=request.blueprint,
            architecture_spec=request.architecture_design.visual_tokens,
        )
        if build.status == "failed":
            validation = ValidationReport(
                passed=False,
                checks=[
                    *validation.checks,
                    ValidationCheck(
                        check_id="runtime.javascript_syntax",
                        label="JavaScript syntax build",
                        status="fail",
                        root_cause="app_spec",
                        resolvable=True,
                        detail=build.stderr or "node --check failed",
                    ),
                ],
            )
        if test.status == "failed":
            validation = ValidationReport(
                passed=False,
                checks=[
                    *validation.checks,
                    ValidationCheck(
                        check_id="runtime.unit_tests",
                        label="Engineer unit tests",
                        status="fail",
                        root_cause="app_spec",
                        resolvable=True,
                        detail=test.stderr or test.stdout or "node --test failed",
                    ),
                ],
            )
        deadline_exceeded = (
            build.status == "timeout"
            or test.status == "timeout"
            or time.monotonic() >= deadline
        )
        if deadline_exceeded:
            validation = ValidationReport(
                passed=False,
                checks=[
                    *validation.checks,
                    ValidationCheck(
                        check_id="runtime.timeout",
                        label="Runtime execution deadline",
                        status="fail",
                        root_cause="platform",
                        detail="Execution exceeded the deadline supplied by the Control Plane.",
                    ),
                ],
            )
        event("validation.completed", passed=validation.passed)
        passed = build.status == "passed" and test.status == "passed" and validation.passed
        status = "passed" if passed else "failed"
        execution_report = ExecutionReport(
            execution_id=request.execution_id,
            adapter_id=request.adapter_id,
            source_manifest_hash=request.source_bundle.manifest_hash.removeprefix("sha256:"),
            status=status,
            build=build,
            test=test,
            tests_collected=len(test_files),
            tests_passed=len(test_files) if test.status == "passed" else 0,
            tests_failed=len(test_files) if test.status == "failed" else 0,
            started_at=started_at,
            finished_at=_now(),
            error_code=(
                None
                if passed
                else "EXECUTION_TIMEOUT"
                if deadline_exceeded
                else "EXECUTION_VALIDATION_FAILED"
            ),
            error_message=(
                None
                if passed
                else "执行超过主服务指定的截止时间。"
                if deadline_exceeded
                else "构建、单元测试或确定性验证未通过。"
            ),
        )
        build_artifact = _artifact(workspace) if build.status == "passed" else None
        event("execution.completed" if passed else "execution.failed", status=status)
        result = ExecutionResult(
            execution_id=request.execution_id,
            request_hash=request.request_hash,
            adapter_id=request.adapter_id,
            source_manifest_hash=request.source_bundle.manifest_hash.removeprefix("sha256:"),
            status=status,
            build_artifact=build_artifact,
            execution_report=execution_report,
            validation_report=validation,
        )
        return events, result
