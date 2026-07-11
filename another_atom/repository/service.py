import json
import os
import subprocess
from pathlib import Path

from another_atom.config import get_settings
from another_atom.contracts.schemas import AppSpec, VersionSource


class RepositoryError(RuntimeError):
    pass


MAX_BROWSER_FILE_BYTES = 256_000


def repository_path(project_id: str) -> Path:
    if not project_id or any(character not in "0123456789abcdef-" for character in project_id):
        raise RepositoryError("Invalid Project identifier for repository path")
    root = get_settings().project_repository_root.resolve()
    path = (root / project_id).resolve()
    if not path.is_relative_to(root):
        raise RepositoryError("Project repository escaped the configured root")
    return path


def initialize_repository(project_id: str) -> Path:
    path = repository_path(project_id)
    if (path / ".git").is_dir():
        return path
    path.mkdir(parents=True, exist_ok=False)
    _git(path, "init", "--initial-branch=main")
    _git(path, "config", "user.name", "Another Atom Runtime")
    _git(path, "config", "user.email", "runtime@another-atom.local")
    (path / "README.md").write_text(
        "# Another Atom Project\n\n"
        "`app-spec.json` is the editable source contract for the controlled V1 renderer.\n",
        encoding="utf-8",
    )
    (path / ".gitignore").write_text(".another-atom/worktrees/\n", encoding="utf-8")
    _git(path, "add", "README.md", ".gitignore")
    _git(path, "commit", "-m", "chore: initialize project repository")
    return path


def commit_version(
    project_id: str,
    version_id: str,
    version_number: int,
    source: VersionSource,
    app_spec: AppSpec,
) -> str:
    path = initialize_repository(project_id)
    marker_dir = path / ".another-atom"
    marker_dir.mkdir(exist_ok=True)
    marker_path = marker_dir / "version.json"
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("version_id") == version_id:
            return _git(path, "rev-parse", "HEAD")
    (path / "app-spec.json").write_text(
        json.dumps(app_spec.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    marker_path.write_text(
        json.dumps(
            {
                "version_id": version_id,
                "version_number": version_number,
                "source": source.value,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    _git(path, "add", "app-spec.json", ".another-atom/version.json")
    _git(path, "commit", "-m", f"version {version_number}: {source.value}")
    return _git(path, "rev-parse", "HEAD")


def list_repository_files(project_id: str) -> list[tuple[str, int]]:
    path = repository_path(project_id)
    if not path.is_dir():
        raise RepositoryError("Project repository was not found")
    entries: list[tuple[str, int]] = []
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if ".git" in relative.parts:
            continue
        if relative.parts[:2] == (".another-atom", "worktrees"):
            continue
        if candidate.is_file():
            entries.append((relative.as_posix(), candidate.stat().st_size))
    return sorted(entries, key=lambda item: (item[0].count("/"), item[0].casefold()))


def read_repository_file(project_id: str, relative_path: str) -> str:
    root = repository_path(project_id)
    if not relative_path or relative_path.startswith("/"):
        raise RepositoryError("Invalid repository file path")
    candidate = (root / relative_path).resolve()
    if not candidate.is_relative_to(root) or ".git" in candidate.relative_to(root).parts:
        raise RepositoryError("Repository file path is not readable")
    if not candidate.is_file():
        raise RepositoryError("Repository file was not found")
    if candidate.stat().st_size > MAX_BROWSER_FILE_BYTES:
        raise RepositoryError("Repository file is too large to display")
    try:
        return candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryError("Repository file is not UTF-8 text") from exc


def _git(path: Path, *arguments: str) -> str:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(path),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = subprocess.run(
        ["git", *arguments],
        cwd=path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RepositoryError(f"git {' '.join(arguments[:2])} failed: {detail}")
    return result.stdout.strip()
