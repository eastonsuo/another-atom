from another_atom.agent.provider import MockLLMProvider
from another_atom.config import get_settings
from another_atom.contracts.schemas import Mode, VersionSource
from another_atom.repository.service import (
    build_source_snapshot,
    calculate_source_diff,
    commit_version,
    initialize_repository,
)


def test_existing_project_source_becomes_an_implicit_change_baseline(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("PROJECT_REPOSITORY_ROOT", str(tmp_path / "repositories"))
    get_settings.cache_clear()
    provider = MockLLMProvider()
    prompt = "创建一个复古像素风扫雷游戏"
    blueprint = provider.create_blueprint(prompt, Mode.TEAM)
    architecture = provider.create_architecture_spec(blueprint)
    current = provider.create_app_spec(blueprint, architecture, prompt)
    project_id = "11111111-1111-1111-1111-111111111111"
    version_id = "22222222-2222-2222-2222-222222222222"
    initialize_repository(project_id)
    commit = commit_version(
        project_id,
        version_id,
        1,
        VersionSource.BUILD,
        current,
    )

    snapshot = build_source_snapshot(project_id, version_id, commit)
    brief = provider.create_change_brief(
        '把标题改成“夜间扫雷”，其他游戏逻辑保持不变', blueprint, current
    )
    requirements = provider.create_requirement_delta(brief, blueprint)
    revised_architecture = provider.revise_architecture_spec(
        blueprint, architecture, brief, requirements
    )
    revised = provider.revise_app_spec(
        blueprint,
        revised_architecture,
        current,
        brief,
        requirements,
    )
    source_diff = calculate_source_diff(snapshot, revised)

    assert snapshot.base_git_commit == commit
    assert {file.path for file in snapshot.files} == {
        "app-spec.json",
        "index.html",
        "styles.css",
        "app.js",
    }
    assert revised.hero_title == "夜间扫雷"
    assert revised.javascript == current.javascript
    assert "app.js" not in source_diff.changed_files
    assert {"app-spec.json", "index.html"} <= set(source_diff.changed_files)
    get_settings.cache_clear()
