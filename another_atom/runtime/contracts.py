from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable

from another_atom.contracts.schemas import (
    RuntimeBinding,
    RuntimeCapabilities,
    RuntimeContract,
    SourceBundle,
    ValidationCheck,
    ValidationReport,
)


class RuntimeContractError(ValueError):
    def __init__(self, code: str, message: str, *, blocked: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.blocked = blocked


WEB_PROJECT_TYPES = {
    "product_catalog",
    "tool",
    "web_application",
    "web_game",
    "website",
}


def _canonical_hash(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=lambda value: value.model_dump(mode="json"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _contract(**values: object) -> RuntimeContract:
    payload = {"schema_version": "1.0", **values}
    return RuntimeContract(**payload, contract_hash=_canonical_hash(payload))


_CONTRACTS = {
    ("web-static-v1", "1.0"): _contract(
        contract_id="web-static-v1",
        version="1.0",
        lifecycle="legacy_read_only",
        supported_project_types=sorted(WEB_PROJECT_TYPES),
        document_semantics="fragment",
        required_files=["index.html", "styles.css", "app.js", "app-spec.json"],
        required_entrypoint_kinds=[],
        tests_required=True,
        allowed_manifest_files=[],
        dependency_installation="forbidden",
        network_policy="public_https_only",
        capabilities=RuntimeCapabilities(build=True, test=True, preview=True, publish=True),
        execution_plan="web-static-v1",
        max_files=24,
        max_file_bytes=256_000,
        max_total_bytes=1_000_000,
    ),
    ("web-static-document", "1.0"): _contract(
        contract_id="web-static-document",
        version="1.0",
        lifecycle="active",
        supported_project_types=sorted(WEB_PROJECT_TYPES),
        document_semantics="document",
        required_files=["index.html"],
        required_entrypoint_kinds=["application", "test"],
        tests_required=True,
        allowed_manifest_files=[],
        dependency_installation="forbidden",
        network_policy="public_https_only",
        capabilities=RuntimeCapabilities(build=True, test=True, preview=True, publish=True),
        execution_plan="web-static-document",
        max_files=128,
        max_file_bytes=256_000,
        max_total_bytes=2_000_000,
    ),
}


def registered_runtime_contracts() -> tuple[RuntimeContract, ...]:
    return tuple(_CONTRACTS[key] for key in sorted(_CONTRACTS))


def get_runtime_contract(contract_id: str, version: str) -> RuntimeContract:
    contract = _CONTRACTS.get((contract_id, version))
    if contract is None:
        raise RuntimeContractError(
            "RUNTIME_CONTRACT_NOT_FOUND",
            f"Runtime Contract is not registered: {contract_id}@{version}",
        )
    return contract


def runtime_binding(contract: RuntimeContract) -> RuntimeBinding:
    return RuntimeBinding(
        contract_id=contract.contract_id,
        contract_version=contract.version,
        contract_hash=contract.contract_hash,
    )


def resolve_runtime_binding(binding: RuntimeBinding) -> RuntimeContract:
    contract = get_runtime_contract(binding.contract_id, binding.contract_version)
    if contract.contract_hash != binding.contract_hash:
        raise RuntimeContractError(
            "RUNTIME_CONTRACT_HASH_MISMATCH",
            "Runtime Contract hash does not match "
            f"{binding.contract_id}@{binding.contract_version}",
        )
    return contract


def select_runtime_contract(project_type: str) -> RuntimeContract | None:
    if project_type.casefold() in WEB_PROJECT_TYPES:
        return get_runtime_contract("web-static-document", "1.0")
    return None


def source_manifest_hash(bundle: SourceBundle) -> str:
    if bundle.schema_version == "1.0":
        payload = [
            {"path": item.path, "role": item.role, "content_hash": item.content_hash}
            for item in sorted(bundle.files, key=lambda item: item.path)
        ]
    else:
        payload = [
            {
                "path": item.path,
                "role": item.role,
                "encoding": item.encoding,
                "content_hash": item.content_hash,
            }
            for item in sorted(bundle.files, key=lambda item: item.path)
        ]
    return _canonical_hash(payload)


def _check(
    check_id: str,
    label: str,
    passed: bool,
    *,
    detail: str | None = None,
    root_cause: str = "source",
    resolvable: bool = True,
) -> ValidationCheck:
    return ValidationCheck(
        check_id=check_id,
        label=label,
        status="pass" if passed else "fail",
        root_cause=root_cause,
        resolvable=resolvable,
        detail=None if passed else detail,
    )


def validate_source_bundle(bundle: SourceBundle) -> ValidationReport:
    checks: list[ValidationCheck] = []
    invalid_hashes = [
        item.path
        for item in bundle.files
        if item.content_hash != f"sha256:{hashlib.sha256(item.content.encode('utf-8')).hexdigest()}"
    ]
    checks.append(
        _check(
            "source.content_hashes",
            "Source file content hashes match",
            not invalid_hashes,
            detail=f"Invalid content hash: {', '.join(invalid_hashes)}",
        )
    )
    actual_manifest = source_manifest_hash(bundle)
    checks.append(
        _check(
            "source.manifest_hash",
            "Source manifest hash matches",
            actual_manifest == bundle.manifest_hash,
            detail="SourceBundle manifest_hash does not match its sorted file manifest",
        )
    )
    if bundle.schema_version == "2.0":
        paths = {item.path for item in bundle.files}
        entrypoint_paths = {item.path for item in bundle.entrypoints}
        checks.append(
            _check(
                "source.entrypoints",
                "Declared entrypoints exist in the source bundle",
                entrypoint_paths <= paths,
                detail="One or more declared entrypoints are missing",
            )
        )
    return ValidationReport(
        passed=all(check.status != "fail" for check in checks),
        checks=checks,
    )


def preflight_runtime(bundle: SourceBundle) -> tuple[RuntimeContract, ValidationReport]:
    if bundle.runtime_binding is None:
        raise RuntimeContractError(
            "RUNTIME_BINDING_MISSING",
            "SourceBundle has no RuntimeBinding and must use the source_ready path",
        )
    contract = resolve_runtime_binding(bundle.runtime_binding)
    checks = list(validate_source_bundle(bundle).checks)
    files = {item.path: item for item in bundle.files}
    total_bytes = sum(len(item.content.encode("utf-8")) for item in bundle.files)
    oversized = [
        item.path
        for item in bundle.files
        if len(item.content.encode("utf-8")) > contract.max_file_bytes
    ]
    missing_files = sorted(set(contract.required_files) - set(files))
    entrypoint_kinds = {item.kind for item in bundle.entrypoints}
    missing_entrypoints = sorted(set(contract.required_entrypoint_kinds) - entrypoint_kinds)
    checks.extend(
        [
            _check(
                "runtime.project_type",
                "Project type is supported by the Runtime Contract",
                bundle.project_type.casefold()
                in {item.casefold() for item in contract.supported_project_types},
                detail=(
                    f"{bundle.project_type} is not supported by "
                    f"{contract.contract_id}@{contract.version}"
                ),
                root_cause="runtime",
            ),
            _check(
                "runtime.required_files",
                "Runtime-required files are present",
                not missing_files,
                detail=f"Missing required files: {', '.join(missing_files)}",
                root_cause="runtime",
            ),
            _check(
                "runtime.entrypoints",
                "Runtime-required entrypoint kinds are declared",
                not missing_entrypoints,
                detail=f"Missing entrypoint kinds: {', '.join(missing_entrypoints)}",
                root_cause="runtime",
            ),
            _check(
                "runtime.tests",
                "Runtime-required tests are present",
                not contract.tests_required or any(item.role == "test" for item in bundle.files),
                detail="Runtime Contract requires at least one test file",
                root_cause="runtime",
            ),
            _check(
                "runtime.source_limits",
                "Source bundle stays within Runtime limits",
                len(bundle.files) <= contract.max_files
                and total_bytes <= contract.max_total_bytes
                and not oversized,
                detail=(
                    f"files={len(bundle.files)}/{contract.max_files}, "
                    f"bytes={total_bytes}/{contract.max_total_bytes}, "
                    f"oversized={', '.join(oversized) or 'none'}"
                ),
                root_cause="runtime",
            ),
        ]
    )
    if contract.document_semantics == "document" and "index.html" in files:
        html = files["index.html"].content
        document_boundaries = (
            r"<!doctype\s+html[^>]*>",
            r"<html(?:\s[^>]*)?>",
            r"<head(?:\s[^>]*)?>",
            r"</head\s*>",
            r"<body(?:\s[^>]*)?>",
            r"</body\s*>",
            r"</html\s*>",
        )
        complete_document = all(
            len(re.findall(pattern, html, flags=re.IGNORECASE)) == 1
            for pattern in document_boundaries
        )
        checks.append(
            _check(
                "runtime.document",
                "Web entrypoint is a complete HTML Document",
                complete_document,
                detail="index.html must contain one complete DOCTYPE/html/head/body document",
                root_cause="runtime",
            )
        )
    if contract.network_policy == "public_https_only":
        loopback = _find_patterns(
            (item.content for item in bundle.files),
            (
                r"https?://localhost(?:[:/]|$)",
                r"https?://127(?:\.[0-9]{1,3}){1,3}(?:[:/]|$)",
                r"https?://\[?::1\]?(?:[:/]|$)",
                r"https?://0\.0\.0\.0(?:[:/]|$)",
            ),
        )
        checks.append(
            _check(
                "security.loopback_network",
                "Source does not access localhost or loopback services",
                not loopback,
                detail="Runtime-bound source contains a localhost or loopback URL",
                root_cause="security",
                resolvable=False,
            )
        )
    return contract, ValidationReport(
        passed=all(check.status != "fail" for check in checks),
        checks=checks,
    )


def _find_patterns(contents: Iterable[str], patterns: tuple[str, ...]) -> bool:
    return any(
        re.search(pattern, content, flags=re.IGNORECASE) is not None
        for content in contents
        for pattern in patterns
    )


def engineer_contract_context(contract: RuntimeContract | None) -> dict[str, object]:
    if contract is None:
        return {
            "runtime_binding": None,
            "delivery_mode": "source_only",
            "instruction": (
                "Generate the requested project type as source. Do not create a Web substitute."
            ),
        }
    return {
        "runtime_binding": runtime_binding(contract).model_dump(mode="json"),
        "delivery_mode": "runtime_bound",
        "supported_project_types": contract.supported_project_types,
        "document_semantics": contract.document_semantics,
        "required_files": contract.required_files,
        "required_entrypoint_kinds": contract.required_entrypoint_kinds,
        "tests_required": contract.tests_required,
        "dependency_installation": contract.dependency_installation,
        "network_policy": contract.network_policy,
        "capabilities": contract.capabilities.model_dump(mode="json"),
        "limits": {
            "max_files": contract.max_files,
            "max_file_bytes": contract.max_file_bytes,
            "max_total_bytes": contract.max_total_bytes,
        },
    }
