from __future__ import annotations

import hashlib
import json

from another_atom.contracts.schemas import (
    ArchitectureDesign,
    ArchitectureDesignDraft,
    EngineerOutput,
    RuntimeContract,
    SourceBundle,
    SourceEntrypoint,
    SourceFile,
)
from another_atom.repository.service import render_version_files
from another_atom.runtime.contracts import runtime_binding, source_manifest_hash


def content_hash(content: str) -> str:
    return f"sha256:{hashlib.sha256(content.encode('utf-8')).hexdigest()}"


def create_architecture_design(
    draft: ArchitectureDesignDraft,
    product_spec_hash: str,
) -> ArchitectureDesign:
    content = render_architecture_design(draft)
    return ArchitectureDesign(
        **draft.model_dump(mode="python"),
        content=content,
        content_hash=content_hash(content),
        product_spec_hash=product_spec_hash,
    )


def render_architecture_design(draft: ArchitectureDesignDraft) -> str:
    def bullets(values: list[str]) -> list[str]:
        return [f"- {value}" for value in values] or ["- 无（None）"]

    components: list[str] = []
    for component in draft.components:
        files = "、".join(component.files) if component.files else "未指定"
        components.extend(
            [
                f"### {component.name}",
                "",
                component.responsibility,
                "",
                f"关键文件（Key files）：{files}",
                "",
            ]
        )
    visual = draft.visual_tokens
    lines = [
        "# 架构设计文档（Architecture Design）",
        "",
        "## 背景（Background）",
        "",
        "本文档依据已确认的产品规格（ProductSpec）生成，约束工程实现和运行验证边界。",
        "",
        "## 摘要（Summary）",
        "",
        draft.summary,
        "",
        "## 目标平台与运行适配器（Target Platform and Runtime Adapter）",
        "",
        f"- 目标平台（Target platform）：{draft.target_platform}",
        f"- 运行适配器（Runtime adapter）：{draft.runtime_adapter}",
        "- 已知能力缺口（Capability gaps）：",
        *[f"  {item}" for item in bullets(draft.capability_gaps)],
        "",
        "## 页面、模块与组件（Pages, Modules and Components）",
        "",
        *components,
        "## 状态与数据流（State and Data Flow）",
        "",
        *bullets(draft.state_and_data_flow),
        "",
        "## 关键交互（Key Interactions）",
        "",
        *bullets(draft.interactions),
        "",
        "## 接口与外部边界（Interfaces and External Boundaries）",
        "",
        *bullets(draft.interfaces),
        "",
        "## 目录与关键文件（Directory and Key Files）",
        "",
        *bullets(draft.directory_plan),
        "",
        "## 单元测试策略（Unit Test Strategy）",
        "",
        *bullets(draft.test_strategy),
        "",
        "## 验收映射（Acceptance Mapping）",
        "",
        *bullets(draft.acceptance_mapping),
        "",
        "## 视觉约束（Visual Constraints）",
        "",
        f"- 主色（Primary color）：{visual.primary_color}",
        f"- 强调色（Accent color）：{visual.accent_color}",
        f"- 背景色（Background color）：{visual.background_color}",
        f"- 字体方向（Typography）：{visual.typography}",
        f"- 信息密度（Density）：{visual.density}",
        f"- 风格（Style）：{visual.style}",
        "",
        "## 产品边界复核（Product Boundary Reapproval）",
        "",
        (
            f"需要回到产品规格确认：{draft.reapproval_reason}"
            if draft.requires_product_reapproval
            else "不需要额外确认；本设计未改变已确认的产品范围。"
        ),
        "",
    ]
    return "\n".join(lines)


