import json
import os
import re
import subprocess
import tempfile
from difflib import unified_diff
from hashlib import sha256
from pathlib import Path

from another_atom.config import get_settings
from another_atom.contracts.schemas import (
    AppSpec,
    ArchitectureSpec,
    BaseSourceSnapshot,
    SourceBundle,
    SourceContext,
    SourceDiff,
    SourcePatchApplyReport,
    SourcePatchOperation,
    SourcePatchSet,
    SourceSnapshotFile,
    VersionSource,
)


class RepositoryError(RuntimeError):
    pass


class SourcePatchError(RepositoryError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


MAX_BROWSER_FILE_BYTES = 256_000
VERSION_SOURCE_FILES = ("app-spec.json", "index.html", "styles.css", "app.js")
CODE_SUFFIXES = {".css", ".html", ".js", ".jsx", ".py", ".ts", ".tsx", ".yaml", ".yml"}
NETWORK_GUARD_JAVASCRIPT = """(() => {
  const blocked = (value) => {
    try {
      const raw = typeof value === 'string' ? value : value && value.url;
      const host = new URL(raw, window.location.href).hostname.toLowerCase();
      return host === 'localhost' || host.endsWith('.localhost') ||
        /^127(?:\\.[0-9]{1,3}){0,3}$/.test(host) ||
        host === '[::1]' || host === '::1' || host === '0.0.0.0';
    } catch (_) {
      return false;
    }
  };
  const deny = (value) => {
    if (blocked(value)) throw new TypeError('Localhost and loopback network access is blocked');
  };
  const nativeFetch = window.fetch.bind(window);
  window.fetch = (input, init) => {
    try { deny(input); } catch (error) { return Promise.reject(error); }
    return nativeFetch(input, init);
  };
  const nativeOpen = XMLHttpRequest.prototype.open;
  XMLHttpRequest.prototype.open = function(method, url, ...rest) {
    deny(url);
    return nativeOpen.call(this, method, url, ...rest);
  };
  const NativeWebSocket = window.WebSocket;
  window.WebSocket = class extends NativeWebSocket {
    constructor(url, protocols) {
      deny(url);
      super(url, protocols);
    }
  };
})();"""


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
        "Generated Web source is stored in `index.html`, `styles.css`, and `app.js`.\n"
        "`app-spec.json` preserves the versioned Agent contract.\n",
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
    source_bundle: SourceBundle | None = None,
) -> str:
    path = initialize_repository(project_id)
    marker_dir = path / ".another-atom"
    marker_dir.mkdir(exist_ok=True)
    marker_path = marker_dir / "version.json"
    if marker_path.exists():
        marker = json.loads(marker_path.read_text(encoding="utf-8"))
        if marker.get("version_id") == version_id:
            return _git(path, "rev-parse", "HEAD")
    version_files = (
        {item.path: item.content for item in source_bundle.files}
        if source_bundle is not None
        else render_version_files(app_spec)
    )
    generated_files = [".another-atom/version.json"]
    removed_files: list[str] = []
    if source_bundle is not None:
        tracked_files = _git(path, "ls-files").splitlines()
        controlled_files = {
            relative_path
            for relative_path in tracked_files
            if relative_path in VERSION_SOURCE_FILES
            or Path(relative_path).suffix.casefold() in CODE_SUFFIXES
        }
        removed_files = sorted(controlled_files - set(version_files))
        for relative_path in removed_files:
            _repository_text_path(project_id, relative_path).unlink(missing_ok=True)
    for relative_path, content in version_files.items():
        candidate = _repository_text_path(project_id, relative_path)
        candidate.parent.mkdir(parents=True, exist_ok=True)
        candidate.write_text(content, encoding="utf-8")
        generated_files.append(relative_path)
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
    _git(path, "add", "-A", "--", *generated_files, *removed_files)
    _git(path, "commit", "-m", f"version {version_number}: {source.value}")
    return _git(path, "rev-parse", "HEAD")


