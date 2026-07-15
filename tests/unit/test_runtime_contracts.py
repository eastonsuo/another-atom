import hashlib

import pytest

from another_atom.contracts.schemas import RuntimeBinding, SourceBundle
from another_atom.runtime.contracts import (
    RuntimeContractError,
    preflight_runtime,
    resolve_runtime_binding,
    source_manifest_hash,
)


def test_runtime_binding_hash_is_part_of_the_shared_contract() -> None:
    with pytest.raises(RuntimeContractError, match="hash does not match") as error:
        resolve_runtime_binding(
            RuntimeBinding(
                contract_id="web-static-document",
                contract_version="1.0",
                contract_hash="sha256:" + ("0" * 64),
            )
        )

    assert error.value.code == "RUNTIME_CONTRACT_HASH_MISMATCH"


def test_document_preflight_blocks_loopback_before_execution(
    client,
) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a browser notes tool", "mode": "team"},
    ).json()
    run = client.get(f"/api/runs/{created['run_id']}").json()
    client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    completed = client.get(f"/api/runs/{created['run_id']}").json()
    bundle = SourceBundle.model_validate(completed["source_bundle"])
    files = []
    for item in bundle.files:
        if item.path == "app.js":
            content = "fetch('http://localhost:11434/api');\n"
            item = item.model_copy(
                update={
                    "content": content,
                    "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
                }
            )
        files.append(item)
    candidate = bundle.model_copy(update={"files": files})
    candidate = candidate.model_copy(update={"manifest_hash": source_manifest_hash(candidate)})

    _, report = preflight_runtime(candidate)

    assert report.passed is False
    security = next(
        check for check in report.checks if check.check_id == "security.loopback_network"
    )
    assert security.status == "fail"
    assert security.root_cause == "security"


def test_document_preflight_requires_exactly_one_document_shell(client) -> None:
    created = client.post(
        "/api/runs",
        json={"prompt": "Build a browser notes tool", "mode": "team"},
    ).json()
    run = client.get(f"/api/runs/{created['run_id']}").json()
    client.post(
        f"/api/runs/{created['run_id']}/approve",
        json={"blueprint": run["blueprint"]},
    )
    completed = client.get(f"/api/runs/{created['run_id']}").json()
    bundle = SourceBundle.model_validate(completed["source_bundle"])
    files = []
    for item in bundle.files:
        if item.path == "index.html":
            content = item.content + "\n<html><head></head><body></body></html>\n"
            item = item.model_copy(
                update={
                    "content": content,
                    "content_hash": "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest(),
                }
            )
        files.append(item)
    candidate = bundle.model_copy(update={"files": files})
    candidate = candidate.model_copy(update={"manifest_hash": source_manifest_hash(candidate)})

    _, report = preflight_runtime(candidate)

    document = next(check for check in report.checks if check.check_id == "runtime.document")
    assert document.status == "fail"
