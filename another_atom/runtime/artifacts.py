from __future__ import annotations

import hashlib
import json

from another_atom.contracts.schemas import (
    ArchitectureDesign,
    ArchitectureDesignDraft,
    EngineerOutput,
    SourceBundle,
    SourceFile,
)
from another_atom.repository.service import render_version_files


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
) -> SourceBundle:
    rendered = render_version_files(output.app_spec)
    files: list[SourceFile] = []
    for path, content in sorted(rendered.items()):
        role = "config" if path == "app-spec.json" else "source"
        files.append(
            SourceFile(path=path, role=role, content=content, content_hash=content_hash(content))
        )
    for test in output.unit_tests:
        files.append(
            SourceFile(
                **test.model_dump(mode="python"),
                content_hash=content_hash(test.content),
            )
        )
    manifest_payload = [
        {"path": item.path, "role": item.role, "content_hash": item.content_hash}
        for item in sorted(files, key=lambda item: item.path)
    ]
    manifest_hash = content_hash(
        json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"))
    )
    return SourceBundle(
        project_type=project_type,
        files=files,
        manifest_hash=manifest_hash,
    )


def create_source_bundle_from_files(
    candidate_files: dict[str, str],
    project_type: str,
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
    manifest_payload = [
        {"path": item.path, "role": item.role, "content_hash": item.content_hash}
        for item in files
    ]
    manifest_hash = content_hash(
        json.dumps(manifest_payload, ensure_ascii=False, separators=(",", ":"))
    )
    return SourceBundle(
        project_type=project_type,
        files=files,
        manifest_hash=manifest_hash,
    )