def build_source_snapshot(
    project_id: str,
    version_id: str,
    git_commit: str,
) -> BaseSourceSnapshot:
    """Read the controlled Project source from the exact version commit."""
    if not re_full_git_commit(git_commit):
        raise RepositoryError("Project version does not have a valid Git commit")
    path = repository_path(project_id)
    tracked_files = _git(path, "ls-tree", "-r", "--name-only", git_commit).splitlines()
    source_paths = sorted(
        {
            relative_path
            for relative_path in tracked_files
            if relative_path in VERSION_SOURCE_FILES
            or Path(relative_path).suffix.casefold() in CODE_SUFFIXES
        }
    )
    files: list[SourceSnapshotFile] = []
    for relative_path in source_paths:
        try:
            content = _git_file_at_commit(path, git_commit, relative_path)
        except RepositoryError as exc:
            if "does not exist" in str(exc) or "exists on disk" in str(exc):
                continue
            raise
        encoded = content.encode("utf-8")
        files.append(
            SourceSnapshotFile(
                path=relative_path,
                sha256=sha256(encoded).hexdigest(),
                size=len(encoded),
                content=content,
            )
        )
    if not files or not any(file.path == "app-spec.json" for file in files):
        raise RepositoryError("Project version source is incomplete")
    manifest = "\n".join(f"{file.path}\0{file.sha256}" for file in files)
    return BaseSourceSnapshot(
        project_id=project_id,
        base_version_id=version_id,
        base_git_commit=git_commit,
        files=files,
        source_manifest_hash=sha256(manifest.encode("utf-8")).hexdigest(),
    )


def build_source_context(
    snapshot: BaseSourceSnapshot,
    request: str,
    max_source_chars: int,
    selected_files: list[str] | None = None,
    runtime_managed_files: list[str] | None = None,
) -> SourceContext:
    """Pack whole source files into a deterministic character budget."""
    if max_source_chars <= 0:
        raise RepositoryError("MAX_SOURCE_CHARS must be greater than zero")
    files_by_path = {file.path: file for file in snapshot.files}
    managed_paths = {
        path for path in (runtime_managed_files or []) if path in files_by_path
    }
    ordered_paths: list[str] = []

    def add_path(relative_path: str) -> None:
        if (
            relative_path in files_by_path
            and relative_path not in managed_paths
            and relative_path not in ordered_paths
        ):
            ordered_paths.append(relative_path)

    for relative_path in selected_files or []:
        add_path(relative_path)
    for relative_path in _mentioned_source_paths(request, files_by_path):
        add_path(relative_path)
    for relative_path in sorted(files_by_path):
        add_path(relative_path)

    included: list[SourceSnapshotFile] = []
    omitted: list[str] = []
    used_chars = 0
    for relative_path in ordered_paths:
        source_file = files_by_path[relative_path]
        source_chars = len(source_file.content)
        if used_chars + source_chars <= max_source_chars:
            included.append(source_file)
            used_chars += source_chars
        else:
            omitted.append(relative_path)
    return SourceContext(
        source_manifest_hash=snapshot.source_manifest_hash,
        max_source_chars=max_source_chars,
        used_source_chars=used_chars,
        included_files=included,
        omitted_files=omitted,
        runtime_managed_files=sorted(managed_paths),
        trimming_applied=bool(omitted),
    )


