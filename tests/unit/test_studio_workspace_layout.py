from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_desktop_workspace_owns_its_scroll_regions() -> None:
    app_source = (ROOT / "studio/src/App.tsx").read_text(encoding="utf-8")
    styles = (ROOT / "studio/src/styles.css").read_text(encoding="utf-8")

    assert '<div className="workspace-stage">' in app_source
    assert ".studio-main.active { height: 100vh; min-height: 0; overflow: hidden; }" in styles
    assert (
        ".workspace-grid { height: calc(100vh - 66px); min-height: 0; overflow: hidden; }"
        in styles
    )
    assert ".workspace-process { min-height: 0; overflow-y: auto; }" in styles
    assert (
        ".workspace-content { min-height: 0; display: flex; flex-direction: column; overflow: hidden; }"
        in styles
    )
    assert ".workspace-stage { flex: 1 1 auto; min-height: 0; overflow-y: auto; }" in styles
    assert ".workspace-stage .center-state { min-height: 100%; }" in styles
