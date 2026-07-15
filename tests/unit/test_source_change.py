from hashlib import sha256

import pytest

from another_atom.agent.provider import MockLLMProvider
from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    EngineerOutput,
    Mode,
    ProductSpec,
    SourceFileChange,
    SourceFileDraft,
    VersionSource,
)
from another_atom.repository.service import (
    SourceChangeError,
    build_source_context,
    build_source_snapshot,
    calculate_source_diff_from_files,
    commit_version,
    initialize_repository,
    materialize_source_file_change_set,
)
from another_atom.runtime.artifacts import (
    create_architecture_design,
    create_source_bundle,
    create_source_bundle_from_files,
)


def _prepared_change(tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    get_settings.cache_clear()
    provider = MockLLMProvider()
    prompt = "创建一个复古像素风扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    app_spec = provider.create_app_spec(blueprint, architecture, prompt)
    content = "# 扫雷游戏\n"
    product_spec = ProductSpec(
        summary="扫雷游戏产品说明",
        content=content,
        content_hash=f"sha256:{sha256(content.encode()).hexdigest()}",
    )
    architecture_design = create_architecture_design(
        provider.create_architecture_design(product_spec, blueprint),
        product_spec.content_hash,
    )
    source_bundle = create_source_bundle(
        EngineerOutput(
            app_spec=app_spec,
            unit_tests=[
                SourceFileDraft(
                    path="tests/app.test.js",
                    role="test",
                    content=(
                        "import test from 'node:test';\n"
                        "import assert from 'node:assert/strict';\n"
                        "test('source exists', () => assert.ok(true));\n"
                    ),
                )
            ],
        ),
        blueprint.product_type,
    )
    project_id = "11111111-1111-1111-1111-111111111111"
    version_id = "22222222-2222-2222-2222-222222222222"
    initialize_repository(project_id)
    commit = commit_version(
        project_id,
        version_id,
        1,
        VersionSource.BUILD,
        app_spec,
        source_bundle,
    )
    snapshot = build_source_snapshot(project_id, version_id, commit)
    brief = provider.create_change_brief(
        '把标题改成“夜间扫雷”，其他游戏逻辑保持不变',
        blueprint,
        app_spec,
    )
    requirements = provider.create_requirement_delta(brief, blueprint)
    revised_architecture = provider.revise_architecture_spec(
        blueprint, architecture, brief, requirements
    )
    return (
        provider,
        blueprint,
        revised_architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    )


def test_static_source_change_round_trip_rebuilds_runtime_contract(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )

    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    candidate_app, candidate_files, report = materialize_source_file_change_set(
        snapshot,
        context,
        change_set,
        app_spec,
        architecture,
    )
    source_bundle = create_source_bundle_from_files(
        candidate_files, blueprint.product_type
    )
    source_diff = calculate_source_diff_from_files(snapshot, candidate_files)

    assert {item.path for item in change_set.changes} == {"index.html"}
    assert all(item.path != "app-spec.json" for item in change_set.changes)
    assert "unified_diff" not in change_set.model_dump_json()
    assert candidate_app.hero_title == "夜间扫雷"
    assert "夜间扫雷" in candidate_files["index.html"]
    assert '"hero_title": "夜间扫雷"' in candidate_files["app-spec.json"]
    assert report.status == "passed"
    assert candidate_files["tests/app.test.js"] == next(
        item.content for item in snapshot.files if item.path == "tests/app.test.js"
    )
    assert source_bundle.manifest_hash.startswith("sha256:")
    assert {"app-spec.json", "index.html"} <= set(source_diff.changed_files)
    get_settings.cache_clear()


def test_static_source_change_canonicalizes_runtime_owned_html_shell(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    index_change = next(item for item in change_set.changes if item.path == "index.html")
    reformatted = (
        index_change.replacement_content.replace("<!doctype html>", "<!DOCTYPE html>")
        .replace("<body>\n", "<body >\n\n")
        .replace(
            '<script src="./app.js"></script>',
            '<script src="app.js" ></script>',
        )
    )
    change_set = change_set.model_copy(
        update={
            "changes": [
                item.model_copy(update={"replacement_content": reformatted})
                if item.path == "index.html"
                else item
                for item in change_set.changes
            ]
        }
    )

    candidate_app, candidate_files, report = materialize_source_file_change_set(
        snapshot, context, change_set, app_spec, architecture
    )

    assert candidate_app.hero_title == "夜间扫雷"
    assert candidate_files["index.html"].startswith("<!doctype html>\n")
    assert '<script src="./app.js"></script>\n</body>\n</html>\n' in candidate_files[
        "index.html"
    ]
    assert "runtime-document-shell-canonicalization" in report.checks
    get_settings.cache_clear()


def test_static_source_change_rejects_non_runtime_application_script(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    change_set = change_set.model_copy(
        update={
            "changes": [
                item.model_copy(
                    update={
                        "replacement_content": item.replacement_content.replace(
                            './app.js', 'https://example.com/app.js'
                        )
                    }
                )
                if item.path == "index.html"
                else item
                for item in change_set.changes
            ]
        }
    )

    with pytest.raises(SourceChangeError) as raised:
        materialize_source_file_change_set(
            snapshot, context, change_set, app_spec, architecture
        )

    assert raised.value.code == "CANDIDATE_CONTRACT_INVALID"
    get_settings.cache_clear()


def test_static_source_change_cannot_modify_omitted_baseline_file(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    styles = next(item for item in snapshot.files if item.path == "styles.css")
    context = build_source_context(
        snapshot,
        brief.original_request,
        len(styles.content),
        selected_files=["styles.css"],
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )

    with pytest.raises(SourceChangeError) as raised:
        materialize_source_file_change_set(
            snapshot, context, change_set, app_spec, architecture
        )

    assert raised.value.code == "CONTEXT_INSUFFICIENT"
    get_settings.cache_clear()


def test_static_source_change_rejects_before_hash_mismatch(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    first = change_set.changes[0]
    change_set = change_set.model_copy(
        update={
            "changes": [
                SourceFileChange(
                    **first.model_dump(mode="python", exclude={"before_hash"}),
                    before_hash="0" * 64,
                )
            ]
        }
    )

    with pytest.raises(SourceChangeError) as raised:
        materialize_source_file_change_set(
            snapshot, context, change_set, app_spec, architecture
        )

    assert raised.value.code == "SOURCE_CHANGE_HASH_MISMATCH"
    get_settings.cache_clear()


def test_static_source_change_rejects_output_over_configured_limit(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    monkeypatch.setenv("MAX_SOURCE_CHANGE_BYTES", "100")
    get_settings.cache_clear()

    with pytest.raises(SourceChangeError) as raised:
        materialize_source_file_change_set(
            snapshot, context, change_set, app_spec, architecture
        )

    assert raised.value.code == "SOURCE_CHANGE_OUTPUT_TOO_LARGE"
    get_settings.cache_clear()


@pytest.mark.parametrize(
    ("path", "operation", "before_hash"),
    [
        ("app-spec.json", "modify", "0" * 64),
        (".git/hooks/evil.py", "add", None),
    ],
)
def test_static_source_change_rejects_runtime_managed_and_git_paths(
    tmp_path,
    monkeypatch,
    path,
    operation,
    before_hash,
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    protected_change = SourceFileChange(
        path=path,
        operation=operation,
        before_hash=before_hash,
        replacement_content="print('forbidden')\n",
    )
    change_set = change_set.model_copy(update={"changes": [protected_change]})

    with pytest.raises(SourceChangeError) as raised:
        materialize_source_file_change_set(
            snapshot, context, change_set, app_spec, architecture
        )

    assert raised.value.code == "SOURCE_CHANGE_PATH_FORBIDDEN"
    get_settings.cache_clear()


def test_static_source_change_add_delete_survive_version_commit(
    tmp_path, monkeypatch
) -> None:
    (
        provider,
        blueprint,
        architecture,
        architecture_design,
        app_spec,
        product_spec,
        snapshot,
        brief,
        requirements,
    ) = _prepared_change(tmp_path, monkeypatch)
    context = build_source_context(
        snapshot,
        brief.original_request,
        120_000,
        runtime_managed_files=["app-spec.json"],
    )
    change_set = provider.create_source_file_change_set(
        "33333333-3333-3333-3333-333333333333",
        snapshot,
        context,
        product_spec,
        blueprint,
        architecture_design,
        architecture,
        brief,
        requirements,
        app_spec,
    )
    old_test = next(item for item in snapshot.files if item.path == "tests/app.test.js")
    new_test_content = (
        "import test from 'node:test';\n"
        "import assert from 'node:assert/strict';\n"
        "test('replacement exists', () => assert.ok(true));\n"
    )
    delete_test = SourceFileChange(
        path=old_test.path,
        operation="delete",
        before_hash=old_test.sha256,
    )
    add_test = SourceFileChange(
        path="tests/replacement.test.js",
        operation="add",
        replacement_content=new_test_content,
    )
    change_set = change_set.model_copy(
        update={"changes": [*change_set.changes, delete_test, add_test]}
    )

    candidate_app, candidate_files, _ = materialize_source_file_change_set(
        snapshot, context, change_set, app_spec, architecture
    )
    source_bundle = create_source_bundle_from_files(
        candidate_files, blueprint.product_type
    )
    commit = commit_version(
        snapshot.project_id,
        "44444444-4444-4444-4444-444444444444",
        2,
        VersionSource.AI_EDIT,
        candidate_app,
        source_bundle,
    )
    committed = build_source_snapshot(
        snapshot.project_id,
        "44444444-4444-4444-4444-444444444444",
        commit,
    )
    committed_paths = {item.path for item in committed.files}

    assert "tests/app.test.js" not in committed_paths
    assert "tests/replacement.test.js" in committed_paths
    get_settings.cache_clear()