def calculate_source_context_hash(context: SourceContext) -> str:
    payload = json.dumps(
        context.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _mentioned_source_paths(
    request: str, files_by_path: dict[str, SourceSnapshotFile]
) -> list[str]:
    mentioned: list[tuple[int, str]] = []
    for relative_path in sorted(files_by_path):
        pattern = rf"(?<![\w./-]){re.escape(relative_path)}(?![\w./-])"
        match = re.search(pattern, request)
        if match:
            mentioned.append((match.start(), relative_path))
    return [relative_path for _, relative_path in sorted(mentioned)]


def calculate_source_diff(
    snapshot: BaseSourceSnapshot,
    candidate: AppSpec,
) -> SourceDiff:
    return calculate_source_diff_from_files(snapshot, render_version_files(candidate))


def calculate_source_diff_from_files(
    snapshot: BaseSourceSnapshot,
    candidate_files: dict[str, str],
) -> SourceDiff:
    before = {file.path: file.content for file in snapshot.files}
    after = candidate_files
    changed = sorted(path for path in before.keys() & after.keys() if before[path] != after[path])
    added = sorted(after.keys() - before.keys())
    removed = sorted(before.keys() - after.keys())
    chunks: list[str] = []
    additions = 0
    deletions = 0
    for relative_path in sorted(set(changed + added + removed)):
        lines = list(
            unified_diff(
                before.get(relative_path, "").splitlines(keepends=True),
                after.get(relative_path, "").splitlines(keepends=True),
                fromfile=f"a/{relative_path}",
                tofile=f"b/{relative_path}",
            )
        )
        additions += sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        deletions += sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
        chunks.extend(lines)
    return SourceDiff(
        base_version_id=snapshot.base_version_id,
        changed_files=changed,
        added_files=added,
        removed_files=removed,
        line_additions=additions,
        line_deletions=deletions,
        unified_diff="".join(chunks)[:120_000],
    )


def apply_source_patch_set(
    snapshot: BaseSourceSnapshot,
    context: SourceContext,
    patch_set: SourcePatchSet,
    base_app_spec: AppSpec,
    architecture_spec: ArchitectureSpec,
) -> tuple[AppSpec, dict[str, str], SourcePatchApplyReport]:
    context_hash = calculate_source_context_hash(context)
    expected_bindings = {
        "project_id": snapshot.project_id,
        "base_version_id": snapshot.base_version_id,
        "base_git_commit": snapshot.base_git_commit,
        "source_manifest_hash": snapshot.source_manifest_hash,
        "source_context_hash": context_hash,
    }
    actual_bindings = {
        "project_id": patch_set.project_id,
        "base_version_id": patch_set.base_version_id,
        "base_git_commit": patch_set.base_git_commit,
        "source_manifest_hash": patch_set.source_manifest_hash,
        "source_context_hash": patch_set.source_context_hash,
    }
    if actual_bindings != expected_bindings:
        raise SourcePatchError(
            "PATCH_BASE_MISMATCH",
            "SourcePatchSet does not match the fixed Project baseline or SourceContext",
        )

    snapshot_files = {item.path: item for item in snapshot.files}
    included_files = {item.path: item for item in context.included_files}
    managed_files = set(context.runtime_managed_files) | {"app-spec.json"}
    allowed_add_suffixes = CODE_SUFFIXES
    required_files = {"index.html", "styles.css", "app.js"}
    patch_texts: list[str] = []
    for patch in patch_set.patches:
        path = patch.path
        if (
            path in managed_files
            or path == ".git"
            or path.startswith(".git/")
            or path.startswith(".another-atom/")
        ):
            raise SourcePatchError(
                "PATCH_PATH_FORBIDDEN",
                f"Runtime-managed file cannot be patched: {path}",
            )
        if patch.operation in {"modify", "delete"}:
            source_file = snapshot_files.get(path)
            if source_file is None:
                raise SourcePatchError(
                    "PATCH_PATH_FORBIDDEN",
                    f"Patch target does not exist in the fixed baseline: {path}",
                )
            if path not in included_files:
                raise SourcePatchError(
                    "CONTEXT_INSUFFICIENT",
                    f"Patch target was not fully included in SourceContext: {path}",
                )
            if patch.before_hash != source_file.sha256:
                raise SourcePatchError(
                    "PATCH_HASH_MISMATCH",
                    f"Patch before_hash does not match the fixed baseline: {path}",
                )
            if patch.operation == "delete" and path in required_files:
                raise SourcePatchError(
                    "PATCH_PATH_FORBIDDEN",
                    f"Required web-static-v1 file cannot be deleted: {path}",
                )
        else:
            if path in snapshot_files:
                raise SourcePatchError(
                    "PATCH_PATH_FORBIDDEN",
                    f"Add patch target already exists in the fixed baseline: {path}",
                )
            if Path(path).suffix.casefold() not in allowed_add_suffixes:
                raise SourcePatchError(
                    "PATCH_PATH_FORBIDDEN",
                    f"Added file type is not allowed by web-static-v1: {path}",
                )
        _validate_patch_headers(patch)
        patch_texts.append(
            patch.unified_diff
            if patch.unified_diff.endswith("\n")
            else f"{patch.unified_diff}\n"
        )

    combined_patch = "".join(patch_texts)
    with tempfile.TemporaryDirectory(prefix="another-atom-patch-") as directory:
        workspace = Path(directory)
        for source_file in snapshot.files:
            target = workspace / source_file.path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source_file.content, encoding="utf-8")
        checked = _run_git_apply(workspace, combined_patch, check=True)
        if checked.returncode != 0:
            raise SourcePatchError(
                "PATCH_CHECK_FAILED",
                checked.stderr.strip() or "git apply --check rejected SourcePatchSet",
            )
        applied = _run_git_apply(workspace, combined_patch, check=False)
        if applied.returncode != 0:
            raise SourcePatchError(
                "PATCH_APPLY_FAILED",
                applied.stderr.strip() or "git apply rejected SourcePatchSet",
            )
        candidate_paths = set(snapshot_files)
        for patch in patch_set.patches:
            if patch.operation == "delete":
                candidate_paths.discard(patch.path)
            else:
                candidate_paths.add(patch.path)
        candidate_files: dict[str, str] = {}
        for path in sorted(candidate_paths):
            target = workspace / path
            if not target.is_file() or target.is_symlink():
                raise SourcePatchError(
                    "CANDIDATE_CONTRACT_INVALID",
                    f"Candidate source is missing or not a regular file: {path}",
                )
            try:
                content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as exc:
                raise SourcePatchError(
                    "CANDIDATE_CONTRACT_INVALID",
                    f"Candidate source is not UTF-8 text: {path}",
                ) from exc
            if len(content) > 120_000:
                raise SourcePatchError(
                    "CANDIDATE_CONTRACT_INVALID",
                    f"Candidate source exceeds the V1 per-file limit: {path}",
                )
            candidate_files[path] = content

    if not required_files <= set(candidate_files):
        raise SourcePatchError(
            "CANDIDATE_CONTRACT_INVALID",
            "Candidate source is missing a required web-static-v1 entry file",
        )
    if not any(
        path.startswith("tests/") and path.endswith(".test.js")
        for path in candidate_files
    ):
        raise SourcePatchError(
            "CANDIDATE_CONTRACT_INVALID",
            "Candidate source must retain at least one tests/*.test.js file",
        )

    app_spec = _rebuild_app_spec_from_candidate(
        base_app_spec,
        architecture_spec,
        patch_set,
        candidate_files,
    )
    rendered = render_version_files(app_spec)
    for path in sorted(required_files):
        if candidate_files[path] != rendered[path]:
            raise SourcePatchError(
                "CANDIDATE_CONTRACT_INVALID",
                "Applied source cannot be represented by the AppSpec compatibility "
                f"contract: {path}",
            )
    candidate_files["app-spec.json"] = rendered["app-spec.json"]
    candidate_hash = _candidate_source_hash(candidate_files)
    report = SourcePatchApplyReport(
        source_context_hash=context_hash,
        applied_files=sorted(patch.path for patch in patch_set.patches),
        candidate_source_hash=candidate_hash,
        checks=[
            "baseline-and-context-binding",
            "path-and-before-hash-policy",
            "git-apply-check",
            "git-apply",
            "app-spec-source-consistency",
        ],
    )
    return app_spec, candidate_files, report