def create_source_bundle(
    output: EngineerOutput,
    project_type: str,
    runtime_contract: RuntimeContract | None = None,
) -> SourceBundle:
    legacy_compatibility = runtime_contract is None and not output.source_files
    if output.source_files:
        drafts = [*output.source_files, *output.unit_tests]
        if not any(item.path == "app-spec.json" for item in drafts):
            drafts.append(
                SourceFile(
                    path="app-spec.json",
                    role="config",
                    content=json.dumps(
                        output.app_spec.model_dump(mode="json"),
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                    content_hash=content_hash(
                        json.dumps(
                            output.app_spec.model_dump(mode="json"),
                            ensure_ascii=False,
                            indent=2,
                        )
                        + "\n"
                    ),
                )
            )
    else:
        rendered = render_version_files(output.app_spec)
        drafts = [
            SourceFile(
                path=path,
                role="config" if path == "app-spec.json" else "source",
                content=content,
                content_hash=content_hash(content),
            )
            for path, content in sorted(rendered.items())
        ]
        drafts.extend(output.unit_tests)
    files: list[SourceFile] = []
    for item in drafts:
        if isinstance(item, SourceFile):
            files.append(item)
            continue
        files.append(
            SourceFile(
                **item.model_dump(mode="python"),
                content_hash=content_hash(item.content),
            )
        )
    if legacy_compatibility:
        bundle = SourceBundle(
            project_type=project_type,
            files=files,
            manifest_hash="sha256:" + ("0" * 64),
        )
        return bundle.model_copy(update={"manifest_hash": source_manifest_hash(bundle)})
    binding = runtime_binding(runtime_contract) if runtime_contract is not None else None
    entrypoints = list(output.entrypoints)
    if runtime_contract is not None and not entrypoints:
        entrypoints = [
            SourceEntrypoint(kind="application", path="index.html"),
            SourceEntrypoint(kind="test", path=output.unit_tests[0].path),
        ]
    bundle = SourceBundle(
        schema_version="2.0",
        adapter_id=binding.contract_id if binding is not None else None,
        project_type=project_type,
        entrypoint=None,
        entrypoints=entrypoints,
        runtime_binding=binding,
        files=files,
        manifest_hash="sha256:" + ("0" * 64),
    )
    return bundle.model_copy(update={"manifest_hash": source_manifest_hash(bundle)})


def create_source_bundle_from_files(
    candidate_files: dict[str, str],
    project_type: str,
    runtime_contract: RuntimeContract | None = None,
    entrypoints: list[SourceEntrypoint] | None = None,
) -> SourceBundle:
    files: list[SourceFile] = []
    for path, content in sorted(candidate_files.items()):
        role = (
            "config"
            if path == "app-spec.json"
            else "test"
            if path.startswith("tests/") and path.endswith(".test.js")
            else "source"
        )
        files.append(
            SourceFile(
                path=path,
                role=role,
                content=content,
                content_hash=content_hash(content),
            )
        )
    binding = runtime_binding(runtime_contract) if runtime_contract is not None else None
    resolved_entrypoints = list(entrypoints or [])
    available_paths = {item.path for item in files}
    test_paths = [item.path for item in files if item.role == "test"]
    if resolved_entrypoints:
        resolved_entrypoints = [
            (
                SourceEntrypoint(kind="test", path=test_paths[0])
                if item.kind == "test" and item.path not in available_paths and test_paths
                else item
            )
            for item in resolved_entrypoints
        ]
    if runtime_contract is not None and not resolved_entrypoints:
        resolved_entrypoints = [SourceEntrypoint(kind="application", path="index.html")]
        if test_paths:
            resolved_entrypoints.append(SourceEntrypoint(kind="test", path=test_paths[0]))
    bundle = SourceBundle(
        schema_version="2.0",
        adapter_id=binding.contract_id if binding is not None else None,
        project_type=project_type,
        entrypoint=None,
        entrypoints=resolved_entrypoints,
        runtime_binding=binding,
        files=files,
        manifest_hash="sha256:" + ("0" * 64),
    )
    return bundle.model_copy(update={"manifest_hash": source_manifest_hash(bundle)})


def replace_source_bundle_contents(
    bundle: SourceBundle,
    replacements: dict[str, str],
) -> SourceBundle:
    """Return the same source contract with selected file contents replaced."""
    known_paths = {item.path for item in bundle.files}
    unknown_paths = sorted(set(replacements) - known_paths)
    if unknown_paths:
        raise ValueError(f"SourceBundle replacement paths do not exist: {', '.join(unknown_paths)}")
    files = [
        item.model_copy(
            update={
                "content": replacements[item.path],
                "content_hash": content_hash(replacements[item.path]),
            }
        )
        if item.path in replacements
        else item
        for item in bundle.files
    ]
    candidate = bundle.model_copy(update={"files": files})
    return candidate.model_copy(update={"manifest_hash": source_manifest_hash(candidate)})
