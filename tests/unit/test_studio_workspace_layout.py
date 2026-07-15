from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_desktop_workspace_owns_its_scroll_regions() -> None:
    app_source = (ROOT / "studio/src/App.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "studio/src/styles.css").read_text(encoding="utf-8")

    assert '<div className="workspace-stage">' not in app_source
    assert ".studio-main.active { height: 100vh; min-height: 0; overflow: hidden; }" in styles
    assert (
        ".workspace-grid { height: calc(100vh - 66px); min-height: 0; overflow: hidden; }"
        in styles
    )
    assert ".workspace-process { min-height: 0; overflow-y: auto; }" in styles
    assert ".workspace-content { min-height: 0; overflow-y: auto; }" in styles
    assert (
        ".workspace-tools { height: 100%; min-height: 0; max-height: none; z-index: 2; }"
        in styles
    )
    assert (
        ".workspace-tool-content { position: relative; flex: 1; min-width: 0; "
        "min-height: 0; height: 100%; max-height: 100%; overflow: hidden; }"
        in styles
    )
    assert "grid-template-rows: auto minmax(160px, 34%) minmax(180px, 1fr);" in styles
    assert (
        ".failed-project-view { min-height: clamp(420px, calc(100vh - 300px), 640px); }"
        in styles
    )
    assert ".failed-project-view .center-state { min-height: 0; flex: 1 1 auto; }" in styles


def test_architecture_document_request_wins_over_background_file_refresh() -> None:
    app_source = (ROOT / "studio/src/App.tsx").read_text(encoding="utf-8")
    repository_source = (
        ROOT / "studio/src/components/RepositoryPanel.tsx"
    ).read_text(encoding="utf-8")

    assert (
        'requestedPath = run.architecture_design?.path ?? "docs/architecture-design.md";'
        in app_source
    )
    assert "const refreshGeneration = useRef(0);" in repository_source
    assert "const fileOpenGeneration = useRef(0);" in repository_source
    requested_effect = repository_source.split("if (!requestedFilePath) return;", 1)[1]
    assert requested_effect.index("refreshGeneration.current += 1;") < requested_effect.index(
        'setActive("files")'
    )
    assert requested_effect.index("setLoading(false);") < requested_effect.index(
        'setActive("files")'
    )
    assert requested_effect.index("await refresh(requestedFilePath);") < requested_effect.index(
        "onRequestedFileOpened?.();"
    )