def _validate_patch_headers(patch: SourcePatchOperation) -> None:
    old_headers = [
        line[4:].strip()
        for line in patch.unified_diff.splitlines()
        if line.startswith("--- ")
    ]
    new_headers = [
        line[4:].strip()
        for line in patch.unified_diff.splitlines()
        if line.startswith("+++ ")
    ]
    if len(old_headers) != 1 or len(new_headers) != 1:
        raise SourcePatchError(
            "PATCH_CHECK_FAILED",
            f"Patch must contain exactly one old/new file header: {patch.path}",
        )
    expected = {
        "modify": (f"a/{patch.path}", f"b/{patch.path}"),
        "add": ("/dev/null", f"b/{patch.path}"),
        "delete": (f"a/{patch.path}", "/dev/null"),
    }[patch.operation]
    if (old_headers[0], new_headers[0]) != expected:
        raise SourcePatchError(
            "PATCH_CHECK_FAILED",
            f"Patch headers do not match declared operation/path: {patch.path}",
        )


def _run_git_apply(
    workspace: Path,
    patch: str,
    *,
    check: bool,
) -> subprocess.CompletedProcess[str]:
    arguments = ["git", "apply", "--whitespace=nowarn"]
    if check:
        arguments.append("--check")
    return subprocess.run(
        arguments,
        cwd=workspace,
        input=patch,
        capture_output=True,
        text=True,
        check=False,
    )


def _rebuild_app_spec_from_candidate(
    base_app_spec: AppSpec,
    architecture_spec: ArchitectureSpec,
    patch_set: SourcePatchSet,
    candidate_files: dict[str, str],
) -> AppSpec:
    html_document = candidate_files["index.html"]
    body_start = "<body>\n"
    body_end = '\n<script src="./app.js"></script>\n</body>\n</html>\n'
    if html_document.count(body_start) != 1 or not html_document.endswith(body_end):
        raise SourcePatchError(
            "CANDIDATE_CONTRACT_INVALID",
            "index.html changed the Runtime-managed document shell",
        )
    html = html_document.split(body_start, 1)[1][: -len(body_end)]

    css_file = candidate_files["styles.css"]
    if not css_file.endswith("\n"):
        raise SourcePatchError(
            "CANDIDATE_CONTRACT_INVALID",
            "styles.css must retain the Runtime-managed final newline",
        )
    css = css_file[:-1]

    javascript_file = candidate_files["app.js"]
    javascript_prefix = f"{NETWORK_GUARD_JAVASCRIPT}\n\n"
    if not javascript_file.startswith(javascript_prefix) or not javascript_file.endswith("\n"):
        raise SourcePatchError(
            "CANDIDATE_CONTRACT_INVALID",
            "app.js changed the Runtime-managed network guard",
        )
    javascript = javascript_file[len(javascript_prefix) : -1]
    metadata_updates = patch_set.app_spec_delta.model_dump(
        mode="python", exclude_none=True
    )
    return base_app_spec.model_copy(
        update={
            **metadata_updates,
            "html": html,
            "css": css,
            "javascript": javascript,
            "primary_color": architecture_spec.primary_color,
            "accent_color": architecture_spec.accent_color,
            "background_color": architecture_spec.background_color,
        }
    )


def _candidate_source_hash(candidate_files: dict[str, str]) -> str:
    manifest = "\n".join(
        f"{path}\0{sha256(content.encode('utf-8')).hexdigest()}"
        for path, content in sorted(candidate_files.items())
    )
    return sha256(manifest.encode("utf-8")).hexdigest()


def render_version_files(app_spec: AppSpec) -> dict[str, str]:
    files = {
        "app-spec.json": json.dumps(
            app_spec.model_dump(mode="json"), indent=2, ensure_ascii=False
        )
        + "\n"
    }
    if app_spec.html:
        files.update(
            {
                "index.html": _web_document(app_spec),
                "styles.css": app_spec.css + "\n",
                "app.js": guarded_browser_javascript(app_spec.javascript),
            }
        )
    else:
        product_cards = "\n".join(
            '<article class="product-card">'
            f"<h2>{item.name}</h2><p>{item.description}</p>"
            f"<strong>{item.price}</strong></article>"
            for item in app_spec.products
        )
        fallback = app_spec.model_copy(
            update={
                "html": (
                    f'<main><header><h1>{app_spec.hero_title}</h1>'
                    f"<p>{app_spec.hero_body}</p></header>"
                    f'<section class="product-grid">{product_cards}</section></main>'
                ),
                "css": (
                    f":root{{--primary:{app_spec.primary_color};--accent:{app_spec.accent_color};"
                    f"--background:{app_spec.background_color}}}"
                    "*{box-sizing:border-box}body{margin:0;background:var(--background);"
                    "color:var(--primary);font-family:system-ui,sans-serif}main{max-width:72rem;"
                    "margin:auto;padding:3rem 1.5rem}.product-grid{display:grid;"
                    "grid-template-columns:repeat(auto-fit,minmax(14rem,1fr));gap:1rem}"
                    ".product-card{padding:1.25rem;border:1px solid currentColor;"
                    "border-radius:1rem}"
                    ".product-card strong{color:var(--accent)}"
                ),
                "javascript": "document.documentElement.dataset.appReady = 'true';",
            }
        )
        files.update(
            {
                "index.html": _web_document(fallback),
                "styles.css": fallback.css + "\n",
                "app.js": guarded_browser_javascript(fallback.javascript),
            }
        )
    return files


def guarded_browser_javascript(source: str) -> str:
    return f"{NETWORK_GUARD_JAVASCRIPT}\n\n{source}\n"


def re_full_git_commit(value: str) -> bool:
    return len(value) == 40 and all(character in "0123456789abcdef" for character in value)


def _web_document(app_spec: AppSpec) -> str:
    title = (
        app_spec.project_name.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">\n'
        f"<title>{title}</title>\n"
        '<link rel="stylesheet" href="./styles.css">\n</head>\n<body>\n'
        f"{app_spec.html}\n"
        '<script src="./app.js"></script>\n</body>\n</html>\n'
    )


def list_repository_files(project_id: str) -> list[tuple[str, int]]:
    path = repository_path(project_id)
    if not path.is_dir():
        raise RepositoryError("Project repository was not found")
    entries: list[tuple[str, int]] = []
    for candidate in path.rglob("*"):
        relative = candidate.relative_to(path)
        if ".git" in relative.parts:
            continue
        if relative.parts and relative.parts[0] == ".another-atom":
            continue
        if candidate.is_file() and not candidate.is_symlink():
            entries.append((relative.as_posix(), candidate.stat().st_size))
    return sorted(entries, key=lambda item: (item[0].count("/"), item[0].casefold()))


def read_repository_file(project_id: str, relative_path: str) -> str:
    candidate = _repository_text_path(project_id, relative_path)
    if not candidate.is_file():
        raise RepositoryError("Repository file was not found")
    if candidate.stat().st_size > MAX_BROWSER_FILE_BYTES:
        raise RepositoryError("Repository file is too large to display")
    try:
        return candidate.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise RepositoryError("Repository file is not UTF-8 text") from exc


def repository_file_capabilities(relative_path: str) -> tuple[str, bool, str]:
    suffix = Path(relative_path).suffix.casefold()
    if suffix in {".md", ".markdown"}:
        kind, render_mode = "markdown", "markdown"
    elif suffix == ".json":
        kind, render_mode = "json", "source"
    elif suffix in CODE_SUFFIXES:
        kind, render_mode = "code", "source"
    else:
        kind, render_mode = "text", "source"
    editable = relative_path not in VERSION_SOURCE_FILES
    return kind, editable, render_mode


def repository_content_hash(content: str) -> str:
    return f"sha256:{sha256(content.encode('utf-8')).hexdigest()}"


def save_repository_text_file(
    project_id: str,
    relative_path: str,
    content: str,
    expected_hash: str,
    operation_id: str,
) -> tuple[str, str, int]:
    candidate = _repository_text_path(project_id, relative_path)
    _, editable, _ = repository_file_capabilities(relative_path)
    if not editable:
        raise RepositoryError("Repository file is read-only in the file panel")
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_BROWSER_FILE_BYTES:
        raise RepositoryError("Repository file is too large to save")
    current = read_repository_file(project_id, relative_path)
    if repository_content_hash(current) != expected_hash:
        raise RepositoryError("Repository file changed after it was opened")
    root = repository_path(project_id)
    if current == content:
        return repository_content_hash(content), _git(root, "rev-parse", "HEAD"), len(encoded)
    try:
        _atomic_write(candidate, encoded)
        _git(root, "add", "--", relative_path)
        _git(
            root,
            "commit",
            "-m",
            f"docs: update {relative_path}",
            "-m",
            f"File-Save-Operation: {operation_id}",
        )
        commit = _git(root, "rev-parse", "HEAD")
    except RepositoryError:
        _atomic_write(candidate, current.encode("utf-8"))
        try:
            _git(root, "restore", "--staged", "--", relative_path)
        except RepositoryError:
            pass
        raise
    return repository_content_hash(content), commit, len(encoded)


def write_product_spec(project_id: str, content: str) -> tuple[str, str]:
    relative_path = "docs/product-spec.md"
    root = initialize_repository(project_id)
    candidate = _repository_text_path(project_id, relative_path)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_BROWSER_FILE_BYTES:
        raise RepositoryError("Product specification is too large to save")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    previous = candidate.read_bytes() if candidate.exists() else None
    if previous == encoded:
        return repository_content_hash(content), _git(root, "rev-parse", "HEAD")
    try:
        _atomic_write(candidate, encoded)
        _git(root, "add", "--", relative_path)
        _git(root, "commit", "-m", "docs: add product specification")
        commit = _git(root, "rev-parse", "HEAD")
    except RepositoryError:
        if previous is None:
            candidate.unlink(missing_ok=True)
        else:
            _atomic_write(candidate, previous)
        try:
            _git(root, "restore", "--staged", "--", relative_path)
        except RepositoryError:
            pass
        raise
    return repository_content_hash(content), commit


def write_architecture_design(project_id: str, content: str) -> tuple[str, str]:
    relative_path = "docs/architecture-design.md"
    root = initialize_repository(project_id)
    candidate = _repository_text_path(project_id, relative_path)
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_BROWSER_FILE_BYTES:
        raise RepositoryError("Architecture design is too large to save")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    previous = candidate.read_bytes() if candidate.exists() else None
    if previous == encoded:
        return repository_content_hash(content), _git(root, "rev-parse", "HEAD")
    try:
        _atomic_write(candidate, encoded)
        _git(root, "add", "--", relative_path)
        _git(root, "commit", "-m", "docs: add architecture design")
        commit = _git(root, "rev-parse", "HEAD")
    except RepositoryError:
        if previous is None:
            candidate.unlink(missing_ok=True)
        else:
            _atomic_write(candidate, previous)
        try:
            _git(root, "restore", "--staged", "--", relative_path)
        except RepositoryError:
            pass
        raise
    return repository_content_hash(content), commit


def find_file_save_commit(project_id: str, operation_id: str) -> str | None:
    root = repository_path(project_id)
    result = _git(
        root,
        "log",
        "--all",
        "--fixed-strings",
        f"--grep=File-Save-Operation: {operation_id}",
        "--format=%H",
        "-1",
    )
    return result or None


def _repository_text_path(project_id: str, relative_path: str) -> Path:
    root = repository_path(project_id)
    if not relative_path or relative_path.startswith("/") or len(relative_path) > 500:
        raise RepositoryError("Invalid repository file path")
    unresolved = root / relative_path
    if unresolved.is_symlink():
        raise RepositoryError("Repository symlinks are not readable")
    candidate = unresolved.resolve()
    if not candidate.is_relative_to(root):
        raise RepositoryError("Repository file path is not readable")
    parts = candidate.relative_to(root).parts
    if not parts or parts[0] in {".git", ".another-atom"}:
        raise RepositoryError("Repository file path is not readable")
    return candidate


def _atomic_write(candidate: Path, content: bytes) -> None:
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=candidate.parent, prefix=f".{candidate.name}.", delete=False
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_name = temporary.name
        os.replace(temporary_name, candidate)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


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


def _git_file_at_commit(path: Path, git_commit: str, relative_path: str) -> str:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "HOME": str(path),
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    result = subprocess.run(
        ["git", "show", f"{git_commit}:{relative_path}"],
        cwd=path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "unknown git error"
        raise RepositoryError(f"git show failed: {detail}")
    return result.stdout
